import html
import json

from flask import (
    current_app,
    flash,
    make_response,
    render_template,
    request,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

from extensions import db
from front import front_bp
from front.cart import _read_cart_cookie
from helpers.auth import current_user, login_required
from helpers.currency import khr_format, khr_from_usd, usd_format
from helpers.money import from_cents, to_cents
from helpers.telegram import send_telegram
from front.cart import _resolve_product
from services.khqr_service import generate_khqr
from services.order_service import create_order, new_order_number
from services.wallet_service import compute_split_payment


def _checkout_cart_items():
    cart_items = []
    for item in _read_cart_cookie():
        product = _resolve_product(item['id'], item.get('variant_id'))
        if not product:
            continue
        item.update({
            'image': product['image'],
            'name': product['name'],
            'description': product['description'],
            'price': float(product['price']),
            'category': product['category'],
        })
        cart_items.append(item)
    return cart_items


def _customer_defaults():
    user = current_user()
    if not user:
        return {'first_name': '', 'last_name': '', 'email': '', 'phone': '', 'address': ''}
    return {
        'first_name': getattr(user, 'first_name', '') or user.username,
        'last_name': getattr(user, 'last_name', '') or '',
        'email': user.email or '',
        'phone': getattr(user, 'phone', '') or '',
        'address': getattr(user, 'address', '') or '',
    }


def _render_checkout(cart_items, error=None, coupon_code=None, discount_cents=0):
    subtotal_cents = sum(to_cents(item['price']) * item['qty'] for item in cart_items)
    subtotal = from_cents(subtotal_cents)
    shipping = 0
    total_cents = max(0, subtotal_cents + to_cents(shipping) - discount_cents)
    total = from_cents(total_cents)
    user = current_user()
    return render_template(
        'front/checkout.html',
        cart_items=cart_items,
        subtotal=subtotal,
        discount_cents=discount_cents,
        discount=from_cents(discount_cents),
        coupon_code=coupon_code,
        shipping=shipping,
        total=total,
        total_khr=khr_from_usd(total),
        wallet_balance_khr=getattr(user, 'wallet_balance_khr', 0) if user else 0,
        base64_uri=None,
        qr_image_base64=None,
        khqr_payment=None,
        customer_defaults=_customer_defaults(),
        checkout_error=error,
        is_authenticated=bool(user),
        user=user,
        khr_format=khr_format,
        usd_format=usd_format,
    )


@front_bp.get('/checkout', endpoint='checkout')
@login_required
def checkout():
    return _render_checkout(_checkout_cart_items())


@front_bp.post('/checkout', endpoint='do_checkout')
@login_required
def do_checkout():
    cart_before = _checkout_cart_items()
    user = current_user()
    if user:
        try:
            db.session.refresh(user)
        except Exception:
            pass
    customer_defaults = _customer_defaults()
    order_info = {
        'first_name': request.form.get('first_name', '').strip() or customer_defaults['first_name'],
        'last_name': request.form.get('last_name', '').strip() or customer_defaults['last_name'],
        'address': request.form.get('address', '').strip() or customer_defaults['address'],
        'phone': request.form.get('phone', '').strip() or customer_defaults['phone'],
        'email': request.form.get('email', '').strip() or customer_defaults['email'],
        'payment': request.form.get('payment', '').strip().lower(),
    }
    if not cart_before:
        return _render_checkout(cart_before, 'Your cart is empty or no longer contains available products.'), 400
    if not all(order_info[field] for field in ('first_name', 'last_name', 'address', 'phone', 'email')):
        return _render_checkout(cart_before, 'Please complete all contact and delivery fields.'), 400

    payment_method = order_info['payment']
    if payment_method == 'khqr':
        payment_method = 'qr'
        order_info['payment'] = payment_method
    if payment_method not in {'cod', 'qr', 'wallet', 'split'}:
        return _render_checkout(cart_before, 'Choose a valid payment method.'), 400
    if payment_method in {'wallet', 'split'} and not user:
        return _render_checkout(cart_before, 'Sign in to use wallet payments.'), 403

    subtotal_cents = sum(to_cents(item['price']) * item['qty'] for item in cart_before)
    subtotal = from_cents(subtotal_cents)

    coupon_code = (request.form.get('coupon_code') or request.form.get('coupon_input') or '').strip().upper()
    discount_cents = 0
    if coupon_code:
        from services.coupon_service import validate_coupon
        valid, msg, calculated_discount = validate_coupon(
            coupon_code, subtotal_cents, user_id=user.id if user else None
        )
        if valid:
            discount_cents = calculated_discount
        else:
            coupon_code = None

    total_cents = max(0, subtotal_cents - discount_cents)
    total = from_cents(total_cents)
    total_khr = khr_from_usd(total)
    wallet_balance_khr = getattr(user, 'wallet_balance_khr', 0) if user else 0
    if payment_method == 'wallet':
        if wallet_balance_khr < total_khr:
            return _render_checkout(
                cart_before,
                'Your wallet balance is not enough for this order. Choose split payment or KHQR.',
            ), 400
        payment_result = compute_split_payment(total_khr, wallet_balance_khr)
    elif payment_method == 'split':
        if wallet_balance_khr <= 0:
            return _render_checkout(cart_before, 'Your wallet has no available balance to split.'), 400
        payment_result = compute_split_payment(total_khr, wallet_balance_khr)
    else:
        payment_result = {
            'payment_mode': 'khqr' if payment_method == 'qr' else 'cod',
            'wallet_used_khr': 0,
            'khqr_remaining_khr': total_khr if payment_method == 'qr' else 0,
            'total_khr': total_khr,
        }

    if payment_method == 'split' and payment_result['payment_mode'] == 'wallet':
        payment_method = 'wallet'
    elif payment_method == 'split' and payment_result['payment_mode'] == 'khqr':
        payment_method = 'qr'

    order_number = new_order_number()
    khqr_payment = None
    payment_reference = None
    external_amount_khr = payment_result['khqr_remaining_khr']
    if external_amount_khr:
        try:
            khqr_payment = generate_khqr(
                reference=order_number[:25],
                amount_khr=external_amount_khr,
            )
        except RuntimeError:
            current_app.logger.exception('Unable to generate checkout KHQR payment.')
            return _render_checkout(cart_before, 'Unable to create a payment QR right now. Please try again.'), 503
        payment_reference = khqr_payment['reference_md5']

    payment_status = (
        'pending' if external_amount_khr
        else 'paid' if payment_result['wallet_used_khr']
        else 'unpaid'
    )
    order_info['payment'] = payment_method
    try:
        order = create_order(
            order_info,
            cart_before,
            user_id=user.id if user else None,
            payment_method='split' if payment_result['wallet_used_khr'] and external_amount_khr else (
                'wallet' if payment_result['wallet_used_khr'] else payment_method
            ),
            payment_status=payment_status,
            payment_reference=payment_reference,
            total_khr=total_khr,
            wallet_used_khr=payment_result['wallet_used_khr'],
            order_number=order_number,
            coupon_code=coupon_code,
        )
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return _render_checkout(cart_before, str(exc)), 400
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to place customer checkout order.')
        return _render_checkout(cart_before, 'We could not place your order. Please try again.'), 500

    base64_uri = khqr_payment.get('base64_uri') if khqr_payment else None
    if not base64_uri:
        flash(f"Order #{order.order_number} received! You have 2 hours to cancel for an instant refund.", "success")
    response = make_response(render_template(
        'front/checkout.html',
        order_placed=True,
        order_id=order.order_number,
        order=order,
        order_number=order.order_number,
        order_info=order_info,
        cart_items=cart_before,
        subtotal=subtotal,
        discount_cents=discount_cents,
        discount=from_cents(discount_cents),
        coupon_code=coupon_code,
        shipping=0,
        total=total,
        total_khr=total_khr,
        wallet_balance_khr=getattr(user, 'wallet_balance_khr', 0) if user else 0,
        is_authenticated=bool(user),
        user=user,
        payment_result={**payment_result, **({'khqr': khqr_payment} if khqr_payment else {})},
        base64_uri=base64_uri,
        qr_image_base64=base64_uri,
        payment_check_url=(
            url_for('api_bp.payment_check', payment_hash=payment_reference)
            if payment_reference else None
        ),
        payment_cancel_url=(
            url_for('api_bp.payment_cancel', payment_hash=payment_reference)
            if payment_reference else None
        ),
        checkout_url=url_for('front_bp.checkout'),
        khr_format=khr_format,
        usd_format=usd_format,
    ))
    if not payment_reference:
        response.set_cookie('cart_list', json.dumps([]), max_age=0, samesite='Lax')
    return response
