import json
from flask import render_template, request, make_response, redirect, url_for
from front import front_bp
from product import get_product_by_id
from helpers.currency import khr_format, usd_format

# helper, read cart cookie and return list of items, validate make sure qty > 1
def _read_cart_cookie():
    cart_list = request.cookies.get('cart_list')
    if not cart_list:
        return []

    try:
        parsed = json.loads(cart_list)
        safe_cart = []
        for item in parsed:
            if not isinstance(item, dict):
                continue

            try:
                product_id = int(item.get('id'))
                qty = int(item.get('qty', 1))
                price = float(item.get('price', 0))
            except (TypeError, ValueError):
                continue

            if qty < 1:
                qty = 1

            safe_cart.append({
                "id": product_id,
                "qty": qty,
                "price": price,
            })

        return safe_cart
    except Exception:
        return []

# helper, accept http response and convert cart list to cookie string, set cookie to response and return response
def _write_cart_cookie(resp, cart_list):
    cookie_data = [
        {"id": item["id"], "qty": item["qty"], "price": item.get("price", 0)}
        for item in cart_list
    ]
    resp.set_cookie('cart_list', json.dumps(cookie_data), max_age=60 * 60 * 24 * 30, samesite='Lax')
    return resp

# add product to current cart list
def _add_product_to_cart(cart_list, product, qty=1):
    if qty < 1:
        qty = 1

    for item in cart_list:
        if item['id'] == product['id']:
            item['qty'] += qty
            item['price'] = float(product['price'])
            return cart_list

    cart_list.append({
        "id": product['id'],
        "qty": qty,
        "price": float(product['price']),
    })
    return cart_list

@front_bp.app_template_filter('khr_format')
def khr_format_filter(value):
    return khr_format(value)


@front_bp.app_template_filter('usd_format')
def usd_format_filter(value):
    return usd_format(value)


# render the cart number in header
@front_bp.app_context_processor
def inject_cart_count():
    cart_items = _read_cart_cookie()
    return {
        'cart_count': len(cart_items),
        'khr_format': khr_format,
        'usd_format': usd_format,
    }

# get current cart cookie, (id,qty,price)
@front_bp.get('/cart', endpoint='cart')
def cart():
    product_id = request.args.get('product_id')
    qty = request.args.get('qty', 1)
    cart_list = _read_cart_cookie()

    if product_id:
        try:
            product_id = int(product_id)
            qty = int(qty)
        except (TypeError, ValueError):
            product_id = None
            qty = 1

    if product_id:
        product = get_product_by_id(product_id)
        if product:
            cart_list = _add_product_to_cart(cart_list, product, qty)
    # if product id exist,render the product info to cart page display
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

    response = make_response(render_template('front/cart.html', cart_items=cart_list))
    return _write_cart_cookie(response, cart_list)

# update cart item qty, if qty < 1, remove the item from cart, return json response with cart count and success status
@front_bp.get('/update_cart', endpoint='update_cart')
def update_cart():
    product_id = request.args.get('product_id')
    qty = request.args.get('qty')

    if not product_id or qty is None:
        return {"error": "product_id and qty required"}, 400

    try:
        product_id = int(product_id)
        qty = int(qty)
    except (TypeError, ValueError):
        return {"error": "invalid product_id or qty"}, 400

    # Read raw cookie per preference
    cart_raw = request.cookies.get('cart_list')
    cart_list = json.loads(cart_raw) if cart_raw else []
    product = get_product_by_id(product_id)
    if not product:
        return {"error": "product not found"}, 404

    if qty < 1:
        cart_list = [item for item in cart_list if item['id'] != product_id]
    else:
        found = False
        for item in cart_list:
            if item['id'] == product_id:
                item['qty'] = qty
                item['price'] = float(product['price'])
                found = True
                break

        if not found:
            cart_list.append({
                "id": product['id'],
                "qty": qty,
                "price": float(product['price']),
            })

    resp = make_response({"cart_count": len(cart_list), "success": True})
    resp.headers['Content-Type'] = 'application/json'
    return _write_cart_cookie(resp, cart_list)

# remove product from cart, redirect to cart page after remove
@front_bp.get('/remove_from_cart', endpoint='remove_from_cart')
def remove_from_cart():
    product_id = request.args.get('product_id')
    if not product_id:
        return redirect(url_for('front_bp.cart'))

    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        return redirect(url_for('front_bp.cart'))

    cart_list = _read_cart_cookie()
    cart_list = [item for item in cart_list if item['id'] != product_id]
    response = make_response(redirect(url_for('front_bp.cart')))
    return _write_cart_cookie(response, cart_list)