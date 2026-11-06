from flask import render_template, request, redirect, url_for, session, abort
from front import front_bp
from extensions import limiter
from services.auth_service import (
    authenticate,
    register_user,
    logout_user,
    get_post_login_redirect,
    login_required,
)

@front_bp.route('/login', methods=['GET', 'POST'], endpoint='login')
@limiter.limit("5 per minute", methods=["POST"])
def login():
    """
    Canonical Login route.
    GET: Displays login form.
    POST: Authenticates credentials, clears session, and redirects appropriately.
    """
    next_url = request.args.get('next')
    if request.method == 'POST':
        identifier = request.form.get('email') or request.form.get('username')
        password = request.form.get('password')
        form_next = request.form.get('next') or next_url

        success, error_msg, user = authenticate(identifier, password)
        if success:
            return get_post_login_redirect(user, form_next)

        return render_template('login.html', error=error_msg, next=form_next), 400

    return render_template('login.html', next=next_url)

@front_bp.route('/register', methods=['GET', 'POST'], endpoint='register')
@limiter.limit("5 per minute", methods=["POST"])
def register():
    """
    Canonical Register route.
    GET: Displays registration form.
    POST: Creates user with role='user', auto-logs in, and redirects.
    """
    next_url = request.args.get('next')
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        form_next = request.form.get('next') or next_url

        success, error_msg, user = register_user(username, email, password, confirm_password)
        if success:
            return get_post_login_redirect(user, form_next)

        return render_template('register.html', error=error_msg, next=form_next), 400

    return render_template('register.html', next=next_url)

@front_bp.post('/logout', endpoint='logout')
def logout():
    """
    POST Logout route with CSRF protection.
    Clears session and redirects to storefront home.
    """
    logout_user()
    return redirect(url_for('front_bp.home'))

@front_bp.route('/forgot-password', methods=['GET', 'POST'], endpoint='forgot_password')
def forgot_password():
    """
    Stub: Forgot password request flow.
    """
    if request.method == 'POST':
        abort(501)
    raise NotImplementedError("TODO: Workstream B - Forgot Password")

@front_bp.route('/reset-password/<token>', methods=['GET', 'POST'], endpoint='reset_password')
def reset_password(token: str):
    """
    Stub: Password reset with token flow.
    """
    if request.method == 'POST':
        abort(501)
    raise NotImplementedError("TODO: Workstream B - Reset Password with Token")
