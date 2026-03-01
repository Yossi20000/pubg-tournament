# PUBG Tournament System - זיכרון מלא של המערכת

## פרטי המשתמש
- GitHub Username: yossi20000
- מחשב: Windows
- תיקיית פרויקט: C:\PUBG_Tournament\
- חשבון Render: קיים
- Render API Key: rnd_oxZZIV77rFTKyS8tD6TBwwdUNERJ

---

## קבצים במחשב
| קובץ | תיאור |
|------|--------|
| admin.html | פאנל אדמין ראשי - ניהול טורניר |
| overlay1-status.html | אוברליי לOBS - סטטוס שחקנים |
| overlay2-summary.html | אוברליי לOBS - סיכום |
| overlay3-cubes.html | אוברליי לOBS - קיוביות |
| overlay4-timer.html | אוברליי לOBS - טיימר |
| deploy.ps1 | סקריפט פריסה |
| push.ps1 | סקריפט push לGitHub |
| pages.ps1 | סקריפט GitHub Pages |

---

## GitHub
- Repository: https://github.com/yossi20000/pubg-tournament
- GitHub Pages (עובד!): https://yossi20000.github.io/pubg-tournament/
- Admin Panel: https://yossi20000.github.io/pubg-tournament/admin.html

---

## פיצ'רים של המערכת
- ניהול עד 8 בתים עם 16 קבוצות כל אחד
- מעקב סטטוס שחקנים: alive / knocked / dead
- ספירת kills
- ניקוד placement
- 4 אוברליי נפרדים לOBS
- טיימר משותף

---

## סטטוס הפיתוח

### Phase 1 - הושלם ✅
- כל הקבצים נבנו
- עלה ל-GitHub Pages ועובד
- גרסת localStorage עובדת מלא

### Phase 2 - WebSocket Migration - לא הושלם ❌
**המטרה:** מעבר מ-localStorage ל-WebSocket כדי לסנכרן בין מכשירים שונים.

**הארכיטקטורה המתוכננת:**
```
אדמין (כל מחשב/טלפון)
        ↕ WebSocket
   שרת Render ← שומר state בזיכרון
        ↕ WebSocket
   OBS Overlays (כל מחשב)
```

**מה נכתב:**
- server.js: Node.js + express + socket.io
- כל הקבצים עודכנו לעבוד עם socket.io במקום localStorage

**למה לא הושלם:**
- הסביבה של Claude חסומה מהאינטרנט - לא יכול להגיע ל-api.render.com
- הפריסה לא בוצעה אוטומטית

---

## הצעד הבא - פריסה ל-Render
1. היכנס ל-dashboard.render.com
2. New → Web Service
3. חבר את ה-repo: yossi20000/pubg-tournament
4. הגדרות:
   - Build Command: `npm install`
   - Start Command: `node server.js`
   - Environment: Node
5. קבל את ה-URL של Render
6. עדכן את כל הקבצים עם ה-URL החדש

---

## דברים עתידיים שרצינו להוסיף
- מערכת אוטומטית לחיבור לטלפון במצב spectator
- לחיצות אוטומטיות על הטלפון (ADB / פתרון אחר)
