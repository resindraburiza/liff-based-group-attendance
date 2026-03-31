import sqlite3
from datetime import datetime, timezone, timedelta
from config import DATABASE_PATH

JST = timezone(timedelta(hours=9))


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            venue       TEXT,
            date        TEXT,           -- YYYY-MM-DD (JST)
            time_start  TEXT,           -- HH:MM (JST)
            time_end    TEXT,           -- HH:MM (JST)
            max_players INTEGER DEFAULT 20,
            is_open     INTEGER DEFAULT 1,
            created_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS attendees (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER REFERENCES sessions(id),
            line_user_id    TEXT NOT NULL,
            display_name    TEXT,
            player_count    INTEGER DEFAULT 1,
            note            TEXT,
            registered_at   TEXT,
            status          TEXT NOT NULL DEFAULT 'confirmed'
        );

        CREATE TABLE IF NOT EXISTS cancellations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER REFERENCES sessions(id),
            line_user_id    TEXT NOT NULL,
            display_name    TEXT,
            player_count    INTEGER DEFAULT 1,
            note            TEXT,
            was_status      TEXT NOT NULL,  -- 'confirmed' or 'waiting'
            cancelled_at    TEXT NOT NULL
        );
    ''')
    conn.commit()

    # Migration: add 'status' column to existing attendees tables that predate this feature
    existing_columns = [row[1] for row in conn.execute("PRAGMA table_info(attendees)").fetchall()]
    if 'status' not in existing_columns:
        conn.execute("ALTER TABLE attendees ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'")
        conn.commit()

    # Migration: create cancellations table if it didn't exist before this feature
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cancellations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER REFERENCES sessions(id),
            line_user_id    TEXT NOT NULL,
            display_name    TEXT,
            player_count    INTEGER DEFAULT 1,
            note            TEXT,
            was_status      TEXT NOT NULL,
            cancelled_at    TEXT NOT NULL
        )
    ''')
    conn.commit()

    conn.close()


def now_jst() -> str:
    """Return current datetime as ISO string in JST."""
    return datetime.now(JST).isoformat()


def today_jst() -> str:
    """Return today's date as YYYY-MM-DD string in JST."""
    return datetime.now(JST).strftime('%Y-%m-%d')
