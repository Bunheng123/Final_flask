"""
Transactional Email Service Stub.
Owner: Workstream C / M3 (Orders, Checkout Transitions & Grace Period Confirmer)
"""
import logging

logger = logging.getLogger(__name__)

def send_order_email(order, event: str = "created"):
    """
    No-op stub for sending transactional order emails (receipts, status updates).
    TODO: Workstream C / M3 - Connect to Flask-Mail and send formatted email templates.
    """
    logger.info(f"[Email Service Stub] send_order_email called for order {getattr(order, 'order_number', order)} with event '{event}'")
    return True
