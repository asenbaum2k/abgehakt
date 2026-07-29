# abgehakt v2 ✅

Smarte To-Do Liste — was muss, wird abgehakt.

Mobile-first iPhone PWA mit Python/FastAPI + SQLite + Vanilla JS/CSS. Zugriff nur über Tailscale (privat).

## 🚀 Start

```bash
cd src/backend
pip install -r requirements.txt
python main.py
# → http://localhost:8766
```

## ✨ V2 Features (neu)

### 🔔 Browser-Notifications bei Fälligkeit
- Permission-Flow: Klick auf 🔔 im Header → Browser-Frage
- Clientseitiger Scheduler prüft jede Minute auf fällige Todos
- Notification erscheint bei exakter Uhrzeit (wenn `due_time` gesetzt & "Erinnern" aktiviert)
- Service Worker fängt Notification-Clicks ab und fokussiert die App

### 🔁 Wiederkehrende Todos
- Intervalle: **Täglich**, **Wöchentlich**, **Monatlich**, **Jährlich**
- Beim Abhaken (✓) wird automatisch die nächste Instanz erstellt
- Keine Duplikate: Nur wenn zutreffend (uncompleted + hat due_date)
- Monatsübergänge werden korrekt behandelt (31. Jan → 28. Feb etc.)
- Badge zeigt das Intervall an jedem Todo an

### 🏷️ Tags / Labels
- Eingabe: Komma-getrennt im Add-Form
- Anzeige: Klickbare Chips unter jedem Todo
- Filter: Tag-Chips unter den Tabs — anklicken filtert die Liste
- API: `GET /api/tags` + `GET /api/todos?tag=work`

### 👆 Mobile Swipe-to-Delete mit Undo
- Nach links wischen → löschen
- Visuelles Feedback (opacity + translation)
- **Undo-Bar** erscheint nach Löschen für 6 Sekunden
- "Rückgängig" stellt das Todo wieder her (POST /api/todos/{id}/undo)

### 📱 PWA / Service Worker
- `sw.js` cached HTML, CSS, JS, Icons für Offline-Zugriff
- Installierbar auf iPhone/Android Homescreen
- `manifest.json` mit Standalone-Mode

## 📡 API Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|-------------|
| GET | `/api/todos?filter=all\|today\|week&tag=` | Todos mit optionalem Filter |
| GET | `/api/tags` | Alle Tags |
| POST | `/api/todos` | Neues Todo |
| GET | `/api/todos/{id}` | Einzelnes Todo |
| PATCH | `/api/todos/{id}` | Felder aktualisieren |
| PATCH | `/api/todos/{id}/toggle` | Abhaken (recurring → next) |
| DELETE | `/api/todos/{id}` | Löschen (soft, archiviert) |
| POST | `/api/todos/{id}/undo` | Gelöschtes wiederherstellen |

### Todo-Felder

```json
{
  "title": "Milch kaufen",
  "notes": "Vollmilch",
  "due_date": "2026-07-30",
  "due_time": "18:00",
  "recurring": "weekly",
  "tags": "einkauf,küche",
  "notify_at": "due"
}
```

## 🧪 Tests

```bash
cd src/backend
pytest tests/ -v
```

Tests decken ab: CRUD, Tags (create/list/filter), Recurring (daily/weekly/monthly advance), Undo, Notify, Filter modes.

## 🏗️ Architektur

```
src/
├── backend/
│   ├── main.py          # FastAPI app + routes
│   ├── database.py      # SQLite mit Migrationen
│   ├── models.py        # Pydantic models
│   ├── requirements.txt
│   └── tests/
│       └── test_api.py  # 20+ tests
└── frontend/
    ├── index.html       # Mobile-first UI
    ├── app.js           # V2 features
    ├── style.css        # Ampel + Dark Mode + Swipe
    ├── sw.js            # Service Worker
    ├── manifest.json    # PWA manifest
    ├── icon-192.png
    └── icon-512.png
```

## 🔒 Sicherheit

- Nur lokaler Zugriff (`0.0.0.0:8766`)
- Zugang über Tailscale (privat, kein öffentlicher Port)
- CORS offen für lokale Entwicklung

## 📝 Designentscheidungen V2

- **Tags als CSV im Hauptfeld** statt eigener Many-to-Many-Tabelle — einfacher, performant für <100 Tags
- **Soft-Delete** mit `deleted_todos` Tabelle statt echtem Löschen — ermöglicht Undo ohne Komplexität
- **Recurring: beim Toggle nächste Instanz erstellen** (nicht beim Öffnen/Cron) — vermeidet Race Conditions, nutzergesteuert
- **Client-Scheduler für Notifications** — kein Server-Cron nötig, solange PWA offen
- **Kein Push-Subscription/Web-Push** — hätte Server + VAPID-Keys benötigt, überdimensioniert für privaten Einzelnutzer
