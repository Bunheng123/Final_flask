from flask import jsonify, request, session
from api import api_bp
from extensions import db
from models.user import User

def require_admin_session():
    if not session.get('is_login') or session.get('role') != 'admin':
        return jsonify({
            'status': 401,
            'error': 'Unauthorized',
            'message': 'Admin session required.'
        }), 401
    return None

def get_all_users():
    users = User.query.all()
    return [{
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': u.role,
        'profile': u.profile
    } for u in users]

def get_user_by_id(user_id):
    u = db.session.get(User, user_id)
    if not u:
        return None
    return {
        'id': u.id,
        'username': u.username,
        'email': u.email,
        'role': u.role,
        'profile': u.profile
    }

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
