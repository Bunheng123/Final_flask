"""
Authentication and Authorization Helpers.
Provides unified user session access, route protection decorators, and URL validation.
"""
from functools import wraps
from urllib.parse import urlparse
from flask import session, request, redirect, url_for, abort, g
from models.user import User

def is_safe_next_url(target: str) -> bool:
    """
    Validates that a redirect target URL is safe and internal.
    Rejects external URLs, scheme-relative URLs (//), and javascript/data schemes.
    """
    if not target:
        return False
    target = target.strip()
    if not target.startswith('/') or target.startswith('//'):
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc

def current_user() -> User | None:
    """
    Returns the currently authenticated User model instance, or None if anonymous.
    Caches the lookup on Flask request context `g`.
    """
    if not session.get('is_login') or not session.get('user_id'):
        return None

    if not hasattr(g, '_current_user'):
        user_id = session.get('user_id')
        g._current_user = User.query.get(user_id)
    return g._current_user

def login_required(f):
    """
    Decorator requiring an authenticated session.
    Redirects unauthenticated users to /login?next=<requested_url>.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_login') or not session.get('user_id'):
            next_url = request.full_path if request.query_string else request.path
            if next_url.endswith('?'):
                next_url = next_url[:-1]
            return redirect(url_for('front_bp.login', next=next_url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """
    Decorator requiring an authenticated user with role == 'admin'.
    If unauthenticated, redirects to /login?next=...
    If authenticated but role != 'admin', aborts with HTTP 403 Forbidden.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_login') or not session.get('user_id'):
            next_url = request.full_path if request.query_string else request.path
            if next_url.endswith('?'):
                next_url = next_url[:-1]
            return redirect(url_for('front_bp.login', next=next_url))

        role = session.get('role') or session.get('user_role')
        if role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# Aliases for storefront and workstream compatibility
customer_required = login_required
current_customer = current_user
