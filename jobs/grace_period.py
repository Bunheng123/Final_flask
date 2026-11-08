"""
Grace Period Order Confirmation Job.
Runs periodically to automatically confirm orders that have been pending for > 4 hours.
Owner: Workstream C (Orders & Grace Period)
"""
import os
import sys
import logging
from datetime import timedelta

# Ensure workspace root is in sys.path for direct script execution
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import current_app, has_app_context
from extensions import db
from models.order import Order
from config import GRACE_PERIOD_HOURS
from helpers.time import utc_now
from helpers.money import format_money
from helpers.telegram import send_telegram
from services.order_service import transition_order

logger = logging.getLogger(__name__)

def _process_grace_period(grace_hours: int = None) -> list[Order]:
    """
    Internal processor: queries qualified pending orders and transitions them.
    Must be called within an active Flask application context.
    """
    if grace_hours is None:
        if has_app_context():
            grace_hours = current_app.config.get('GRACE_PERIOD_HOURS', GRACE_PERIOD_HOURS)
        else:
            grace_hours = GRACE_PERIOD_HOURS

    cutoff = utc_now() - timedelta(hours=grace_hours)
    
    # Query all orders meeting: status == 'pending' and created_at <= (utc_now() - grace_hours)
    qualified_orders = Order.query.filter(
        Order.status == 'pending',
        Order.created_at <= cutoff
    ).all()

    confirmed_orders = []

    for order in qualified_orders:
        try:
            # Advance state using domain state machine
            transition_order(order.id, 'confirmed')
            confirmed_orders.append(order)

            # Step 3: Dispatch Telegram automation alert in background thread
            alert_text = (
                f"⏰ <b>[AUTO-CONFIRMED ORDER #{order.order_number}]</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Customer: <b>{order.customer_name}</b>\n"
                f"Total Amount: <b>{format_money(order.total_cents)}</b>\n"
                f"Notice: <b>{grace_hours}-hour grace window expired.</b>\n"
                f"Status: <b>CONFIRMED</b> (Auto-advanced to fulfillment)\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_telegram(alert_text)

            # In-app customer alert for grace period auto-confirmation
            if order.user_id:
                try:
                    from services.notification_service import notify_user
                    notify_user(
                        user_id=order.user_id,
                        title=f"Order #{order.order_number} Auto-Confirmed",
                        message=f"Your order #{order.order_number} was automatically confirmed after the {grace_hours}-hour grace period and is now being prepared for shipment.",
                        type='order'
                    )
                except Exception:
                    pass

            logger.info(f"[Grace Period] Auto-confirmed order #{order.order_number} (ID: {order.id}).")

        except Exception as e:
            logger.error(f"[Grace Period] Error auto-confirming order #{order.id}: {e}")
            db.session.rollback()

    if confirmed_orders:
        db.session.commit()
        logger.info(f"[Grace Period Scheduler] Successfully processed and confirmed {len(confirmed_orders)} order(s).")

    return confirmed_orders


def check_grace_period_orders(app=None, grace_hours: int = None) -> list[Order]:
    """
    Periodic job function to check and auto-confirm expired pending orders.
    Ensures execution occurs cleanly within an active Flask application context.
    """
    if not has_app_context():
        if app is None:
            from app import app as flask_app
            app = flask_app
        with app.app_context():
            return _process_grace_period(grace_hours)
    return _process_grace_period(grace_hours)


# Alias for backward-compatibility with jobs/__init__.py and scheduler task registration
auto_confirm_pending_orders_job = check_grace_period_orders


if __name__ == '__main__':
    # Allow manual invocation via CLI: python jobs/grace_period.py
    from app import app
    with app.app_context():
        confirmed = check_grace_period_orders()
        print(f"[CLI] Manually processed {len(confirmed)} auto-confirmed order(s).")
