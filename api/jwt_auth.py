"""
JWT Authentication & Authorization Engine.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security)
"""
from functools import wraps
from datetime import datetime, timezone, timedelta
import jwt
from flask import current_app, request, jsonify, g
from models.user import User

JWT_ALGORITHM = "HS256"
DEFAULT_EXPIRATION_SECONDS = 86400  # 24 hours


def _get_secret_key() -> str:
    """Retrieve application secret key for JWT signing."""
    return current_app.config.get("SECRET_KEY", "dev-secret-key-fallback")


def create_access_token(user: User, expires_in: int = DEFAULT_EXPIRATION_SECONDS) -> str:
    """
    Generate a signed JWT token valid for 24 hours (or expires_in seconds).
    Payload includes user id, username, email, role, and standard claims.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role or "user",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, _get_secret_key(), algorithm=JWT_ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT token.
    Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on verification failure.
    """
    return jwt.decode(token, _get_secret_key(), algorithms=[JWT_ALGORITHM])


def _extract_token_from_header() -> str | None:
    """Extract Bearer token from HTTP Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None
    parts = auth_header.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def jwt_required(f):
    """
    Decorator for API endpoints requiring valid JWT Bearer authentication.
    Populates `g.jwt_user` (payload dict) and `g.current_user` (User model instance).
    Returns HTTP 401 on missing or invalid tokens.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token_from_header()
        if not token:
            return jsonify({
                "success": False,
                "error": "Missing or malformed Authorization header. Expected: Bearer <token>"
            }), 401

        try:
            payload = decode_access_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({
                "success": False,
                "error": "Token has expired. Please log in again."
            }), 401
        except jwt.InvalidTokenError:
            return jsonify({
                "success": False,
                "error": "Invalid authentication token."
            }), 401

        user_id = payload.get("user_id")
        user = User.query.get(user_id) if user_id else None
        if not user or not getattr(user, "is_active", True):
            return jsonify({
                "success": False,
                "error": "User account not found or inactive."
            }), 401

        g.jwt_user = payload
        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def jwt_admin_required(f):
    """
    Decorator for API endpoints requiring JWT authentication with 'admin' role.
    Returns HTTP 401 on missing/invalid token, HTTP 403 on non-admin user.
    """
    @wraps(f)
    @jwt_required
    def decorated(*args, **kwargs):
        role = g.jwt_user.get("role") if hasattr(g, "jwt_user") else None
        user_role = getattr(g.current_user, "role", None) if hasattr(g, "current_user") else None

        if role != "admin" and user_role != "admin":
            return jsonify({
                "success": False,
                "error": "Admin privileges required."
            }), 403

        return f(*args, **kwargs)

    return decorated

