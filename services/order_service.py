"""Order creation and customer cancellation lifecycle."""

import uuid

from extensions import db
from helpers.money import to_cents
from helpers.time import utc_now
from models.order import Order
from models.order_item import OrderItem
from services.wallet_service import refund_order_to_wallet, reserve_wallet_for_order


def new_order_number():
    return uuid.uuid4().hex[:16].upper()


def create_order(
    customer_data: dict,
    cart_items: list,
    user_id: int = None,
    payment_method: str = 'cod',
    payment_status: str = 'unpaid',
    payment_reference: str = None,
    total_khr: int = 0,
    wallet_used_khr: int = 0,
    order_number: str = None,
):
    """Persist an order snapshot and any wallet debit in the current transaction."""
    if not cart_items:
        raise ValueError('Your cart is empty.')
    if payment_method in {'wallet', 'split'} and not user_id:
        raise ValueError('Sign in to use wallet payments.')
    if payment_status not in {'unpaid', 'pending', 'paid'}:
        raise ValueError('Invalid order payment state.')

    subtotal_cents = sum(to_cents(item['price']) * int(item['qty']) for item in cart_items)
    if subtotal_cents <= 0:
        raise ValueError('Order total must be greater than zero.')

    order = Order(
        order_number=order_number or new_order_number(),
        user_id=user_id,
        customer_name=' '.join(filter(None, [
            customer_data.get('first_name', '').strip(),
            customer_data.get('last_name', '').strip(),
        ])),
        email=customer_data.get('email', '').strip(),
        phone=customer_data.get('phone', '').strip(),
        address=customer_data.get('address', '').strip(),
        payment_method=payment_method,
        payment_status=payment_status,
        payment_reference=payment_reference,
        subtotal_cents=subtotal_cents,
        total_cents=subtotal_cents,
        total_khr=int(total_khr),
        wallet_used_khr=int(wallet_used_khr),
        status='confirmed' if payment_status == 'paid' else 'pending',
        paid_at=utc_now() if payment_status == 'paid' else None,
    )
    for item in cart_items:
        qty = int(item['qty'])
        unit_price_cents = to_cents(item['price'])
        product_id = item.get('id')
        order.items.append(OrderItem(
            product_name=item.get('name') or 'Product',
            sku=f'PRODUCT-{product_id}' if product_id is not None else 'PRODUCT',
            spec_name='Default',
            qty=qty,
            unit_price_cents=unit_price_cents,
            line_total_cents=unit_price_cents * qty,
        ))

    db.session.add(order)
    db.session.flush()
    if wallet_used_khr:
        reserve_wallet_for_order(
            user_id,
            wallet_used_khr,
            payment_reference or f'order-wallet:{order.order_number}',
            order.id,
            pending_payment=payment_status == 'pending',
        )
    return order


def cancel_order(order_id: int, user_id: int):
    """Cancel an order owned by the customer and refund paid value to wallet."""
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    if order is None:
        raise LookupError('Order was not found.')
    return refund_order_to_wallet(order)

def confirm_pending_orders(grace_hours: int = 4) -> list:
    """
    Finds all orders with status='pending' older than grace_hours, marks them 'confirmed',
    and dispatches Telegram alerts.

    TODO: Workstream C - Implement confirm_pending_orders.
    """
    raise NotImplementedError("TODO: Workstream C - Implement confirm_pending_orders")
