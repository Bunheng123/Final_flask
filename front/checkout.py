import datetime
import json
import os
import requests
from flask import render_template, request, make_response, current_app, session
from front import front_bp
from front.cart import _read_cart_cookie
from product import get_product_by_id
from helpers.auth import login_required, current_user

# render checkout page, get cart cookie and render to checkout page, calculate subtotal, shipping and total, free shipping for all order
@front_bp.get('/checkout', endpoint='checkout')
@login_required
def checkout():
    cart_list = _read_cart_cookie()
    for item in cart_list:
        product = get_product_by_id(item['id'])
        if product:
            item.update({
                "image": product['image'],
                "name": product['name'],
                "description": product['description'],
                "price": float(product['price']),
                "category": product['category'],
            })

    subtotal = sum(item['price'] * item['qty'] for item in cart_list)
    shipping = 0  # free shipping
    total = subtotal + shipping
    user = current_user()
    return render_template(
        'front/checkout.html',
        cart_items=cart_list,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        user=user,
    )

# handle checkout form post, read posted user info, capture cart snapshot before clearing cookie, build the Telegram order message, send order message to Telegram bot, clear the cart cookie and render checkout page with order placed message
@front_bp.post('/checkout', endpoint='do_checkout')
@login_required
def do_checkout():
    # Read posted user info
    order_info = {
        'first_name': request.form.get('first_name', '').strip(),
        'last_name': request.form.get('last_name', '').strip(),
        'address': request.form.get('address', '').strip(),
        'phone': request.form.get('phone', '').strip(),
        'email': request.form.get('email', '').strip(),
        'payment': request.form.get('payment', '').strip(),
    }

    # Capture cart snapshot before clearing cookie
    cart_before = _read_cart_cookie()
    for item in cart_before:
        product = get_product_by_id(item['id'])
        if product:
            item.update({
                'name': product['name'],
                'image': product['image'],
            })

    subtotal = sum(item['price'] * item['qty'] for item in cart_before)
    shipping = 0
    total = subtotal + shipping
    order_id = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')

    # Build the Telegram order message.
    message = f"<b>✅ New Order #{order_id}</b>\n"
    message += f"<b>Customer:</b> {order_info['first_name']} {order_info['last_name']}\n"
    message += f"<b>Address:</b> {order_info['address']}\n"
    message += f"<b>Phone:</b> {order_info['phone']}\n"
    message += f"<b>Email:</b> {order_info['email']}\n"
    message += f"<b>Payment Method:</b> {order_info['payment']}\n\n"
    message += "<b>Items:</b>\n"

    for item in cart_before:
        name = item.get('name', 'Product')
        qty = item.get('qty', 1)
        line_total = item.get('price', 0) * qty
        message += f"- {name} ×{qty} = ${line_total:.2f}\n"

    message += f"\n<b>Subtotal:</b> ${subtotal:.2f}\n"
    message += f"<b>Shipping:</b> Free\n"
    message += f"<b>Total:</b> <b>${total:.2f}</b>\n"

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
        order_info=order_info,
        cart_items=cart_before,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
    ))
    # Clear the cart cookie
    response.set_cookie('cart_list', json.dumps([]), max_age=0, samesite='Lax')
    return response
