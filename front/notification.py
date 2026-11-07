"""
Notification Front Routes & Navbar Context Engine.
Owner: Workstream C (Orders & Grace Period)
"""
from flask import render_template, request, session, redirect, url_for, jsonify, flash
from front import front_bp
from services.auth_service import login_required
from helpers.time import to_local
from services.notification_service import (
    get_user_notifications,
    get_unread_count,
    mark_as_read,
    mark_all_as_read
)

@front_bp.app_context_processor
def inject_notifications_context():
    """
    Inject unread_count into all storefront templates for the navbar bell icon.
    """
    user_id = session.get('user_id')
    if user_id and session.get('is_login'):
        count = get_unread_count(user_id)
        return dict(
            unread_count=count,
            unread_notifications_count=count
        )
    return dict(
        unread_count=0,
        unread_notifications_count=0
    )


@front_bp.get('/notifications', endpoint='notifications')
@login_required
def notifications_inbox():
    """
    Customer notification inbox list.
    """
    user_id = session.get('user_id')
    notifications = get_user_notifications(user_id, limit=50)
    unread_count = get_unread_count(user_id)

    return render_template(
        'front/notifications/index.html',
        notifications=notifications,
        unread_count=unread_count,
        to_local=to_local
    )


@front_bp.post('/notifications/<int:notification_id>/read', endpoint='mark_notification_read')
@login_required
def read_notification(notification_id: int):
    """
    Mark an individual notification as read.
    Supports both AJAX and standard POST redirect.
    """
    user_id = session.get('user_id')
    success = mark_as_read(notification_id=notification_id, user_id=user_id)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': success,
            'unread_count': get_unread_count(user_id)
        })

    return redirect(request.referrer or url_for('front_bp.notifications'))


@front_bp.post('/notifications/read-all', endpoint='mark_all_notifications_read')
@login_required
def read_all_notifications():
    """
    Mark all unread notifications as read.
    """
    user_id = session.get('user_id')
    count = mark_all_as_read(user_id=user_id)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'count': count,
            'unread_count': 0
        })

    flash(f"Marked {count} notification(s) as read.", "success")
    return redirect(url_for('front_bp.notifications'))


@front_bp.get('/api/notifications/unread-count', endpoint='api_unread_count')
def api_unread_count():
    """
    Lightweight JSON endpoint for navbar live counter polling.
    """
    user_id = session.get('user_id')
    count = get_unread_count(user_id) if user_id and session.get('is_login') else 0
    return jsonify({
        'success': True,
        'unread_count': count
    })

