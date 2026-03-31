# Toyonaka Badminton Bot

LINE-integrated badminton session manager built with Flask, SQLite, and LIFF.

It provides two main views:

- an admin panel for creating and managing sessions
- a member registration page for joining sessions or waiting lists

## Features

- Create, edit, close, reopen, and delete sessions
- View confirmed attendees and waiting lists per session
- Register from LINE using LIFF and the user's LINE profile
- Support multiple players per registration with `player_count`
- Automatic waitlist handling when sessions fill up
- JST-based date and time handling for sessions and registrations

## Tech Stack

- Python 3
- Flask
- SQLite
- LINE LIFF
- Vanilla JavaScript + HTML templates

## Project Structure

```text
app.py              # Flask app entry point
config.py           # Environment variable loading
database.py         # SQLite connection + schema helpers
passenger_wsgi.py   # WSGI entrypoint for Passenger hosting
routes/
	api.py            # REST API used by the LIFF pages
	liff.py           # Serves the admin and member pages
	webhook.py        # LINE webhook handler scaffold
templates/
	admin.html        # Admin LIFF page
	register.html     # Member registration LIFF page
static/style.css    # Shared UI styling
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the project root.

## Environment Variables

```env
LIFF_ID_ADMIN=
LIFF_ID_REGISTER=
ADMIN_SECRET=<admin pass>
BASE_URL=https://yourhost.com # this one actually useless because we do not use webhook anymore and the URL is now infered by flask's url_for() 
DATABASE_PATH=badminton.db
WAITLIST_PRIORITY_HOURS=48
```

### Notes

- `ADMIN_SECRET` is used by the admin page and protected API endpoints.
- `BASE_URL` is used when building the admin shortcut reply in `routes/webhook.py`.
- `DATABASE_PATH` defaults to `badminton.db`.
- `WAITLIST_PRIORITY_HOURS` controls how long a waiting group can block later promotions.

## Run Locally

Start the Flask app:

```bash
python app.py
```

The app initializes the SQLite database on startup by calling `init_db()`.

## Pages

### Admin page

- URL: `/admin`
- Requires the admin secret to unlock the UI
- Uses LIFF to initialize the LINE context
- Lets you manage all sessions, including closed ones
- Shows confirmed and waiting attendees for each session

### Member page

- URL: `/members`
- Initializes LIFF and reads the current LINE profile
- Shows upcoming open sessions only
- Lets members register, join the waitlist, or cancel their own registration

## API Endpoints

All API routes are under `/api`.

### Admin auth

- `GET /api/admin/ping`
  - Requires `X-Admin-Secret: <ADMIN_SECRET>`
  - Used by the admin page to verify the password before unlocking the UI

### Sessions

- `GET /api/sessions`
  - Returns sessions with aggregated attendee counts
  - Query flags:
    - `open=true`
    - `upcoming=true`
    - `line_user_id=...`
- `GET /api/sessions/<id>`
  - Returns one session with its attendee list
- `POST /api/sessions`
  - Creates a session, admin only
- `PUT /api/sessions/<id>`
  - Updates a session, admin only
- `DELETE /api/sessions/<id>`
  - Deletes a session and its registrations, admin only
- `PATCH /api/sessions/<id>/toggle`
  - Toggles `is_open`, admin only

### Attendees

- `GET /api/sessions/<id>/attendees`
  - Returns confirmed and waiting attendees separately
- `POST /api/sessions/<id>/register`
  - Registers a LINE user for a session
- `DELETE /api/sessions/<id>/register`
  - Cancels the user's registration

## Data Model

### `sessions`

- `id`
- `title`
- `venue`
- `date`
- `time_start`
- `time_end`
- `max_players`
- `is_open`
- `created_at`

### `attendees`

- `id`
- `session_id`
- `line_user_id`
- `display_name`
- `player_count`
- `note`
- `registered_at`
- `status`

`status` is either `confirmed` or `waiting`.

## Registration Flow

1. The member page initializes LIFF.
2. The user's LINE profile is read client-side.
3. The page loads upcoming open sessions with the user-specific registration state.
4. When a session is full, new registrations go to the waitlist.
5. When a confirmed slot opens, the app promotes waiting entries in FIFO order.

## Waitlist Rules

- Confirmed registrations use `player_count` to reserve multiple spots.
- Waiting registrations are ordered by `registered_at`.
- If a waiting group does not fit into the remaining space, the app keeps scanning newer waiters.
- Once a waiting group has been waiting longer than `WAITLIST_PRIORITY_HOURS`, it blocks later promotions until it can fit.

## Hosting Notes

- `passenger_wsgi.py` exposes the Flask app as `application` for Passenger deployments.
- HTTPS is required for LIFF.
- The app expects to run in JST for correct date filtering and display.

## Current Notes

- `routes/webhook.py` contains a LINE webhook handler for the admin DM shortcut, but it is not currently registered in `app.py`.
- That webhook module also expects `linebot`-related dependencies, which are not listed in `requirements.txt`.
- Initially, wante to have push notification features to the LINE group whenever a new session is created. But, creating a bot that has messaging API capability is bothersome. Hence, this feature is dropped.

## License

MIT
