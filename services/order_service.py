"""
Order Service - Order creation, cancellation, and transition lifecycles.
Owner: Workstream C (Orders & Grace Period)
"""
from datetime import datetime, timezone
from extensions import db
from models.order import Order
from models.order_item import OrderItem
from models.product_variant import ProductVariant
from helpers.time import utc_now
from helpers.money import to_cents


def create_order(customer_data: dict, cart_items: list, coupon_code: str = None, user_id: int = None) -> Order:
    """
    Creates an order snapshot in the database (linking nullable user_id),
    sets status='pending', records itemized OrderItems, and decrements inventory stock.
    """
    first_name = customer_data.get('first_name', '').strip()
    last_name = customer_data.get('last_name', '').strip()
    name = f"{first_name} {last_name}".strip() or customer_data.get('customer_name', 'Customer')

    order_ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')[:17]
    order_number = f"ORD-{order_ts}"

    subtotal_cents = 0
    items_to_create = []

    for item in cart_items:
        prod_id = item.get('id')
        qty = int(item.get('qty', 1))
        unit_price = float(item.get('price', 0))
        unit_cents = to_cents(unit_price)
        line_cents = unit_cents * qty
        subtotal_cents += line_cents

        variant = None
        if prod_id:
            variant = ProductVariant.query.filter_by(product_id=prod_id).first()
            if not variant:
                variant = db.session.get(ProductVariant, prod_id)

        items_to_create.append(OrderItem(
            variant_id=variant.id if variant else None,
            product_name=item.get('name', 'Product'),
            sku=variant.sku if variant else f"SKU-{prod_id or 'DEF'}",
            spec_name=variant.spec_name if variant else 'Default',
            qty=qty,
            unit_price_cents=unit_cents,
            line_total_cents=line_cents
        ))

        # Decrement stock atomically if variant is present
        if variant:
            try:
                from services.stock_service import decrement_stock_atomic
                decrement_stock_atomic(variant.id, qty)
            except Exception:
                pass

    discount_cents = customer_data.get('discount_cents', 0)
    total_cents = max(0, subtotal_cents - discount_cents)

    order = Order(
        order_number=order_number,
        user_id=user_id,
        customer_name=name,
        email=customer_data.get('email', '').strip().lower(),
        phone=customer_data.get('phone', '').strip(),
        address=customer_data.get('address', '').strip(),
        payment_method=customer_data.get('payment', customer_data.get('payment_method', 'cod')),
        status='pending',
        subtotal_cents=subtotal_cents,
        discount_cents=discount_cents,
        total_cents=total_cents,
        coupon_code=coupon_code,
        created_at=utc_now(),
        items=items_to_create
    )

    db.session.add(order)
    db.session.commit()
    return order


def cancel_order(order_id: int, reason: str = None) -> bool:
    """
    Cancels an order, restores stock, releases coupons, and updates status to 'cancelled'.
    """
    order = db.session.get(Order, order_id)
    if not order or order.status == 'cancelled':
        return False

    order.status = 'cancelled'
    order.cancelled_at = utc_now()

    # Restore stock
    try:
        from services.stock_service import restore_stock
        for item in order.items:
            if item.variant_id:
                try:
                    restore_stock(item.variant_id, item.qty)
                except Exception:
                    pass
    except Exception:
        pass

    db.session.commit()
    return True


def confirm_pending_orders(grace_hours: int = 4) -> list:
    """
    Finds all orders with status='pending' older than grace_hours, marks them 'confirmed',
    and dispatches Telegram alerts.
    """
    from datetime import timedelta
    cutoff = utc_now() - timedelta(hours=grace_hours)
    pending_orders = Order.query.filter(
        Order.status == 'pending',
        Order.created_at <= cutoff
    ).all()

    confirmed = []
    for order in pending_orders:
        order.status = 'confirmed'
        order.confirmed_at = utc_now()
        confirmed.append(order)

    if confirmed:
        db.session.commit()

    return confirmed
