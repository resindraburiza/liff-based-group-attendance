import logging
import sys
from flask import Blueprint, request, jsonify
from functools import wraps
from database import get_db, now_jst, today_jst
from config import ADMIN_SECRET, WAITLIST_PRIORITY_HOURS

# print(f'api blueprint loaded, ADMIN_SECRET repr={ADMIN_SECRET}')

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ─── Auth decorator ───────────────────────────────────────────────────────────

def require_admin(f):
    """Decorator that rejects requests missing a valid X-Admin-Secret header with a 401."""
    @wraps(f)
    def decorated(*args, **kwargs):
        secret = request.headers.get('X-Admin-Secret', '')
        print(f'require_admin: received={secret}  expected={ADMIN_SECRET}')
        if secret != ADMIN_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


# ─── Admin ping ──────────────────────────────────────────────────────────────

@api_bp.route('/admin/ping', methods=['GET'])
@require_admin
def admin_ping():
    """Used by admin.html to verify the password before unlocking the UI."""
    return jsonify({'ok': True})


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _session_to_dict(row, line_user_id=None):
    """Convert a sessions DB row (with total_players / waiting_count) to a dict.
    Optionally includes my_registration (with waiting_position) for the given line_user_id."""
    d = dict(row)
    if line_user_id:
        conn = get_db()
        reg = conn.execute(
            'SELECT * FROM attendees WHERE session_id = ? AND line_user_id = ?',
            (d['id'], line_user_id),
        ).fetchone()
        if reg:
            reg_dict = dict(reg)
            if reg_dict.get('status') == 'waiting':
                # Calculate position in waiting list (1-based, ordered by registered_at)
                pos = conn.execute(
                    '''SELECT COUNT(*) FROM attendees
                       WHERE session_id = ? AND status = ? AND registered_at <= ?''',
                    (d['id'], 'waiting', reg_dict['registered_at']),
                ).fetchone()[0]
                reg_dict['waiting_position'] = pos
            d['my_registration'] = reg_dict
        else:
            d['my_registration'] = None
        conn.close()
    return d


# ─── Sessions ─────────────────────────────────────────────────────────────────

@api_bp.route('/sessions', methods=['GET'])
def list_sessions():
    """GET /api/sessions
    Query params:
      open=true       → only open sessions
      upcoming=true   → only sessions with date >= today (JST)
      line_user_id=U… → include my_registration per session
    """
    open_only     = request.args.get('open') == 'true'
    upcoming_only = request.args.get('upcoming') == 'true'
    line_user_id  = request.args.get('line_user_id')

    query = '''
        SELECT s.*,
               COALESCE(SUM(CASE WHEN a.status = 'confirmed' THEN a.player_count ELSE 0 END), 0) AS total_players,
               COALESCE(SUM(CASE WHEN a.status = 'waiting'   THEN 1            ELSE 0 END), 0) AS waiting_count
        FROM sessions s
        LEFT JOIN attendees a ON a.session_id = s.id
    '''
    conditions, params = [], []

    if open_only:
        conditions.append('s.is_open = 1')
    if upcoming_only:
        conditions.append('s.date >= ?')
        params.append(today_jst())

    if conditions:
        query += ' WHERE ' + ' AND '.join(conditions)
    query += ' GROUP BY s.id ORDER BY s.date ASC, s.time_start ASC'

    conn = get_db()
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return jsonify([_session_to_dict(r, line_user_id) for r in rows])


@api_bp.route('/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id):
    """Return a single session by ID, including its full attendee list."""
    conn = get_db()
    row = conn.execute('''
        SELECT s.*,
               COALESCE(SUM(CASE WHEN a.status = 'confirmed' THEN a.player_count ELSE 0 END), 0) AS total_players,
               COALESCE(SUM(CASE WHEN a.status = 'waiting'   THEN 1            ELSE 0 END), 0) AS waiting_count
        FROM sessions s
        LEFT JOIN attendees a ON a.session_id = s.id
        WHERE s.id = ?
        GROUP BY s.id
    ''', (session_id,)).fetchone()

    if not row:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404

    attendees = conn.execute(
        'SELECT * FROM attendees WHERE session_id = ? ORDER BY registered_at ASC',
        (session_id,),
    ).fetchall()
    conn.close()

    result = _session_to_dict(row)
    result['attendees'] = [dict(a) for a in attendees]
    return jsonify(result)


@api_bp.route('/sessions', methods=['POST'])
@require_admin
def create_session():
    """Create a new session from JSON body; requires admin auth. Returns the new session ID."""
    data = request.get_json()
    if not data or not data.get('title'):
        return jsonify({'error': 'title is required'}), 400

    conn = get_db()
    cursor = conn.execute('''
        INSERT INTO sessions (title, venue, date, time_start, time_end, max_players, is_open, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?)
    ''', (
        data.get('title'),
        data.get('venue'),
        data.get('date'),
        data.get('time_start'),
        data.get('time_end'),
        data.get('max_players', 20),
        now_jst(),
    ))
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return jsonify({'id': session_id, 'message': 'Session created'}), 201


@api_bp.route('/sessions/<int:session_id>', methods=['PUT'])
@require_admin
def update_session(session_id):
    """Update an existing session's fields from JSON body; triggers a waitlist rebalance."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db()
    conn.execute('''
        UPDATE sessions
        SET title=?, venue=?, date=?, time_start=?, time_end=?, max_players=?
        WHERE id=?
    ''', (
        data.get('title'),
        data.get('venue'),
        data.get('date'),
        data.get('time_start'),
        data.get('time_end'),
        data.get('max_players', 20),
        session_id,
    ))
    conn.commit()
    _rebalance_session(session_id, conn)
    conn.close()
    return jsonify({'message': 'Session updated'})


@api_bp.route('/sessions/<int:session_id>', methods=['DELETE'])
@require_admin
def delete_session(session_id):
    """Delete a session and all its attendees permanently."""
    conn = get_db()
    conn.execute('DELETE FROM attendees WHERE session_id = ?', (session_id,))
    conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Session deleted'})


@api_bp.route('/sessions/<int:session_id>/toggle', methods=['PATCH'])
@require_admin
def toggle_session(session_id):
    """Flip a session's is_open flag; triggers a waitlist rebalance when re-opened."""
    conn = get_db()
    conn.execute(
        'UPDATE sessions SET is_open = CASE WHEN is_open = 1 THEN 0 ELSE 1 END WHERE id = ?',
        (session_id,),
    )
    conn.commit()
    new_state = conn.execute('SELECT is_open FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if new_state and new_state['is_open']:
        _rebalance_session(session_id, conn)
    conn.close()
    return jsonify({'message': 'Toggled'})


# ─── Waitlist promotion ───────────────────────────────────────────────────────

def _promote_from_waitlist(session_id, conn):
    """Scan the waiting list in FIFO order after a confirmed slot is freed.
    - If a waiter fits in the remaining slots: promote to confirmed, keep scanning.
    - If a waiter doesn't fit AND has been waiting > WAITLIST_PRIORITY_HOURS: hard stop.
    - If a waiter doesn't fit AND is still fresh: skip them, continue scanning.
    """
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone(timedelta(hours=9)))
    cutoff_delta = timedelta(hours=WAITLIST_PRIORITY_HOURS)

    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        return

    waiters = conn.execute(
        "SELECT * FROM attendees WHERE session_id = ? AND status = 'waiting' ORDER BY registered_at ASC",
        (session_id,),
    ).fetchall()

    if not waiters:
        return

    for waiter in waiters:
        free_slots = session['max_players'] - conn.execute(
            "SELECT COALESCE(SUM(player_count), 0) FROM attendees WHERE session_id = ? AND status = 'confirmed'",
            (session_id,),
        ).fetchone()[0]

        if free_slots <= 0:
            break

        if waiter['player_count'] <= free_slots:
            conn.execute(
                "UPDATE attendees SET status = 'confirmed' WHERE id = ?",
                (waiter['id'],),
            )
            conn.commit()
            print(f"Promoted attendee {waiter['id']} from waiting to confirmed for session {session_id}")
        else:
            # Waiter doesn't fit — check if they've been waiting long enough to block
            try:
                registered_at = datetime.fromisoformat(waiter['registered_at'])
                if registered_at.tzinfo is None:
                    registered_at = registered_at.replace(tzinfo=timezone(timedelta(hours=9)))
            except (ValueError, TypeError):
                registered_at = now  # fallback: treat as fresh

            waited = now - registered_at
            if waited >= cutoff_delta:
                print(
                    f"Waiter {waiter['id']} has been waiting {waited.total_seconds() / 3600:.2f} (>= {WAITLIST_PRIORITY_HOURS}h threshold) — blocking further promotions"
                )
                break  # Hard stop: stale group has priority, nobody behind them gets promoted
            # else: fresh group, skip and continue scanning


def _rebalance_session(session_id, conn):
    """Rebalance confirmed/waiting lists after max_players changes or a session is re-opened.
    - If confirmed total > max_players: demote the most-recently-registered confirmed attendees
      to waiting until the total fits.
    - Then promote from the waiting list to fill any newly available slots.
    """
    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        return

    max_players = session['max_players']

    # Step 1: Demote excess confirmed attendees (most recently registered first)
    confirmed = conn.execute(
        "SELECT * FROM attendees WHERE session_id = ? AND status = 'confirmed' ORDER BY registered_at DESC",
        (session_id,),
    ).fetchall()

    confirmed_total = sum(a['player_count'] for a in confirmed)

    for attendee in confirmed:
        if confirmed_total <= max_players:
            break
        conn.execute(
            "UPDATE attendees SET status = 'waiting' WHERE id = ?",
            (attendee['id'],),
        )
        confirmed_total -= attendee['player_count']
        print(f"Demoted attendee {attendee['id']} from confirmed to waiting for session {session_id}")

    conn.commit()

    # Step 2: Promote from waiting list to fill remaining free slots
    _promote_from_waitlist(session_id, conn)


# ─── Attendees ────────────────────────────────────────────────────────────────

@api_bp.route('/sessions/<int:session_id>/attendees', methods=['GET'])
def list_attendees(session_id):
    """Return confirmed and waiting attendees for a session as two separate lists."""
    conn = get_db()
    confirmed = conn.execute(
        "SELECT * FROM attendees WHERE session_id = ? AND status = 'confirmed' ORDER BY registered_at ASC",
        (session_id,),
    ).fetchall()
    waiting = conn.execute(
        "SELECT * FROM attendees WHERE session_id = ? AND status = 'waiting' ORDER BY registered_at ASC",
        (session_id,),
    ).fetchall()
    conn.close()
    return jsonify({
        'confirmed': [dict(r) for r in confirmed],
        'waiting':   [dict(r) for r in waiting],
    })


@api_bp.route('/sessions/<int:session_id>/cancellations', methods=['GET'])
@require_admin
def list_cancellations(session_id):
    """Return all cancellation records for a session, ordered by cancellation time."""
    print('cancelation')
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM cancellations WHERE session_id = ? ORDER BY cancelled_at ASC',
        (session_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api_bp.route('/sessions/<int:session_id>/register', methods=['POST'])
def register(session_id):
    """Register a LINE user for a session, placing them on the waitlist if the session is full."""
    data = request.get_json()
    line_user_id = data.get('line_user_id') if data else None

    if not line_user_id:
        return jsonify({'error': 'line_user_id is required'}), 400

    conn = get_db()
    conn.isolation_level = None  # manual transaction mode for this connection
    conn.execute('BEGIN IMMEDIATE')  # blocks other writers for the duration

    session = conn.execute(
        'SELECT * FROM sessions WHERE id = ?', (session_id,)
    ).fetchone()
    if not session:
        conn.close()  # uncommitted transaction auto-rolls back on close
        return jsonify({'error': 'Session not found'}), 404
    if not session['is_open']:
        conn.close()
        return jsonify({'error': 'Session is closed'}), 400

    existing = conn.execute(
        'SELECT id FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already registered'}), 409

    player_count = data.get('player_count', 1)
    confirmed_total = conn.execute(
        "SELECT COALESCE(SUM(player_count), 0) AS total FROM attendees WHERE session_id = ? AND status = 'confirmed'",
        (session_id,),
    ).fetchone()['total']

    if confirmed_total + player_count > session['max_players']:
        # Not enough confirmed slots — add to waiting list
        conn.execute(
            'DELETE FROM cancellations WHERE session_id = ? AND line_user_id = ?',
            (session_id, line_user_id),
        )
        reg_time = now_jst()
        conn.execute('''
            INSERT INTO attendees (session_id, line_user_id, display_name, player_count, note, registered_at, status)
            VALUES (?, ?, ?, ?, ?, ?, 'waiting')
        ''', (
            session_id,
            line_user_id,
            data.get('display_name'),
            player_count,
            data.get('note'),
            reg_time,
        ))
        conn.commit()
        # Calculate waiting position
        position = conn.execute(
            "SELECT COUNT(*) FROM attendees WHERE session_id = ? AND status = 'waiting'",
            (session_id,),
        ).fetchone()[0]
        conn.close()
        return jsonify({'message': 'Added to waiting list', 'status': 'waiting', 'position': position}), 201

    conn.execute(
        'DELETE FROM cancellations WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    )
    conn.execute('''
        INSERT INTO attendees (session_id, line_user_id, display_name, player_count, note, registered_at, status)
        VALUES (?, ?, ?, ?, ?, ?, 'confirmed')
    ''', (
        session_id,
        line_user_id,
        data.get('display_name'),
        player_count,
        data.get('note'),
        now_jst(),
    ))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Registered successfully', 'status': 'confirmed'}), 201


@api_bp.route('/sessions/<int:session_id>/register', methods=['PUT'])
def update_registration(session_id):
    """Update player_count and/or note for an existing registration; rebalances the session."""
    data = request.get_json()
    line_user_id = data.get('line_user_id') if data else None

    if not line_user_id:
        return jsonify({'error': 'line_user_id is required'}), 400

    conn = get_db()
    conn.isolation_level = None
    conn.execute('BEGIN IMMEDIATE')

    session = conn.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
    if not session:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    if not session['is_open']:
        conn.close()
        return jsonify({'error': 'Session is closed'}), 400

    existing = conn.execute(
        'SELECT * FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    ).fetchone()
    if not existing:
        conn.close()
        return jsonify({'error': 'Registration not found'}), 404

    player_count = data.get('player_count', existing['player_count'])
    note = data.get('note', existing['note'])

    conn.execute(
        'UPDATE attendees SET player_count = ?, note = ? WHERE session_id = ? AND line_user_id = ?',
        (player_count, note, session_id, line_user_id),
    )
    conn.commit()
    _rebalance_session(session_id, conn)
    conn.close()
    return jsonify({'message': 'Registration updated'})


@api_bp.route('/sessions/<int:session_id>/register', methods=['DELETE'])
def cancel_registration(session_id):
    """Cancel a LINE user's registration and promote the next eligible waiter if a confirmed slot is freed."""
    data = request.get_json()
    line_user_id = data.get('line_user_id') if data else None

    if not line_user_id:
        return jsonify({'error': 'line_user_id is required'}), 400

    conn = get_db()
    conn.isolation_level = None  # manual transaction mode for this connection
    conn.execute('BEGIN IMMEDIATE')  # blocks other writers for the duration

    # Check whether we're cancelling a confirmed or waiting registration
    existing = conn.execute(
        'SELECT status FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    ).fetchone()
    if not existing:
        conn.close()  # uncommitted transaction auto-rolls back on close
        return jsonify({'error': 'Registration not found'}), 404

    was_confirmed = existing['status'] == 'confirmed'

    # Fetch full row before deleting so we can log it
    full_row = conn.execute(
        'SELECT * FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    ).fetchone()

    conn.execute('''
        INSERT INTO cancellations (session_id, line_user_id, display_name, player_count, note, was_status, cancelled_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        session_id,
        line_user_id,
        full_row['display_name'],
        full_row['player_count'],
        full_row['note'],
        full_row['status'],
        now_jst(),
    ))

    conn.execute(
        'DELETE FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    )
    conn.commit()

    # Only run promotion if a confirmed slot was freed
    if was_confirmed:
        _promote_from_waitlist(session_id, conn)

    conn.close()
    return jsonify({'message': 'Registration cancelled'})
