# Badminton Attendance App - Project Spec

## Update:

This spec is not maintained after the project is finally live.

## Overview

A LINE-integrated attendance booking app for a badminton circle. Admin manages sessions via LINE bot DM. Users register attendance via a static LIFF link pinned in the LINE group.

---

## Tech Stack

```
Backend  : Python, Flask
Database : SQLite
Frontend : HTML + Vanilla JS (served by Flask, opened as LIFF)
LIFF     : LINE Login channel (2 LIFF IDs)
Hosting  : Self-hosted, HTTPS required
```

---

## LINE Channel Setup

```
LINE Login channel
   ├── LIFF ID #1 (admin)    → https://yourhost.com/liff/admin
   └── LIFF ID #2 (register) → https://yourhost.com/liff/register
```

---

## Environment Variables

```
LIFF_ID_ADMIN=              # LIFF ID for admin page
LIFF_ID_REGISTER=           # LIFF ID for register page
ADMIN_SECRET=toyonaka-admin     # Trigger string for admin panel
BASE_URL=                   # e.g. https://yourhost.com
```

---

## Project Structure

```
badminton-bot/
│
├── app.py                  # Flask app entry point
├── config.py               # Loads env variables
├── database.py             # SQLite init + query helpers
├── requirements.txt
├── .env
│
├── routes/
│   ├── api.py              # REST API endpoints for LIFF
│   └── liff.py             # Serves LIFF HTML pages
│
├── templates/
│   ├── admin.html          # Admin LIFF page
│   └── register.html       # User registration LIFF page
│
└── static/
    └── style.css
```

---

## Database Schema

```sql
CREATE TABLE sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    venue       TEXT,
    date        TEXT,           -- YYYY-MM-DD (local time, assumed JST)
    time_start  TEXT,           -- HH:MM      (local time, assumed JST)
    time_end    TEXT,           -- HH:MM      (local time, assumed JST)
    max_players INTEGER DEFAULT 20,
    is_open     INTEGER DEFAULT 1,  -- 1=open, 0=closed
    created_at  TEXT            -- ISO datetime
);

CREATE TABLE attendees (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER REFERENCES sessions(id),
    line_user_id    TEXT NOT NULL,
    display_name    TEXT,
    player_count    INTEGER DEFAULT 1,  -- account for +1, +2, etc
    note            TEXT,
    registered_at   TEXT                -- ISO datetime
);
```

---

## API Endpoints (api.py)

### Sessions

```
GET    /api/sessions                  # List all open sessions
GET    /api/sessions?upcoming=true    # Filter to sessions with date >= today (recommended for register page)
GET    /api/sessions/<id>             # Get single session + attendee list
POST   /api/sessions                  # Create session (admin)
PUT    /api/sessions/<id>             # Edit session (admin)
DELETE /api/sessions/<id>             # Delete session (admin)
PATCH  /api/sessions/<id>/toggle      # Toggle is_open (admin)
```

### Attendees

```
GET    /api/sessions/<id>/attendees   # Get attendee list for session
POST   /api/sessions/<id>/register    # Register attendance
DELETE /api/sessions/<id>/register    # Cancel registration
```

### Request/Response Format

```json
// POST /api/sessions body
{
    "title": "Badminton Saturday",
    "venue": "Sport Hall A",
    "date": "2025-06-14",
    "time_start": "09:00",
    "time_end": "12:00",
    "max_players": 20
}

// POST /api/sessions/<id>/register body
{
    "line_user_id": "Uxxxxx",
    "display_name": "Budi",
    "player_count": 2,
    "note": "bringing my wife"
}

// GET /api/sessions response
[
    {
        "id": 1,
        "title": "Badminton Saturday",
        "venue": "Sport Hall A",
        "date": "2025-06-14",
        "time_start": "09:00",
        "time_end": "12:00",
        "max_players": 20,
        "is_open": 1,
        "total_players": 12    // sum of all attendees player_count
    }
]
```

### Admin API Protection

```
All admin API calls (POST/PUT/DELETE/PATCH on /api/sessions)
must include header:
    X-Admin-Secret: <value of ADMIN_SECRET env var>

Flow:
1. Admin opens /liff/admin directly (bookmark the link once)
2. Page shows a password prompt on load
3. Admin enters password; page calls GET /api/admin/ping to verify
4. If correct, adminSecret is stored in memory and the admin UI unlocks
5. All subsequent fetch() calls attach it as the X-Admin-Secret header

Password never appears in the URL or browser history.
No bot or external step required.
```

---

## LIFF Pages

### Admin Page (/liff/admin)

```
- Initialize LIFF SDK on load
- Display list of ALL sessions (open and closed)
- Actions per session:
    - Toggle open/closed
    - Edit session details
    - Delete session
- Button to create new session
- Create/Edit form fields:
    - Title (text)
    - Venue (text)
    - Date (date picker)
    - Time Start (time picker)
    - Time End (time picker)
    - Max Players (number)
- Show attendee list per session (name, player count, note)
```

### User Registration Page (/liff/register)

```
- Initialize LIFF SDK on load
- Fetch LINE user profile (userId, displayName) via LIFF SDK
- Display list of OPEN sessions only
- Per session show:
    - Title, venue, date, time
    - Current total registered / max players
    - "Full" badge if total_players >= max_players
    - [Register] button (disabled if full or already registered)
    - [Cancel] button if user already registered for this session
- Registration form (shown inline or as modal):
    - Display name (auto-filled from LINE profile, read-only)
    - Player count (select: 1 / 2 / 3 / 4)
    - Note (text, optional)
    - [Confirm] button
- On successful register/cancel, refresh session data
```

---

## Requirements.txt

```
flask
python-dotenv
requests
```

---

## Key Constraints

```
- HTTPS is mandatory (LINE LIFF requirement)
- LIFF SDK must be initialized before accessing LINE profile
- line_user_id must be fetched client-side via LIFF SDK, not user-inputted
- A single line_user_id can only have ONE registration per session
  (but player_count handles the +1/+2 use case)
- Static link /liff/register never changes (pin once in group)
- All date/time values are stored and interpreted as JST (UTC+9).
  Ensure the server's local time is set to JST, or apply explicit
  timezone handling when comparing dates (e.g. the ?upcoming=true filter)
```

## Known Limitations

```
- line_user_id trust gap: the server accepts line_user_id from the request
  body and cannot verify it belongs to the actual requester. A malicious
  user could spoof another user's ID via DevTools. The proper fix is to
  send the LIFF access token to the server and verify it against LINE's
  /v2/profile API, but this adds complexity. Accepted trade-off for an
  internal club tool.

```
