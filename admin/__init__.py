from flask import Blueprint, session, redirect, url_for, request, abort

admin_bp = Blueprint('admin_bp', __name__, template_folder='templates')

@admin_bp.before_request
def require_admin_login():
    if request.endpoint in ('admin_bp.login', 'admin_bp.register', 'static'):
        return None

    if not session.get('is_login'):
        next_url = request.full_path if request.query_string else request.path
        if next_url.endswith('?'):
            next_url = next_url[:-1]
        return redirect(url_for('front_bp.login', next=next_url))

    # Populate profile_image and user_role if missing in existing session
    if session.get('user_id') and not session.get('profile_image'):
        from api.user import get_user_by_id
        from helpers.upload import get_thumb_name
        u = get_user_by_id(session['user_id'])
        if u:
            session['username'] = u['username']
            session['email'] = u['email']
            session['role'] = u.get('role', 'user')
            session['user_role'] = u.get('role', 'user')
            prof = u.get('profile')
            if prof:
                session['profile_image'] = f"images/user/{get_thumb_name(prof)}"
                session['profile'] = prof
            else:
                session['profile_image'] = "images/no-image.jpg"
                session['profile'] = None

    if session.get('role') != 'admin' and session.get('user_role') != 'admin':
        abort(403)

from admin import dashboard, user, auth, block_log, products, orders, coupons, reports, variants, reviews, brand

