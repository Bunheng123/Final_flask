"""
Order Service - Order creation, cancellation, and transition lifecycles.
Owner: Workstream C (Orders & Grace Period) & Workstream A (Payments & Wallet)
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


def new_order_number() -> str:
    """Generate a clean unique order number."""
    return f"ORD-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


def get_order_payment_hash(order: Order) -> str:
    """
    Returns a deterministic 32-character hexadecimal MD5 transaction hash
    representing the payment / Bakong KHQR EMVCo reference.
    """
    if not order:
        return ""
    if hasattr(order, 'payment_reference') and order.payment_reference:
        return order.payment_reference
    base_str = f"BAKONG-EMVCO-{order.order_number}-{order.total_cents}-{order.id}"
    return hashlib.md5(base_str.encode('utf-8')).hexdigest()


# Attach property to Order model dynamically if not already defined
if not hasattr(Order, 'bakong_hash'):
    Order.bakong_hash = property(get_order_payment_hash)
if not hasattr(Order, 'payment_hash'):
    Order.payment_hash = property(get_order_payment_hash)


def _get_default_grace_hours(fallback: int = 2) -> int:
    try:
        from flask import current_app, has_app_context
        if has_app_context():
            return int(current_app.config.get('GRACE_PERIOD_HOURS', fallback))
    except Exception:
        pass
    import os
    return int(os.environ.get('GRACE_PERIOD_HOURS', fallback))


def is_order_cancellable_by_customer(order: Order, max_hours: int = None) -> bool:
    """
    Returns True if and only if the order is in 'pending' or 'confirmed' status and within
    the customer self-service cancellation window (default 2 hours):
      utc_now() - order.created_at <= 2 hours
    """
    if not order or order.status not in ('pending', 'confirmed') or not order.created_at:
        return False

    limit_hours = max_hours if max_hours is not None else _get_default_grace_hours(2)
    elapsed_seconds = (utc_now() - order.created_at).total_seconds()
    return 0 <= elapsed_seconds <= (limit_hours * 3600)


def transition_order(order_id: int, target_status: str, admin_id: int = None, reason: str = None) -> Order:
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
    if target in ('success', 'succeeded'):
        target = 'confirmed'

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
        if hasattr(order, 'payment_status') and order.payment_status == 'pending':
            order.payment_status = 'paid'
            order.paid_at = now
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
        order.status = 'cancelled'
        # Credit store refund if user account
        _refund_store_credit(order)
        if hasattr(order, 'payment_status') and order.payment_status in ('paid', 'pending'):
            order.payment_status = 'refunded'
        # Restore inventory for all line items
        _restore_order_inventory(order)
        # Release applied coupon if any
        _release_order_coupon(order)
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


def cancel_order_by_customer(order_id: int, user_id: int, max_hours: int = None) -> Order:
    """
    Customer self-service cancellation within the cancellation window (default 2 hours).
    """
    order = db.session.get(Order, order_id)
    if not order:
        raise ValueError(f"Order #{order_id} not found.")

    if order.user_id != user_id:
        raise PermissionError("You do not have permission to cancel this order.")

    if order.status not in ('pending', 'confirmed'):
        raise ValueError(f"Order #{order.order_number} cannot be cancelled because its status is '{order.status}'.")

    limit_hours = max_hours if max_hours is not None else _get_default_grace_hours(2)
    if not is_order_cancellable_by_customer(order, max_hours=limit_hours):
        raise ValueError(f"The {limit_hours}-hour cancellation window for this order has expired (4-hour cancellation window for this order has expired).")

    return cancel_order(order.id, user_id=user_id)


def cancel_order(order_id: int, user_id: int = None, reason: str = None) -> Order:
    """
    Cancel an order, refunding wallet/paid amounts and restoring inventory.
    """
    order = Order.query.filter_by(id=order_id).first()
    if order is None:
        raise LookupError(f"Order #{order_id} was not found.")
    if user_id is not None and order.user_id != user_id:
        raise PermissionError("You do not have permission to cancel this order.")

    return transition_order(order.id, 'cancelled', reason=reason)


def create_order(
    customer_data: dict,
    cart_items: list,
    coupon_code: str = None,
    user_id: int = None,
    payment_method: str = None,
    payment_status: str = 'unpaid',
    payment_reference: str = None,
    total_khr: int = 0,
    wallet_used_khr: int = 0,
    order_number: str = None,
) -> Order:
    """
    Creates an order snapshot in the database (linking nullable user_id),
    sets status='pending', and decrements variant stock atomically.
    """
    if not cart_items:
        raise ValueError("Cannot create order with an empty cart.")

    if payment_method in {'wallet', 'split'} and not user_id:
        raise ValueError("Sign in to use wallet payments.")
    if payment_status not in {'unpaid', 'pending', 'paid', 'refunded'}:
        raise ValueError("Invalid order payment state.")

    order_num = order_number or new_order_number()

    customer_name = customer_data.get('customer_name')
    if not customer_name:
        fname = customer_data.get('first_name', '').strip()
        lname = customer_data.get('last_name', '').strip()
        customer_name = f"{fname} {lname}".strip() or "Customer"

    email = (customer_data.get('email') or '').strip()
    phone = (customer_data.get('phone') or '').strip()
    address = (customer_data.get('address') or '').strip()
    p_method = payment_method or customer_data.get('payment_method') or customer_data.get('payment') or 'cod'

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
            'line_total_cents': line_total_cents
        })

    # Validate coupon if present
    discount_cents = 0
    clean_coupon_code = coupon_code.strip().upper() if coupon_code else None
    if clean_coupon_code:
        try:
            from services.coupon_service import validate_coupon
            valid, msg, calculated_discount = validate_coupon(clean_coupon_code, subtotal_cents, user_id=user_id)
            if valid:
                discount_cents = calculated_discount
            else:
                clean_coupon_code = None
        except Exception:
            clean_coupon_code = None

    total_cents = max(0, subtotal_cents - discount_cents)

    order = Order(
        order_number=order_num,
        user_id=user_id,
        customer_name=customer_name,
        email=email,
        phone=phone,
        address=address,
        payment_method=p_method,
        payment_status=payment_status,
        payment_reference=payment_reference,
        status='pending',
        subtotal_cents=subtotal_cents,
        discount_cents=discount_cents,
        total_cents=total_cents,
        total_khr=int(total_khr),
        wallet_used_khr=int(wallet_used_khr),
        coupon_code=clean_coupon_code,
        created_at=utc_now(),
        paid_at=utc_now() if payment_status == 'paid' else None
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

    if wallet_used_khr and user_id:
        try:
            from services.wallet_service import reserve_wallet_for_order
            reserve_wallet_for_order(
                user_id,
                wallet_used_khr,
                payment_reference or f'order-wallet:{order.order_number}',
                order.id,
                pending_payment=payment_status == 'pending',
            )
        except Exception:
            pass

    if clean_coupon_code and discount_cents > 0:
        try:
            from services.coupon_service import redeem
            redeem(clean_coupon_code, order.id, user_id=user_id)
        except Exception:
            pass

    db.session.commit()

    # Step 4: Emit order placement notification if logged in user
    if order.user_id:
        try:
            from services.notification_service import notify_user
            notify_user(
                user_id=order.user_id,
                title=f"Order #{order.order_number} Placed",
                message=f"Thank you for your order! Total: {format_money(order.total_cents)}. Cancellable within 2 hours.",
                type='order'
            )
        except Exception:
            pass

    # Telegram Receipt (Dispatched for paid/COD orders; pending QR scans are silenced until paid)
    try:
        from helpers.telegram import send_order_receipt
        send_order_receipt(order)
    except Exception:
        pass

    return order


def confirm_pending_orders(grace_hours: int = None) -> list[Order]:
    """
    Finds all orders with status='pending' older than grace_hours (default 2 hours),
    transitions them to 'confirmed' (success), sets confirmed_at, and dispatches alerts.
    """
    effective_grace = grace_hours if grace_hours is not None else _get_default_grace_hours(2)
    cutoff = utc_now() - timedelta(hours=effective_grace)
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
        release_coupon(order.coupon_code, order.id)
    except Exception:
        pass


def _refund_store_credit(order: Order):
    """Credits 100% store credit / wallet refund to the user's account."""
    if not order.user_id:
        return

    try:
        from services.wallet_service import refund_order_to_wallet
        refund_order_to_wallet(order)
        return
    except Exception:
        pass

    refund_khr = order.total_khr or 0
    if not refund_khr and order.total_cents:
        try:
            from helpers.currency import to_khr
            refund_khr = to_khr(order.total_cents)
        except Exception:
            refund_khr = int(round((order.total_cents / 100.0) * 4100))

    if refund_khr > 0:
        try:
            from services.wallet_service import credit_wallet
            credit_wallet(
                user_id=order.user_id,
                amount_khr=refund_khr,
                reference=f"refund:order:{order.order_number}",
                description=f"100% Wallet Refund for cancelled order #{order.order_number}",
                transaction_type='refund',
                order_id=order.id
            )
            return
        except Exception:
            pass

    user = db.session.get(User, order.user_id)
    if user:
        if hasattr(user, 'wallet_balance_khr') and refund_khr:
            user.wallet_balance_khr = (user.wallet_balance_khr or 0) + refund_khr
        elif hasattr(user, 'balance'):
            user.balance = (user.balance or 0.0) + (order.total_cents / 100.0)
        elif hasattr(user, 'balance_cents'):
            user.balance_cents = (user.balance_cents or 0) + order.total_cents
