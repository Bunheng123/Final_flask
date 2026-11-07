"""
Order Service - Order creation, cancellation, and transition lifecycles.
Owner: Workstream C (Orders & Grace Period)
"""
import hashlib
import uuid
from datetime import timedelta, datetime, timezone
from extensions import db
from models.order import Order
from models.order_item import OrderItem
from models.product_variant import ProductVariant
from models.user import User
from helpers.time import utc_now, to_local
from helpers.money import to_cents, format_money

# Forward-only valid transitions state machine
VALID_TRANSITIONS = {
    'pending': ['confirmed', 'cancelled'],
    'confirmed': ['shipped', 'cancelled'],
    'shipped': ['delivered'],
    'delivered': [],  # Terminal state
    'cancelled': [],  # Terminal state
}

def get_order_payment_hash(order: Order) -> str:
    """
    Returns a deterministic 32-character hexadecimal MD5 transaction hash
    representing the payment / Bakong KHQR EMVCo reference.
    """
    if not order:
        return ""
    base_str = f"BAKONG-EMVCO-{order.order_number}-{order.total_cents}-{order.id}"
    return hashlib.md5(base_str.encode('utf-8')).hexdigest()

# Attach property to Order model dynamically if not already defined
if not hasattr(Order, 'bakong_hash'):
    Order.bakong_hash = property(get_order_payment_hash)
if not hasattr(Order, 'payment_hash'):
    Order.payment_hash = property(get_order_payment_hash)


def is_order_cancellable_by_customer(order: Order, max_hours: int = 4) -> bool:
    """
    Returns True if and only if the order is in 'pending' status and within
    the customer 4-hour self-service cancellation window:
      utc_now() - order.created_at <= 4 hours
    """
    if not order or order.status != 'pending' or not order.created_at:
        return False

    elapsed_seconds = (utc_now() - order.created_at).total_seconds()
    return 0 <= elapsed_seconds <= (max_hours * 3600)


def transition_order(order_id: int, target_status: str, admin_id: int = None) -> Order:
    """
    Transitions an order to target_status enforcing strict forward-only progression:
      pending -> confirmed -> shipped -> delivered (or cancelled from pending/confirmed)
    Prevents jumping directly from pending to delivered, or altering cancelled orders.
    Updates relevant lifecycle timestamps, restores stock on cancellation, and dispatches alerts.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    target = (target_status or '').strip().lower()
    current = order.status

    if target == current:
        return order

    allowed = VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise ValueError(
            f"Invalid status transition from '{current}' to '{target}'. "
            f"Forward-only lifecycle required: pending -> confirmed -> shipped -> delivered."
        )

    now = utc_now()
    notification_title = None
    notification_message = None
    notification_type = 'order'

    if target == 'confirmed':
        order.confirmed_at = now
        notification_title = f"Order #{order.order_number} Confirmed"
        notification_message = f"Your order #{order.order_number} has been approved and confirmed for processing."
    elif target == 'shipped':
        order.shipped_at = now
        notification_title = f"Order #{order.order_number} Shipped"
        notification_message = f"Great news! Your order #{order.order_number} has shipped and is on the way."
    elif target == 'delivered':
        order.delivered_at = now
        notification_title = f"Order #{order.order_number} Delivered"
        notification_message = f"Delivered! Your package for order #{order.order_number} has arrived safely."
    elif target == 'cancelled':
        order.cancelled_at = now
        # Restore inventory for all line items
        _restore_order_inventory(order)
        # Release applied coupon if any
        _release_order_coupon(order)
        # Credit store refund if user account
        _refund_store_credit(order)
        notification_title = f"Order #{order.order_number} Cancelled"
        notification_message = f"Order #{order.order_number} was cancelled. {format_money(order.total_cents)} store credit has been refunded to your account."
        notification_type = 'credit'

    order.status = target
    db.session.commit()

    # Step 4: Dispatch in-app customer notification
    if order.user_id and notification_title:
        try:
            from services.notification_service import notify_user
            notify_user(
                user_id=order.user_id,
                title=notification_title,
                message=notification_message,
                type=notification_type
            )
        except Exception:
            pass

    # Dispatch Telegram alert asynchronously
    try:
        from helpers.telegram import send_order_alert
        send_order_alert(
            order_number=order.order_number,
            total_str=format_money(order.total_cents),
            customer_name=order.customer_name,
            status=target
        )
    except Exception:
        pass

    return order


def cancel_order_by_customer(order_id: int, user_id: int) -> Order:
    """
    Customer self-service cancellation within the 4-hour window.
    Validations:
      1. Order must belong to user_id.
      2. Order must be in 'pending' status.
      3. utc_now() - order.created_at <= 4 hours.
    Actions:
      - Restores variant stock.
      - Credits 100% store credit refund to customer account.
      - Sets status to 'cancelled' and records cancelled_at.
      - Emits in-app notification to user.
      - Dispatches Telegram alert.
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.user_id != user_id:
        raise PermissionError("You do not have permission to cancel this order.")

    if order.status != 'pending':
        raise ValueError(f"Order #{order.order_number} cannot be cancelled because its status is '{order.status}'.")

    if not is_order_cancellable_by_customer(order, max_hours=4):
        raise ValueError("The 4-hour cancellation window for this order has expired.")

    # 1. Restore product inventory
    _restore_order_inventory(order)

    # 2. Release coupon if redeemed
    _release_order_coupon(order)

    # 3. Credit 100% store credit refund to user wallet / account
    _refund_store_credit(order)

    # 4. Mark status cancelled
    order.status = 'cancelled'
    order.cancelled_at = utc_now()
    db.session.commit()

    # Step 4: Emit in-app notification to customer
    try:
        from services.notification_service import notify_user
        notify_user(
            user_id=order.user_id,
            title=f"Order #{order.order_number} Cancelled",
            message=f"Your order #{order.order_number} was successfully cancelled. {format_money(order.total_cents)} has been credited to your store credit balance.",
            type='credit'
        )
    except Exception:
        pass

    # 5. Dispatch Telegram cancellation notification
    try:
        from helpers.telegram import send_telegram
        send_telegram(
            f"🛑 <b>[ORDER CANCELLED #{order.order_number}]</b>\n"
            f"Customer: <b>{order.customer_name}</b>\n"
            f"Total Refunded: <b>{format_money(order.total_cents)}</b> (100% Store Credit)\n"
            f"Status: <b>CANCELLED</b> (Customer self-service within 4-hour window)"
        )
    except Exception:
        pass

    return order


def cancel_order(order_id: int, reason: str = None) -> Order:
    """
    Administrative or system cancellation helper.
    """
    return transition_order(order_id, 'cancelled')


def create_order(customer_data: dict, cart_items: list, coupon_code: str = None, user_id: int = None) -> Order:
    """
    Creates an order snapshot in the database (linking nullable user_id),
    sets status='pending', and decrements variant stock atomically.
    """
    if not cart_items:
        raise ValueError("Cannot create order with an empty cart.")

    # Build unique order number: ORD-YYYYMMDDHHMMSS-XXXXXX
    order_number = f"ORD-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

    customer_name = customer_data.get('customer_name')
    if not customer_name:
        fname = customer_data.get('first_name', '').strip()
        lname = customer_data.get('last_name', '').strip()
        customer_name = f"{fname} {lname}".strip() or "Customer"

    email = (customer_data.get('email') or '').strip()
    phone = (customer_data.get('phone') or '').strip()
    address = (customer_data.get('address') or '').strip()
    payment_method = customer_data.get('payment_method') or customer_data.get('payment') or 'cod'

    # Compute items and subtotal in cents
    subtotal_cents = 0
    items_to_create = []

    for item in cart_items:
        qty = int(item.get('qty', 1))
        if qty <= 0:
            continue

        raw_price = item.get('price', 0)
        unit_price_cents = to_cents(raw_price) if not isinstance(raw_price, int) or raw_price < 100 else raw_price
        line_total_cents = unit_price_cents * qty
        subtotal_cents += line_total_cents

        variant_id = item.get('variant_id') or item.get('id')
        variant = db.session.get(ProductVariant, variant_id) if variant_id else None

        sku = variant.sku if variant else f"SKU-{item.get('id', 0):04d}"
        spec_name = variant.spec_name if variant else "Default"
        product_name = item.get('name') or (variant.product.name if variant and variant.product else "Product")

        items_to_create.append({
            'variant_id': variant.id if variant else None,
            'product_name': product_name,
            'sku': sku,
            'spec_name': spec_name,
            'qty': qty,
            'unit_price_cents': unit_price_cents,
            'line_total_cents': line_total_cents,
        })

    discount_cents = customer_data.get('discount_cents', 0)
    total_cents = max(0, subtotal_cents - discount_cents)

    order = Order(
        order_number=order_number,
        user_id=user_id,
        customer_name=customer_name,
        email=email,
        phone=phone,
        address=address,
        payment_method=payment_method,
        status='pending',
        subtotal_cents=subtotal_cents,
        discount_cents=discount_cents,
        total_cents=total_cents,
        coupon_code=coupon_code,
        created_at=utc_now()
    )
    db.session.add(order)
    db.session.flush()

    for item_data in items_to_create:
        order_item = OrderItem(
            order_id=order.id,
            variant_id=item_data['variant_id'],
            product_name=item_data['product_name'],
            sku=item_data['sku'],
            spec_name=item_data['spec_name'],
            qty=item_data['qty'],
            unit_price_cents=item_data['unit_price_cents'],
            line_total_cents=item_data['line_total_cents']
        )
        db.session.add(order_item)

        # Atomic stock decrement
        if item_data['variant_id']:
            _decrement_variant_stock(item_data['variant_id'], item_data['qty'])

    db.session.commit()

    # Step 4: Emit order placement notification if logged in user
    if order.user_id:
        try:
            from services.notification_service import notify_user
            notify_user(
                user_id=order.user_id,
                title=f"Order #{order.order_number} Placed",
                message=f"Thank you for your order! Total: {format_money(order.total_cents)}. Cancellable within 4 hours.",
                type='order'
            )
        except Exception:
            pass

    # Telegram Receipt & Alert
    try:
        from helpers.telegram import send_order_receipt
        send_order_receipt(order)
    except Exception:
        pass

    return order


def confirm_pending_orders(grace_hours: int = 4) -> list[Order]:
    """
    Finds all orders with status='pending' older than grace_hours,
    transitions them to 'confirmed', sets confirmed_at, and dispatches alerts.
    """
    cutoff = utc_now() - timedelta(hours=grace_hours)
    pending_orders = Order.query.filter(
        Order.status == 'pending',
        Order.created_at <= cutoff
    ).all()

    confirmed_list = []
    for order in pending_orders:
        transition_order(order.id, 'confirmed')
        confirmed_list.append(order)

    return confirmed_list


# Internal Helpers
def _restore_order_inventory(order: Order):
    """Restores inventory for all line items in an order."""
    for item in order.items:
        if not item.variant_id:
            continue
        restored = False
        try:
            from services.stock_service import restore_stock
            restored = restore_stock(item.variant_id, item.qty)
        except Exception:
            restored = False

        if not restored:
            variant = db.session.get(ProductVariant, item.variant_id)
            if variant:
                variant.stock = (variant.stock or 0) + item.qty


def _decrement_variant_stock(variant_id: int, qty: int):
    """Executes atomic inventory decrement with fallback."""
    decremented = False
    try:
        from services.stock_service import decrement_stock_atomic
        decremented = decrement_stock_atomic(variant_id, qty)
    except Exception:
        decremented = False

    if not decremented:
        # Atomic SQL update with rowcount check
        stmt = db.text(
            "UPDATE product_variants SET stock = stock - :qty "
            "WHERE id = :variant_id AND stock >= :qty"
        )
        res = db.session.execute(stmt, {'variant_id': variant_id, 'qty': qty})
        if res.rowcount == 0:
            variant = db.session.get(ProductVariant, variant_id)
            if variant:
                variant.stock = max(0, (variant.stock or 0) - qty)


def _release_order_coupon(order: Order):
    """Releases redeemed coupon usage limit if applicable."""
    if not order.coupon_code:
        return
    try:
        from services.coupon_service import release_coupon
        release_coupon(order.coupon_code)
    except Exception:
        pass


def _refund_store_credit(order: Order):
    """Credits 100% store credit refund to the user's account."""
    if not order.user_id:
        return

    refund_cents = order.total_cents
    try:
        from services.wallet_service import credit_wallet
        credit_wallet(
            user_id=order.user_id,
            amount_cents=refund_cents,
            reason=f"100% Store Credit Refund for cancelled order #{order.order_number}"
        )
    except Exception:
        user = db.session.get(User, order.user_id)
        if user:
            if hasattr(user, 'balance'):
                user.balance = (user.balance or 0.0) + (refund_cents / 100.0)
            elif hasattr(user, 'balance_cents'):
                user.balance_cents = (user.balance_cents or 0) + refund_cents
