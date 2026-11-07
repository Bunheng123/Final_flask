import datetime
import json
import os
import requests
from flask import render_template, request, make_response, current_app, session
from front import front_bp
from front.cart import _read_cart_cookie
from product import get_product_by_id
from services.order_service import create_order
from helpers.money import to_cents
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

# handle checkout form post, create order in database, dispatch notification, and clear cart cookie
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
        'payment': request.form.get('payment', '').strip() or 'cod',
    }

    # Capture cart snapshot before clearing cookie
    cart_before = _read_cart_cookie()
    for item in cart_before:
        product = get_product_by_id(item['id'])
        if product:
            item.update({
                'name': product['name'],
                'image': product['image'],
                'price': float(product.get('price', 0)),
            })

    subtotal = sum(item.get('price', 0) * item.get('qty', 1) for item in cart_before)
    shipping = 0
    total = subtotal + shipping
    # Persist the order in the database so it appears in the customer's Order History
    saved_order = None
    if cart_before:
        try:
            saved_order = create_order(
                customer_data=order_info,
                cart_items=cart_before,
                user_id=session.get('user_id')
            )
        except Exception as err:
            current_app.logger.error(f"Failed to persist order to database: {err}")

    order_number = saved_order.order_number if saved_order else datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')

    response = make_response(render_template(
        'front/checkout.html',
        order_placed=True,
        order=saved_order,
        order_info=order_info,
        order_number=order_number,
        cart_items=cart_before,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
    ))
    # Clear the cart cookie
    response.set_cookie('cart_list', json.dumps([]), max_age=0, samesite='Lax')
    return response
