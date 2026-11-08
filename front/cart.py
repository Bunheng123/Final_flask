import json
from flask import render_template, request, make_response, redirect, url_for
from front import front_bp
from helpers.currency import khr_format, usd_format


def _resolve_product(product_id, variant_id=None):
    """
    Fetch product and pricing from database first (via stock_service),
    falling back to mock product.py if database is unseeded.
    """
    try:
        from services import stock_service
        from helpers.money import from_cents
        db_prod = stock_service.get_product_by_id(product_id)
        if db_prod:
            variant = None
            if variant_id:
                variant = stock_service.get_variant_by_id(variant_id)
            if not variant and getattr(db_prod, 'variants', None):
                variant = getattr(db_prod, 'default_variant', None) or db_prod.variants[0]

            unit_price = float(from_cents(variant.price_cents)) if variant else float(getattr(db_prod, 'price', 0.0))
            category_val = db_prod.category.name if getattr(db_prod, 'category', None) else "General"
            return {
                "id": db_prod.id,
                "variant_id": variant.id if variant else None,
                "name": db_prod.name,
                "description": db_prod.description or "",
                "image": db_prod.image or "",
                "price": unit_price,
                "category": category_val,
            }
    except Exception:
        pass

    try:
        from product import get_product_by_id as mock_get_by_id
        mock = mock_get_by_id(product_id)
        if mock:
            return {
                "id": mock["id"],
                "variant_id": None,
                "name": mock["name"],
                "description": mock.get("description", ""),
                "image": mock.get("image", ""),
                "price": float(mock.get("price", 0.0)),
                "category": mock.get("category", "General"),
            }
    except Exception:
        pass
    return None


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
                variant_id = int(item['variant_id']) if item.get('variant_id') is not None else None
            except (TypeError, ValueError):
                continue

            if qty < 1:
                qty = 1

            cart_entry = {
                "id": product_id,
                "qty": qty,
                "price": price,
            }
            if variant_id is not None:
                cart_entry["variant_id"] = variant_id
            safe_cart.append(cart_entry)

        return safe_cart
    except Exception:
        return []

# helper, accept http response and convert cart list to cookie string, set cookie to response and return response
def _write_cart_cookie(resp, cart_list):
    cookie_data = []
    for item in cart_list:
        entry = {"id": item["id"], "qty": item["qty"], "price": item.get("price", 0)}
        if item.get("variant_id") is not None:
            entry["variant_id"] = item["variant_id"]
        cookie_data.append(entry)
    resp.set_cookie('cart_list', json.dumps(cookie_data), max_age=60 * 60 * 24 * 30, samesite='Lax')
    return resp

# add product to current cart list
def _add_product_to_cart(cart_list, product, qty=1, variant_id=None):
    if qty < 1:
        qty = 1

    target_variant = variant_id or product.get('variant_id')
    for item in cart_list:
        if item['id'] == product['id'] and item.get('variant_id') == target_variant:
            item['qty'] += qty
            item['price'] = float(product['price'])
            return cart_list

    new_item = {
        "id": product['id'],
        "qty": qty,
        "price": float(product['price']),
    }
    if target_variant is not None:
        new_item["variant_id"] = target_variant
    cart_list.append(new_item)
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
    variant_id = request.args.get('variant_id')
    cart_list = _read_cart_cookie()

    if product_id:
        try:
            product_id = int(product_id)
            qty = int(qty)
            variant_id = int(variant_id) if variant_id else None
        except (TypeError, ValueError):
            product_id = None
            qty = 1
            variant_id = None

    if product_id:
        product = _resolve_product(product_id, variant_id)
        if product:
            cart_list = _add_product_to_cart(cart_list, product, qty, variant_id)
    # render the product info to cart page display
    for item in cart_list:
        product = _resolve_product(item['id'], item.get('variant_id'))
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
    variant_id = request.args.get('variant_id')

    if not product_id or qty is None:
        return {"error": "product_id and qty required"}, 400

    try:
        product_id = int(product_id)
        qty = int(qty)
        variant_id = int(variant_id) if variant_id else None
    except (TypeError, ValueError):
        return {"error": "invalid product_id or qty"}, 400

    # Read raw cookie per preference
    cart_list = _read_cart_cookie()
    product = _resolve_product(product_id, variant_id)
    if not product:
        return {"error": "product not found"}, 404

    target_variant = variant_id or product.get('variant_id')
    if qty < 1:
        cart_list = [item for item in cart_list if not (item['id'] == product_id and item.get('variant_id') == target_variant)]
    else:
        found = False
        for item in cart_list:
            if item['id'] == product_id and item.get('variant_id') == target_variant:
                item['qty'] = qty
                item['price'] = float(product['price'])
                found = True
                break

        if not found:
            new_item = {
                "id": product['id'],
                "qty": qty,
                "price": float(product['price']),
            }
            if target_variant is not None:
                new_item["variant_id"] = target_variant
            cart_list.append(new_item)

    resp = make_response({"cart_count": len(cart_list), "success": True})
    resp.headers['Content-Type'] = 'application/json'
    return _write_cart_cookie(resp, cart_list)

# remove product from cart, redirect to cart page after remove
@front_bp.get('/remove_from_cart', endpoint='remove_from_cart')
def remove_from_cart():
    product_id = request.args.get('product_id')
    variant_id = request.args.get('variant_id')
    if not product_id:
        return redirect(url_for('front_bp.cart'))

    try:
        product_id = int(product_id)
        variant_id = int(variant_id) if variant_id else None
    except (TypeError, ValueError):
        return redirect(url_for('front_bp.cart'))

    cart_list = _read_cart_cookie()
    if variant_id is not None:
        cart_list = [item for item in cart_list if not (item['id'] == product_id and item.get('variant_id') == variant_id)]
    else:
        cart_list = [item for item in cart_list if item['id'] != product_id]
    response = make_response(redirect(url_for('front_bp.cart')))
    return _write_cart_cookie(response, cart_list)