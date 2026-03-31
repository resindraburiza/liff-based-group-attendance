import logging
import sys
from flask import Blueprint, request, jsonify
from functools import wraps
from database import get_db, now_jst, today_jst
from config import ADMIN_SECRET

# stderr → Passenger captures this in the application error log
# stdout (print) is NOT captured — always use logger or sys.stderr here
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('toyonaka.api')
logger.debug('api blueprint loaded, ADMIN_SECRET repr=%r', ADMIN_SECRET)

api_bp = Blueprint('api', __name__, url_prefix='/api')


# ─── Auth decorator ───────────────────────────────────────────────────────────

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        secret = request.headers.get('X-Admin-Secret', '')
        logger.debug('require_admin: received=%r  expected=%r  match=%s',
                     secret, ADMIN_SECRET, secret == ADMIN_SECRET)
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
    """Convert a sessions DB row (with total_players) to a dict.
    Optionally includes my_registration for the given line_user_id."""
    d = dict(row)
    if line_user_id:
        conn = get_db()
        reg = conn.execute(
            'SELECT * FROM attendees WHERE session_id = ? AND line_user_id = ?',
            (d['id'], line_user_id),
        ).fetchone()
        conn.close()
        d['my_registration'] = dict(reg) if reg else None
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
        SELECT s.*, COALESCE(SUM(a.player_count), 0) AS total_players
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
    conn = get_db()
    row = conn.execute('''
        SELECT s.*, COALESCE(SUM(a.player_count), 0) AS total_players
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
    conn.close()
    return jsonify({'message': 'Session updated'})


@api_bp.route('/sessions/<int:session_id>', methods=['DELETE'])
@require_admin
def delete_session(session_id):
    conn = get_db()
    conn.execute('DELETE FROM attendees WHERE session_id = ?', (session_id,))
    conn.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Session deleted'})


@api_bp.route('/sessions/<int:session_id>/toggle', methods=['PATCH'])
@require_admin
def toggle_session(session_id):
    conn = get_db()
    conn.execute(
        'UPDATE sessions SET is_open = CASE WHEN is_open = 1 THEN 0 ELSE 1 END WHERE id = ?',
        (session_id,),
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Toggled'})


# ─── Attendees ────────────────────────────────────────────────────────────────

@api_bp.route('/sessions/<int:session_id>/attendees', methods=['GET'])
def list_attendees(session_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM attendees WHERE session_id = ? ORDER BY registered_at ASC',
        (session_id,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@api_bp.route('/sessions/<int:session_id>/register', methods=['POST'])
def register(session_id):
    data = request.get_json()
    line_user_id = data.get('line_user_id') if data else None

    if not line_user_id:
        return jsonify({'error': 'line_user_id is required'}), 400

    conn = get_db()

    session = conn.execute(
        'SELECT * FROM sessions WHERE id = ?', (session_id,)
    ).fetchone()
    if not session:
        conn.close()
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
    total = conn.execute(
        'SELECT COALESCE(SUM(player_count), 0) AS total FROM attendees WHERE session_id = ?',
        (session_id,),
    ).fetchone()['total']
    if total + player_count > session['max_players']:
        conn.close()
        return jsonify({'error': 'Not enough spots remaining'}), 400

    conn.execute('''
        INSERT INTO attendees (session_id, line_user_id, display_name, player_count, note, registered_at)
        VALUES (?, ?, ?, ?, ?, ?)
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
    return jsonify({'message': 'Registered successfully'}), 201


@api_bp.route('/sessions/<int:session_id>/register', methods=['DELETE'])
def cancel_registration(session_id):
    data = request.get_json()
    line_user_id = data.get('line_user_id') if data else None

    if not line_user_id:
        return jsonify({'error': 'line_user_id is required'}), 400

    conn = get_db()
    result = conn.execute(
        'DELETE FROM attendees WHERE session_id = ? AND line_user_id = ?',
        (session_id, line_user_id),
    )
    conn.commit()
    conn.close()

    if result.rowcount == 0:
        return jsonify({'error': 'Registration not found'}), 404
    return jsonify({'message': 'Registration cancelled'})
