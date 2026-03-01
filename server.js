const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const path = require('path');
const fs = require('fs');
const { spawn, exec } = require('child_process');

const app = express();
const server = http.createServer(app);
const io = new Server(server, {
  cors: { origin: '*' }
});

// Serve static files
app.use(express.static(path.join(__dirname, 'public')));

// In-memory state
let gameState = null;
let timerState = { totalSeconds: 600, remaining: 600, running: false, inputMin: 10, inputSec: 0 };
let timerInterval = null;

function timerTick() {
  if (!timerState.running) return;
  timerState.remaining--;
  if (timerState.remaining <= 0) {
    timerState.remaining = 0;
    timerState.running = false;
    clearInterval(timerInterval);
    timerInterval = null;
  }
  io.emit('update', { state: gameState, timer: timerState });
}

// Socket.io
io.on('connection', (socket) => {
  console.log('Client connected:', socket.id);
  
  // Send current state to new client
  socket.emit('update', { state: gameState, timer: timerState });

  // Admin sends full state update
  socket.on('setState', (data) => {
    if (data.state !== undefined) gameState = data.state;
    if (data.timer !== undefined) {
      const t = data.timer;
      // Handle timer commands
      if (t.cmd === 'start') {
        if (!timerState.running && timerState.remaining > 0) {
          timerState.running = true;
          timerInterval = setInterval(timerTick, 1000);
        }
      } else if (t.cmd === 'pause') {
        timerState.running = false;
        clearInterval(timerInterval);
        timerInterval = null;
      } else if (t.cmd === 'reset' || t.cmd === 'set') {
        timerState.running = false;
        clearInterval(timerInterval);
        timerInterval = null;
        timerState.totalSeconds = t.totalSeconds || 600;
        timerState.remaining = timerState.totalSeconds;
        timerState.inputMin = t.inputMin || 10;
        timerState.inputSec = t.inputSec || 0;
      } else {
        // Direct timer state merge
        Object.assign(timerState, t);
      }
    }
    io.emit('update', { state: gameState, timer: timerState });
  });

  socket.on('disconnect', () => {
    console.log('Client disconnected:', socket.id);
  });
});

const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`PUBG TM Server running on port ${PORT}`);
});

// ══════════════════════════════════════════════
// BOT CONTROL API
// ══════════════════════════════════════════════
const WORK_DIR = __dirname;
let botProcess = null;
let botPid = null;

app.use(express.json());

// ── BOT DATA ENDPOINT (מהבוט המקומי → Render → כולם) ──────────
// הבוט שולח POST כל 1.5 שניות עם נתוני המשחק
let latestBotData = null;
const BOT_SECRET = process.env.BOT_SECRET || 'pubg-tournament-secret';

app.post('/api/bot-data', (req, res) => {
  const auth = req.headers['x-bot-secret'];
  if (auth !== BOT_SECRET) return res.status(401).json({ error: 'unauthorized' });
  latestBotData = req.body;
  // הפץ לכל הדפדפנים המחוברים בזמן אמת
  io.emit('bot-update', latestBotData);
  res.json({ ok: true });
});

// GET /api/bot-data — הפאנל יכול לקרוא גם בלי Socket.io
app.get('/api/bot-data', (req, res) => {
  res.json(latestBotData || { error: 'no data yet' });
});

// Serve files from root too (for bridge.js, live_now.png etc.)
app.use(express.static(WORK_DIR));

// GET /api/bot-status
app.get('/api/bot-status', (req, res) => {
  const alive = botProcess && !botProcess.killed;
  let bridge = null;
  try {
    bridge = JSON.parse(fs.readFileSync(path.join(WORK_DIR,'bridge.js'), 'utf-8'));
  } catch(e) {}
  res.json({ running: alive, pid: botPid, bridge });
});

// POST /api/bot-start
app.post('/api/bot-start', (req, res) => {
  if (botProcess && !botProcess.killed) {
    return res.json({ ok: false, msg: 'כבר רץ', pid: botPid });
  }
  try {
    // נסה python, python3, py לפי מה שמותקן
    const pyCmd = (() => {
      const cmds = ['python', 'python3', 'py'];
      const { execSync } = require('child_process');
      for (const cmd of cmds) {
        try { execSync(`${cmd} --version`, {timeout:3000}); return cmd; }
        catch(e) {}
      }
      return 'python';
    })();
    botProcess = spawn(pyCmd, [path.join(WORK_DIR,'bot_ai.py')], {
      cwd: WORK_DIR,
      stdio: ['ignore','pipe','pipe']
    });
    botPid = botProcess.pid;
    botProcess.stdout.on('data', d => {
      const line = d.toString().replace(/\r?\n/,'');
      io.emit('bot-log', { type:'info', msg: line });
      console.log('[BOT]', line);
    });
    botProcess.stderr.on('data', d => {
      const line = d.toString().replace(/\r?\n/,'');
      io.emit('bot-log', { type:'error', msg: line });
    });
    botProcess.on('exit', (code) => {
      io.emit('bot-log', { type:'warn', msg: `Bot יצא עם קוד ${code}` });
      io.emit('bot-status', { running: false, pid: null });
      botProcess = null; botPid = null;
    });
    io.emit('bot-status', { running: true, pid: botPid });
    res.json({ ok: true, pid: botPid });
  } catch(e) {
    res.json({ ok: false, msg: e.message });
  }
});

// POST /api/bot-stop
app.post('/api/bot-stop', (req, res) => {
  if (!botProcess || botProcess.killed) {
    return res.json({ ok: false, msg: 'לא רץ' });
  }
  botProcess.kill('SIGTERM');
  // fallback
  setTimeout(() => {
    if (botProcess && !botProcess.killed) botProcess.kill('SIGKILL');
  }, 3000);
  res.json({ ok: true });
});

// POST /api/bot-settings  — פאנל שולח הגדרות
app.post('/api/bot-settings', (req, res) => {
  try {
    fs.writeFileSync(path.join(WORK_DIR,'bot_settings.json'),
      JSON.stringify(req.body, null, 2), 'utf-8');
    res.json({ ok: true });
  } catch(e) {
    res.json({ ok: false, msg: e.message });
  }
});

// GET /api/screenshot -- no-cache
app.get('/api/screenshot', (req, res) => {
  // אם יש תמונה בזיכרון (מהבוט), שלח אותה
  if (latestScreenshot) {
    res.setHeader('Content-Type', 'image/jpeg');
    res.setHeader('Cache-Control', 'no-store');
    return res.send(latestScreenshot);
  }
  // fallback לקובץ מקומי (רק כשרץ מקומית)
  const p = path.join(WORK_DIR, 'live_now.png');
  if (!fs.existsSync(p)) return res.status(404).send('no screenshot');
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');
  res.sendFile(p);
});

// POST /api/screenshot — הבוט שולח תמונה (base64 JPEG)
let latestScreenshot = null;
app.post('/api/screenshot', express.json({ limit: '2mb' }), (req, res) => {
  const auth = req.headers['x-bot-secret'];
  if (auth !== BOT_SECRET) return res.status(401).json({ error: 'unauthorized' });
  if (req.body && req.body.image) {
    latestScreenshot = Buffer.from(req.body.image, 'base64');
    io.emit('screenshot-updated', { ts: Date.now() });
  }
  res.json({ ok: true });
});

// Watch live_now.png -- WebSocket push on change
const SCREEN_PATH = path.join(WORK_DIR, 'live_now.png');
let lastScreenMtime = 0;
setInterval(() => {
  try {
    const mtime = fs.statSync(SCREEN_PATH).mtimeMs;
    if (mtime !== lastScreenMtime) {
      lastScreenMtime = mtime;
      io.emit('screenshot-updated', { ts: mtime });
    }
  } catch(e) {}
}, 800);

// ── MJPEG LIVE STREAM ──────────────────────────────────────────
// GET /api/stream — שידור MJPEG רציף מה-ADB
const ADB_PATH = (() => {
  const candidates = [
    path.join(WORK_DIR, 'platform-tools', 'adb.exe'),
    path.join(WORK_DIR, 'adb', 'adb.exe'),
    'adb'
  ];
  const { execSync } = require('child_process');
  for (const c of candidates) {
    try { execSync(`"${c}" version`, { timeout: 2000 }); return c; } catch(e) {}
  }
  return null;
})();

let streamClients = new Set();

app.get('/api/stream', (req, res) => {
  if (!ADB_PATH) return res.status(503).send('ADB not found');

  res.setHeader('Content-Type', 'multipart/x-mixed-replace; boundary=frame');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  res.flushHeaders();

  streamClients.add(res);

  const sendFrame = () => {
    if (res.writableEnded) { streamClients.delete(res); return; }
    const p = path.join(WORK_DIR, 'live_now.png');
    if (!fs.existsSync(p)) { setTimeout(sendFrame, 500); return; }
    try {
      const img = fs.readFileSync(p);
      res.write('--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + img.length + '\r\n\r\n');
      res.write(img);
      res.write('\r\n');
    } catch(e) {}
    setTimeout(sendFrame, 500); // 2fps מה-live_now.png
  };

  sendFrame();

  req.on('close', () => { streamClients.delete(res); });
});

// ── SCRCPY LAUNCHER ──────────────────────────────────────────
const SCRCPY_PATH = (() => {
  const candidates = [
    'C:\\Users\\misra\\AppData\\Local\\Microsoft\\WinGet\\Packages\\Genymobile.scrcpy_Microsoft.Winget.Source_8wekyb3d8bbwe\\scrcpy-win64-v3.3.4\\scrcpy.exe',
    'scrcpy'
  ];
  const { execSync } = require('child_process');
  for (const c of candidates) {
    try { execSync(`"${c}" --version`, { timeout: 2000 }); return c; } catch(e) {}
  }
  return null;
})();

let scrcpyProcess = null;

app.post('/api/scrcpy-start', (req, res) => {
  if (scrcpyProcess && !scrcpyProcess.killed) {
    return res.json({ ok: false, msg: 'כבר רץ' });
  }
  if (!SCRCPY_PATH) return res.json({ ok: false, msg: 'scrcpy לא נמצא' });
  try {
    scrcpyProcess = spawn(SCRCPY_PATH, [
      '--window-title', 'PUBG LIVE',
      '--always-on-top',
      '--window-width', '540',
      '--window-height', '960',
      '--no-audio',
      '--max-fps', '30'
    ], { detached: true, stdio: 'ignore' });
    scrcpyProcess.unref();
    res.json({ ok: true });
  } catch(e) {
    res.json({ ok: false, msg: e.message });
  }
});

app.post('/api/scrcpy-stop', (req, res) => {
  if (scrcpyProcess && !scrcpyProcess.killed) {
    scrcpyProcess.kill();
    scrcpyProcess = null;
  }
  res.json({ ok: true });
});