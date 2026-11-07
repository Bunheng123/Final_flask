import datetime
import json
import os
import requests
from flask import render_template, request, make_response, current_app, url_for
from front import front_bp
from front.cart import _read_cart_cookie
from product import get_product_by_id
from helpers.currency import khr_from_usd, khr_format, usd_format
from helpers.money import from_cents, to_cents
from helpers.auth import current_user
from extensions import db
from services.khqr_service import generate_khqr
from services.wallet_service import compute_split_payment


def _checkout_cart_items():
    cart_items = []
    for item in _read_cart_cookie():
        product = get_product_by_id(item['id'])
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
        'first_name': user.first_name or user.username,
        'last_name': user.last_name or '',
        'email': user.email,
        'phone': user.phone or '',
        'address': user.address or '',
    }


# render checkout page, get cart cookie and render to checkout page, calculate subtotal, shipping and total, free shipping for all order
@front_bp.get('/checkout', endpoint='checkout')
def checkout():
    cart_list = _checkout_cart_items()
    subtotal_cents = sum(to_cents(item['price']) * item['qty'] for item in cart_list)
    subtotal = from_cents(subtotal_cents)
    shipping = 0  # free shipping
    total_cents = subtotal_cents + to_cents(shipping)
    total = from_cents(total_cents)
    total_khr = khr_from_usd(total)

    return render_template(
        'front/checkout.html',
        cart_items=cart_list,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        total_khr=total_khr,
        base64_uri=None,
        qr_image_base64=None,
        khqr_payment=None,
        customer_defaults=_customer_defaults(),
        khr_format=khr_format,
        usd_format=usd_format,
    )

# handle checkout form post, read posted user info, capture cart snapshot before clearing cookie, build the Telegram order message, send order message to Telegram bot, clear the cart cookie and render checkout page with order placed message
@front_bp.post('/checkout', endpoint='do_checkout')
def do_checkout():
    # Read posted user info
    customer_defaults = _customer_defaults()
    order_info = {
        'first_name': request.form.get('first_name', '').strip() or customer_defaults['first_name'],
        'last_name': request.form.get('last_name', '').strip(),
        'address': request.form.get('address', '').strip(),
        'phone': request.form.get('phone', '').strip(),
        'email': request.form.get('email', '').strip() or customer_defaults['email'],
        'payment': request.form.get('payment', '').strip(),
    }

    # Capture cart snapshot before clearing cookie
    cart_before = _checkout_cart_items()

    subtotal_cents = sum(to_cents(item['price']) * item['qty'] for item in cart_before)
    subtotal = from_cents(subtotal_cents)
    shipping = 0
    total_cents = subtotal_cents + to_cents(shipping)
    total = from_cents(total_cents)
    order_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')
    payment_method = order_info.get('payment', '').strip().lower()
    total_khr = khr_from_usd(total)
    payment_result = {'payment_mode': payment_method or 'wallet', 'wallet_used_khr': 0, 'khqr_remaining_khr': total_khr}

    if payment_method == 'wallet':
        wallet_balance_khr = int(request.form.get('wallet_balance_khr', 0) or 0)
        payment_result = compute_split_payment(total_khr, wallet_balance_khr)
    elif payment_method in {'khqr', 'qr', 'split'}:
        wallet_balance_khr = int(request.form.get('wallet_balance_khr', 0) or 0)
        payment_result = compute_split_payment(total_khr, wallet_balance_khr)
        if payment_result['khqr_remaining_khr'] > 0:
            payment_result['khqr'] = generate_khqr(
                reference=f'KHQR-{order_id}',
                amount_khr=payment_result['khqr_remaining_khr'],
            )

    base64_uri = None
    if payment_result.get('khqr') and payment_result['khqr'].get('base64_uri'):
        base64_uri = payment_result['khqr']['base64_uri']

    user = current_user()
    if user:
        user.first_name = order_info['first_name']
        user.last_name = order_info['last_name']
        user.phone = order_info['phone']
        user.address = order_info['address']
        db.session.commit()

    # Build the Telegram order message.
    message = f"<b>✅ New Order #{order_id}</b>\n"
    message += f"<b>Customer:</b> {order_info['first_name']} {order_info['last_name']}\n"
    message += f"<b>Address:</b> {order_info['address']}\n"
    message += f"<b>Phone:</b> {order_info['phone']}\n"
    message += f"<b>Email:</b> {order_info['email']}\n"
    message += f"<b>Payment Method:</b> {order_info['payment']}\n"
    if payment_result.get('payment_mode') in {'split', 'khqr', 'qr', 'wallet'}:
        message += f"<b>Wallet Split:</b> {payment_result.get('wallet_used_khr', 0)} KHR / {payment_result.get('khqr_remaining_khr', 0)} KHR\n\n"
    else:
        message += "\n"
    message += "<b>Items:</b>\n"

    for item in cart_before:
        name = item.get('name', 'Product')
        qty = item.get('qty', 1)
        line_total = item.get('price', 0) * qty
        message += f"- {name} ×{qty} = ${line_total:.2f}\n"

    message += f"\n<b>Subtotal:</b> ${subtotal:.2f}\n"
    message += f"<b>Shipping:</b> Free\n"
    message += f"<b>Total:</b> <b>${total:.2f}</b> ({khr_format(total_khr)})\n"

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN") or current_app.config.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or current_app.config.get("TELEGRAM_CHAT_ID", "@SETEC_PP_SHOP")

    if bot_token:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'text': message,
            'parse_mode': 'HTML',
            'chat_id': chat_id,
            'disable_web_page_preview': False,
            'disable_notification': False,
            'reply_to_message_id': None,
        }
        headers = {
            'accept': 'application/json',
            'User-Agent': 'Telegram Bot SDK - (https://github.com/irazasyed/telegram-bot-sdk)',
            'content-type': 'application/json',
        }
        try:
            requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception:
            pass

    response = make_response(render_template(
        'front/checkout.html',
        order_placed=True,
        order_id=order_id,
        order_info=order_info,
        cart_items=cart_before,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        total_khr=total_khr,
        payment_result=payment_result,
        base64_uri=base64_uri,
        qr_image_base64=base64_uri,
        payment_check_url=(
            url_for('api_bp.payment_check', payment_hash=payment_result['khqr']['reference_md5'])
            if payment_result.get('khqr') else None
        ),
        checkout_url=url_for('front_bp.checkout'),
        khr_format=khr_format,
        usd_format=usd_format,
    ))
    if not payment_result.get('khqr'):
        response.set_cookie('cart_list', json.dumps([]), max_age=0, samesite='Lax')
    return response
