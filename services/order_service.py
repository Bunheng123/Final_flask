"""
Order Service - Order creation, cancellation, and transition lifecycles.
Owner: Workstream C (Orders & Grace Period)
"""

def create_order(customer_data: dict, cart_items: list, coupon_code: str = None):
    """
    Creates an order snapshot in the database, sets status='pending', and decrements stock.

    TODO: Workstream C - Implement order creation logic.
    """
    raise NotImplementedError("TODO: Workstream C - Implement create_order")

def cancel_order(order_id: int, reason: str = None) -> bool:
    """
    Cancels an order, restores stock, releases coupons, and updates status to 'cancelled'.

    TODO: Workstream C - Implement cancel_order.
    """
    raise NotImplementedError("TODO: Workstream C - Implement cancel_order")

def confirm_pending_orders(grace_hours: int = 4) -> list:
    """
    Finds all orders with status='pending' older than grace_hours, marks them 'confirmed',
    and dispatches Telegram alerts.

    TODO: Workstream C - Implement confirm_pending_orders.
    """
    raise NotImplementedError("TODO: Workstream C - Implement confirm_pending_orders")
