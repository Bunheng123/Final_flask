from functools import wraps
from flask import session, redirect, url_for, request, abort
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from models.user import User
from helpers.upload import get_thumb_name

def is_safe_redirect_url(target: str) -> bool:
    """Validate that the redirect target is a safe relative path."""
    if not target:
        return False
    # Must start with single slash, not double slash or backslash
    if not target.startswith('/') or target.startswith('//') or target.startswith('/\\'):
        return False
    return True

def login_user(user: User):
    """
    Log in a user into the session.
    Always clears the session first to prevent session fixation.
    """
    session.clear()
    session['is_login'] = True
    session['user_id'] = user.id
    session['username'] = user.username
    session['email'] = user.email
    session['role'] = user.role or 'user'
    session['user_role'] = user.role or 'user'

    if user.profile:
        session['profile_image'] = f"images/user/{get_thumb_name(user.profile)}"
        session['profile'] = user.profile
    else:
        session['profile_image'] = "images/no-image.jpg"
        session['profile'] = None

def logout_user():
    """Clear session data on logout."""
    session.clear()

def authenticate(email_or_username: str, password: str) -> tuple[bool, str, User]:
    """
    Normalize email, verify password hash, reject inactive users,
    and return ONE generic error on failure.
    """
    identifier = (email_or_username or '').strip().lower()
    if not identifier or not password:
        return False, "Invalid email or password", None

    user = User.query.filter(
        (db.func.lower(User.email) == identifier) |
        (db.func.lower(User.username) == identifier)
    ).first()

    if not user:
        return False, "Invalid email or password", None

    if not check_password_hash(user.password, password):
        return False, "Invalid email or password", None

    if getattr(user, 'is_active', True) is False:
        return False, "Your account is inactive. Please contact support.", None

    login_user(user)
    return True, None, user

def register_user(username: str, email: str, password: str, confirm_password: str) -> tuple[bool, str, User]:
    """
    Register a new user account.
    The role is ALWAYS 'user' and is NEVER read from the client request.
    Enforces minimum 8 characters password length and duplicate email validation.
    Auto-logs in the user upon successful registration.
    """
    clean_username = (username or '').strip()
    clean_email = (email or '').strip().lower()

    if not clean_username or not clean_email or not password or not confirm_password:
        return False, "All fields are required", None

    if len(password) < 8:
        return False, "Password must be at least 8 characters long", None

    if password != confirm_password:
        return False, "Passwords do not match", None

    # Duplicate email check
    if User.query.filter(db.func.lower(User.email) == clean_email).first():
        return False, "An account with this email already exists", None

    # Duplicate username check
    if User.query.filter(db.func.lower(User.username) == clean_username.lower()).first():
        return False, "Username is already taken", None

    new_user = User(
        username=clean_username,
        email=clean_email,
        password=generate_password_hash(password),
        role='user',
        profile=None
    )
    db.session.add(new_user)
    db.session.commit()

    # Auto-login after registration
    login_user(new_user)
    return True, None, new_user

def get_post_login_redirect(user: User, next_url: str = None):
    """
    Determine post-login landing destination:
    - role 'admin': validated next if present, otherwise admin dashboard
    - role 'user': validated next if present AND not an /admin URL, otherwise storefront home
    """
    if user.role == 'admin':
        if is_safe_redirect_url(next_url):
            return redirect(next_url)
        return redirect(url_for('admin_bp.dashboard'))
    else:
        if is_safe_redirect_url(next_url) and not next_url.startswith('/admin'):
            return redirect(next_url)
        return redirect(url_for('front_bp.home'))

def login_required(f):
    """Decorator ensuring a user session is authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_login'):
            next_url = request.full_path if request.query_string else request.path
            if next_url.endswith('?'):
                next_url = next_url[:-1]
            return redirect(url_for('front_bp.login', next=next_url))
        return f(*args, **kwargs)
    return decorated_function

def create_admin_user(username: str, email: str, password: str) -> User:
    """Helper to create an admin account (used by CLI or admin CRUD)."""
    clean_username = (username or '').strip()
    clean_email = (email or '').strip().lower()

    if not clean_username or not clean_email or not password:
        raise ValueError("Username, email, and password are required")

    existing = User.query.filter(
        (db.func.lower(User.email) == clean_email) |
        (db.func.lower(User.username) == clean_username.lower())
    ).first()
    if existing:
        raise ValueError("A user with this username or email already exists")

    admin_user = User(
        username=clean_username,
        email=clean_email,
        password=generate_password_hash(password),
        role='admin',
        profile=None
    )
    db.session.add(admin_user)
    db.session.commit()
    return admin_user
