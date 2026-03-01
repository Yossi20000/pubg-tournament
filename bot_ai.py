#!/usr/bin/env python3
import os, sys, time, json, base64, subprocess, requests
from pathlib import Path
try:
    from PIL import Image
    import io as _io
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

WORK_DIR        = Path(r"C:\PUBG_Tournament")
BRIDGE_FILE     = WORK_DIR / "bridge.js"
SETTINGS_FILE   = WORK_DIR / "bot_settings.json"
SCREENSHOT_FILE = WORK_DIR / "live_now.png"
STATE_FILE      = WORK_DIR / "tournament_state.json"
LOG_FILE        = WORK_DIR / "bot_ai.log"
CAPTURE_INTERVAL  = 1.5
CLAUDE_MODEL      = "claude-haiku-4-5-20251001"
CLAUDE_MAX_TOKENS = 1024
CLAUDE_API_URL    = "https://api.anthropic.com/v1/messages"

# כתובת ה-Render — ריק = רק מקומי
RENDER_URL    = os.environ.get("RENDER_URL", "")   # למשל: https://pubg-tm.onrender.com
BOT_SECRET    = os.environ.get("BOT_SECRET", "pubg-tournament-secret")
ADB_CANDIDATES = [
    r"C:\PUBG_Tournament\platform-tools\adb.exe",
    r"C:\Users\misra\AppData\Local\Android\Sdk\platform-tools\adb.exe",
    "adb",
]
VISION_PROMPT = '''Analyze this PUBG Mobile tournament screenshot. Return ONLY valid JSON, no markdown, no explanation.

JSON format:
{"mode":"lobby|game|spectate|loading|unknown","room_id":null,"room_name":null,"teams_alive":null,"players_alive":null,"zone_number":null,"eliminations":[],"lobby_teams":[],"lobby_count":null,"notes":""}

Rules:
- mode: "lobby" if waiting room, "game" if match in progress, "spectate" if watching, "loading" if loading screen
- room_id: the room ID number shown on screen (string), null if not visible
- room_name: room name/password if visible, null otherwise
- teams_alive: number of teams remaining (integer), null if not visible
- players_alive: number of players alive shown on screen (integer), null if not visible  
- zone_number: current zone/circle number (integer), null if not visible
- lobby_teams: list of team names visible in lobby list (strings). Extract ALL team names shown.
- lobby_count: total number of teams in lobby (integer), null if not visible
- eliminations: list of kills visible in kill feed RIGHT NOW. Each kill:
  {"killer_name":"exact name","killed_name":"exact name","weapon":"weapon name or empty","killer_team":"team name or empty","killed_team":"team name or empty"}
  IMPORTANT: Only include kills currently visible on screen. If kill feed is empty, return [].
  Extract exact player names as shown. Team names only if shown next to player name.

Be precise. Return only the JSON object.'''

phone_connected = False
iteration = 0
state = {"teams": {}, "kills": []}
prev_elim_keys = set()

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + "\n")
    except: pass

def find_adb():
    for c in ADB_CANDIDATES:
        try:
            r = subprocess.run([c, "version"], capture_output=True, timeout=3)
            if r.returncode == 0:
                log(f"[ADB] Found: {c}")
                return c
        except: continue
    return None

def check_phone(adb):
    try:
        r = subprocess.run([adb, "devices"], capture_output=True, timeout=5, text=True)
        lines = [l for l in r.stdout.splitlines() if "\t" in l and "offline" not in l]
        return len(lines) > 0
    except: return False

def capture_screenshot(adb):
    try:
        result = subprocess.run([adb, "exec-out", "screencap", "-p"], capture_output=True, timeout=8)
        if result.returncode == 0 and len(result.stdout) > 5000:
            SCREENSHOT_FILE.write_bytes(result.stdout)
            return True
    except: pass
    return False

def image_to_base64():
    if HAS_PIL:
        try:
            img = Image.open(SCREENSHOT_FILE)
            img.thumbnail((1280, 720), Image.LANCZOS)
            buf = _io.BytesIO()
            img.save(buf, format='JPEG', quality=75)
            return base64.standard_b64encode(buf.getvalue()).decode('utf-8'), "image/jpeg"
        except: pass
    return base64.standard_b64encode(SCREENSHOT_FILE.read_bytes()).decode('utf-8'), "image/png"

def ask_claude(api_key, img_b64, media_type):
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    body = {"model": CLAUDE_MODEL, "max_tokens": CLAUDE_MAX_TOKENS, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img_b64}},
        {"type": "text", "text": VISION_PROMPT}
    ]}]}
    resp = requests.post(CLAUDE_API_URL, json=body, headers=headers, timeout=20)
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)

def write_bridge(extra=None):
    data = {"ts": time.time(), "phone_connected": phone_connected, "mode": state.get("mode","unknown"),
            "room_id": state.get("room_id"), "room_name": state.get("room_name"),
            "teams_alive": state.get("teams_alive"), "players_alive": state.get("players_alive"),
            "zone": state.get("zone"), "lobby_teams": state.get("lobby_teams",[]),
            "lobby_count": state.get("lobby_count"), "last_kills": state.get("kills",[])[-15:],
            "teams": state.get("teams",{}), "notes": state.get("notes",""), "iteration": iteration}
    if extra: data.update(extra)
    # כתוב מקומית תמיד
    BRIDGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    # שלח ל-Render אם מוגדר
    if RENDER_URL:
        try:
            requests.post(f"{RENDER_URL}/api/bot-data", json=data,
                headers={"x-bot-secret": BOT_SECRET}, timeout=3)
        except Exception as e:
            pass  # לא קריטי — מקומי עדיין עובד

def process_result(result):
    global prev_elim_keys
    changed = False

    # עדכן שדות בסיסיים
    for field in ["mode","room_id","room_name","teams_alive","players_alive","lobby_teams","lobby_count","notes"]:
        v = result.get(field)
        if v is not None and v != [] and v != "":
            state[field] = v; changed = True
    if result.get("zone_number"):
        state["zone"] = result["zone_number"]; changed = True

    # הוסף קבוצות מהלובי
    for tname in (result.get("lobby_teams") or []):
        tname = tname.strip() if tname else ""
        if tname and tname not in state["teams"]:
            state["teams"][tname] = {"name": tname, "alive": True, "kills": 0}
            log(f"  -> New team: {tname}"); changed = True

    # עדכן teams_alive — סמן קבוצות כמתות לפי מספר
    if result.get("teams_alive") is not None:
        alive_count = result["teams_alive"]
        # אם יש לנו יותר קבוצות מאשר alive — לא נדע אילו מתו בלי מידע נוסף
        state["teams_alive"] = alive_count; changed = True

    # טיפול בקילים — מפתח ייחודי עם timestamp שעה לדיוק
    current_frame_keys = set()
    for elim in (result.get("eliminations") or []):
        killer = (elim.get("killer_name") or "").strip()
        killed = (elim.get("killed_name") or "").strip()
        if not killer or not killed:
            continue
        weapon = (elim.get("weapon") or "").strip()
        killer_team = (elim.get("killer_team") or "").strip()
        killed_team = (elim.get("killed_team") or "").strip()

        # מפתח: שם+שם (ללא weapon כי PUBG מציג אותו לפעמים שונה)
        key = f"{killer}|{killed}"
        current_frame_keys.add(key)

        # רק אם לא ראינו את זה בפריים הקודם
        if key not in prev_elim_keys:
            # נסה לזהות קבוצה לפי שם שחקן אם Claude לא מצא
            if not killer_team:
                for tname, tdata in state.get("teams",{}).items():
                    if killer.lower() in tname.lower() or tname.lower() in killer.lower():
                        killer_team = tname; break
            if not killed_team:
                for tname, tdata in state.get("teams",{}).items():
                    if killed.lower() in tname.lower() or tname.lower() in killed.lower():
                        killed_team = tname; break

            entry = {
                "ts": time.strftime("%H:%M:%S"),
                "killer": killer, "killed": killed,
                "weapon": weapon,
                "killer_team": killer_team, "killed_team": killed_team
            }
            state.setdefault("kills",[]).append(entry)

            # עדכן kills לקבוצה המתאימה
            if killer_team and killer_team in state.get("teams",{}):
                state["teams"][killer_team]["kills"] = state["teams"][killer_team].get("kills",0) + 1

            # סמן קבוצה כמתה אם כל השחקנים שלה נהרגו (פשוט: tracked killed)
            if killed_team and killed_team in state.get("teams",{}):
                state["teams"][killed_team].setdefault("killed_players", [])
                if killed not in state["teams"][killed_team]["killed_players"]:
                    state["teams"][killed_team]["killed_players"].append(killed)

            log(f"  KILL: [{killer_team or '?'}]{killer} -> [{killed_team or '?'}]{killed} ({weapon})")
            changed = True

    # שמור את הפריים הנוכחי לפריים הבא
    # רק אם יש eliminations בפריים הזה — כדי לא לאפס כשהkill feed נעלם
    if current_frame_keys:
        prev_elim_keys = current_frame_keys

    return changed

def load_env():
    """טען משתני סביבה מ-.env"""
    env = WORK_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

def load_api_key():
    load_env()
    # עדיפות: הגדרות פאנל → .env → משתנה סביבה
    try:
        s = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
        if s.get("apiKey"): return s["apiKey"]
    except: pass
    return os.environ.get("ANTHROPIC_API_KEY", "")

def main():
    global phone_connected, iteration, state
    log("==================================================")
    log("PUBG Bot v6 - Ultra Fast Vision")
    log(f"PIL: {'YES jpeg compression' if HAS_PIL else 'NO using png'}")
    log("==================================================")
    api_key = load_api_key()
    if not api_key: log("ERROR: Missing API key!"); sys.exit(1)
    log(f"API Key: {api_key[:10]}...")
    # טען RENDER_URL אחרי load_env שכבר נקרא
    global RENDER_URL, BOT_SECRET
    RENDER_URL = os.environ.get("RENDER_URL", RENDER_URL)
    BOT_SECRET = os.environ.get("BOT_SECRET", BOT_SECRET)
    if RENDER_URL:
        log(f"Render URL: {RENDER_URL}")
    else:
        log("Render: not configured (local only)")
    adb = find_adb()
    if not adb: log("ERROR: ADB not found"); sys.exit(1)
    try: state = json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except: pass
    consecutive_fails = 0
    while True:
        connected = check_phone(adb)
        if connected != phone_connected:
            phone_connected = connected
            log("Phone CONNECTED" if connected else "Phone DISCONNECTED")
            write_bridge()
        if not phone_connected:
            write_bridge({"error": "Phone not connected"})
            time.sleep(2); continue
        t0 = time.time()
        if not capture_screenshot(adb):
            consecutive_fails += 1
            log(f"Screenshot failed ({consecutive_fails})")
            if consecutive_fails >= 3:
                phone_connected = False
                write_bridge({"error": "ADB not responding"})
            time.sleep(1); continue
        consecutive_fails = 0
        try:
            img_b64, media_type = image_to_base64()
            size_kb = len(img_b64) * 3 // 4 // 1024
            # שלח תמונה ל-Render ברקע
            if RENDER_URL:
                try:
                    requests.post(f"{RENDER_URL}/api/screenshot",
                        json={"image": img_b64},
                        headers={"x-bot-secret": BOT_SECRET}, timeout=3)
                except: pass
            t1 = time.time()
            log(f"[{iteration+1}] {size_kb}KB {media_type.split('/')[1]} -> Claude...")
            result = ask_claude(api_key, img_b64, media_type)
            claude_time = time.time() - t1
            iteration += 1
            changed = process_result(result)
            log(f"  OK {state.get('mode','?')} | teams={state.get('teams_alive','?')} zone={state.get('zone','?')} | cap={time.time()-t0-claude_time:.1f}s claude={claude_time:.1f}s")
            write_bridge()
            if changed:
                try: STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
                except: pass
        except requests.exceptions.HTTPError as e:
            log(f"  API Error {e.response.status_code}")
            write_bridge({"error": f"API Error {e.response.status_code}"}); time.sleep(3); continue
        except json.JSONDecodeError as e:
            log(f"  JSON error: {e}")
        except Exception as e:
            log(f"  Error: {type(e).__name__}: {e}"); time.sleep(2); continue
        elapsed = time.time() - t0
        wait = max(0, CAPTURE_INTERVAL - elapsed)
        if wait > 0: time.sleep(wait)

if __name__ == "__main__":
    main()