from flask import Blueprint, render_template
from config import LIFF_ID_ADMIN, LIFF_ID_REGISTER, LIFF_ID_REGISTER_DEVEL

liff_bp = Blueprint('liff', __name__)


@liff_bp.route('/admin')
def admin():
    return render_template('admin.html', liff_id=LIFF_ID_ADMIN)


@liff_bp.route('/members')
def register():
    return render_template('register.html', liff_id=LIFF_ID_REGISTER)

@liff_bp.route('/members_devel')
def register_devel():
    return render_template('register_devel.html', liff_id=LIFF_ID_REGISTER_DEVEL)
