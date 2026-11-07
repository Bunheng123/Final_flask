"""
RESTful JWT Authentication Endpoints.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security)
"""
from flask import request, jsonify, g
from werkzeug.security import check_password_hash
from extensions import db
from api import api_bp
from api.jwt_auth import create_access_token, jwt_required, DEFAULT_EXPIRATION_SECONDS
from models.user import User


@api_bp.post('/auth/login', endpoint='api_auth_login')
def login():
    """
    POST /api/auth/login
    Accepts JSON credentials (username/email and password) and returns a signed 24h JWT Bearer token.
    """
    data = request.get_json(silent=True) or request.form
    if not data:
        return jsonify({
            "success": False,
            "error": "Request body must be valid JSON."
        }), 400

    identifier = (data.get("identifier") or data.get("email") or data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    if not identifier or not password:
        return jsonify({
            "success": False,
            "error": "Email/username and password are required."
        }), 400

    user = User.query.filter(
        (db.func.lower(User.email) == identifier) |
        (db.func.lower(User.username) == identifier)
    ).first()

    if not user or not check_password_hash(user.password, password):
        return jsonify({
            "success": False,
            "error": "Invalid email or password."
        }), 401

    if getattr(user, 'is_active', True) is False:
        return jsonify({
            "success": False,
            "error": "Your account is inactive. Please contact support."
        }), 403

    token = create_access_token(user, expires_in=DEFAULT_EXPIRATION_SECONDS)

    return jsonify({
        "success": True,
        "token": token,
        "token_type": "Bearer",
        "expires_in": DEFAULT_EXPIRATION_SECONDS,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role or "user"
        }
    }), 200


@api_bp.get('/auth/me', endpoint='api_auth_me')
@jwt_required
def me():
    """
    GET /api/auth/me
    Returns current authenticated user details from JWT token.
    """
    user = g.current_user
    return jsonify({
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role or "user",
            "profile": user.profile,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
    }), 200

