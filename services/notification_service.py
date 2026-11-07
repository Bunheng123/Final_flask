"""
Notification Service - Customer In-App Notification Engine.
Owner: Workstream C (Orders & Grace Period)
"""
import logging
from extensions import db
from models.notification import Notification
from helpers.time import utc_now

logger = logging.getLogger(__name__)

def notify_user(user_id: int, title: str, message: str, type: str = 'order') -> Notification | None:
    """
    Persist an in-app notification to the database for a customer.
    Gracefully handles anonymous / guest users (user_id=None).
    """
    if not user_id:
        return None

    try:
        notification = Notification(
            user_id=user_id,
            title=(title or '').strip(),
            message=(message or '').strip(),
            type=(type or 'order').strip().lower(),
            is_read=False,
            created_at=utc_now()
        )
        db.session.add(notification)
        db.session.commit()
        logger.info(f"[Notification] Dispatched alert '{title}' to user #{user_id}.")
        return notification
    except Exception as e:
        logger.error(f"[Notification Error] Failed to persist alert for user #{user_id}: {e}")
        db.session.rollback()
        return None


def get_unread_count(user_id: int) -> int:
    """
    Perform an indexed query count (is_read == False) for optimal navbar rendering.
    """
    if not user_id:
        return 0

    try:
        return Notification.query.filter_by(
            user_id=user_id,
            is_read=False
        ).count()
    except Exception as e:
        logger.error(f"[Notification Error] Error counting unread for user #{user_id}: {e}")
        return 0


def mark_as_read(notification_id: int, user_id: int) -> bool:
    """
    Marks a specific notification as read.
    Enforces user ownership check.
    """
    if not user_id or not notification_id:
        return False

    notification = Notification.query.filter_by(
        id=notification_id,
        user_id=user_id
    ).first()

    if not notification:
        return False

    if not notification.is_read:
        notification.is_read = True
        db.session.commit()

    return True


def mark_all_as_read(user_id: int) -> int:
    """
    Marks all unread notifications as read for a given user.
    Returns the number of notifications updated.
    """
    if not user_id:
        return 0

    count = Notification.query.filter_by(
        user_id=user_id,
        is_read=False
    ).update({Notification.is_read: True})

    if count:
        db.session.commit()

    return count


def get_user_notifications(user_id: int, limit: int = 50) -> list[Notification]:
    """
    Fetches the notification history for a user, sorted newest first.
    """
    if not user_id:
        return []

    return Notification.query.filter_by(
        user_id=user_id
    ).order_by(
        Notification.created_at.desc()
    ).limit(limit).all()

