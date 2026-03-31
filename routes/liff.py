from flask import Blueprint, render_template
from config import LIFF_ID_ADMIN, LIFF_ID_REGISTER

liff_bp = Blueprint('liff', __name__)


@liff_bp.route('/admin')
def admin():
    return render_template('admin.html', liff_id=LIFF_ID_ADMIN)


@liff_bp.route('/members')
def register():
    return render_template('register.html', liff_id=LIFF_ID_REGISTER)
