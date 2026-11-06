from flask import jsonify, request, session
from sqlalchemy import text
from api import api_bp
from extensions import db

def require_admin_session():
    if not session.get('is_login') or session.get('role') != 'admin':
        return jsonify({
            'status': 401,
            'error': 'Unauthorized',
            'message': 'Admin session required.'
        }), 401
    return None

def get_all_users():
    sql = text("SELECT id, username, email, role, profile FROM user")
    result = db.session.execute(sql)
    return [dict(row._mapping) for row in result]

def get_user_by_id(user_id):
    sql = text("SELECT id, username, email, role, profile FROM user WHERE id = :user_id")
    result = db.session.execute(sql, {"user_id": user_id}).fetchone()
    return dict(result._mapping) if result else None

@api_bp.get('/users', endpoint='get_users')
@api_bp.get('/user', endpoint='get_user_list')
def api_users():
    auth_err = require_admin_session()
    if auth_err:
        return auth_err
    users = get_all_users()
    return jsonify(users)

@api_bp.get('/user/<int:user_id>', endpoint='get_user_by_id')
def api_user_detail(user_id):
    auth_err = require_admin_session()
    if auth_err:
        return auth_err
    user = get_user_by_id(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify(user)
