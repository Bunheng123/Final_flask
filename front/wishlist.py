"""
Customer Wishlist ("Save for Later") Controller.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security) & Workstream B
"""
from flask import render_template, request, session, redirect, url_for, jsonify, flash
from extensions import db
from front import front_bp
from helpers.auth import login_required, current_user
from models.wishlist_item import WishlistItem
from models.product import Product
from product import get_product_by_id


def _ensure_product_in_db(product_id: int):
    prod = db.session.get(Product, product_id)
    if prod:
        return prod
    legacy = get_product_by_id(product_id)
    if not legacy:
        return None
    from models.category import Category
    cat = Category.query.first()
    if not cat:
        cat = Category(name='General', slug='general')
        db.session.add(cat)
        db.session.commit()
    prod = Product(
        id=product_id,
        name=legacy.get('name', 'Product'),
        category_id=cat.id,
        description=legacy.get('description', ''),
        image=legacy.get('image', ''),
        is_active=True
    )
    db.session.add(prod)
    db.session.commit()
    return prod


@front_bp.route('/wishlist', methods=['GET'], endpoint='wishlist')
@login_required
def wishlist():
    """
    Display current user's saved wishlist products.
    """
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login', next=request.path))

    items = WishlistItem.query.filter_by(user_id=user.id).order_by(WishlistItem.created_at.desc()).all()

    # Build rich item cards combining DB relations or catalog definitions
    wishlist_products = []
    for item in items:
        prod = item.product
        if prod:
            price = 0.0
            if prod.variants:
                price = prod.variants[0].price_cents / 100.0
            wishlist_products.append({
                "id": prod.id,
                "name": prod.name,
                "description": prod.description,
                "image": prod.image,
                "price": price,
                "category": prod.category.name if getattr(prod, 'category', None) else "Electronics",
                "item_id": item.id,
                "product_id": prod.id,
                "product": prod,
            })
        else:
            cat_prod = get_product_by_id(item.product_id)
            if cat_prod:
                wishlist_products.append({
                    "id": cat_prod.get("id"),
                    "name": cat_prod.get("name"),
                    "description": cat_prod.get("description"),
                    "image": cat_prod.get("image"),
                    "price": cat_prod.get("price", 0.0),
                    "category": cat_prod.get("category", "Electronics"),
                    "item_id": item.id,
                    "product_id": item.product_id,
                })
            else:
                wishlist_products.append({
                    "id": item.product_id,
                    "name": "Product",
                    "description": "",
                    "image": "",
                    "price": 0.0,
                    "category": "Electronics",
                    "item_id": item.id,
                    "product_id": item.product_id,
                })

    for item in items:
        if not item.product:
            legacy = get_product_by_id(item.product_id)
            if legacy:
                item._legacy_name = legacy.get('name')
                item._legacy_image = legacy.get('image')
                item._legacy_price = legacy.get('price')
                item._legacy_desc = legacy.get('description')

    return render_template(
        'front/wishlist/index.html',
        items=items,
        wishlist_products=wishlist_products,
        user=user,
        module='wishlist'
    )


@front_bp.route('/wishlist/toggle/<int:product_id>', methods=['POST'], endpoint='wishlist_toggle')
def wishlist_toggle(product_id: int):
    """
    AJAX endpoint to toggle product presence in user's wishlist.
    """
    user = current_user()
    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.is_json or
        request.accept_mimetypes.best == 'application/json'
    )

    if not user:
        if is_ajax:
            return jsonify({
                "success": False,
                "error": "Authentication required.",
                "login_url": url_for('front_bp.login', next=request.referrer or url_for('front_bp.wishlist'))
            }), 401
        flash("Please log in to add items to your wishlist.", "error")
        return redirect(url_for('front_bp.login', next=request.referrer or url_for('front_bp.wishlist')))

    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "in_wishlist": False,
                "message": "Removed from wishlist."
            }), 200
        flash("Item removed from your wishlist.", "success")
        return redirect(request.referrer or url_for('front_bp.wishlist'))
    else:
        new_item = WishlistItem(user_id=user.id, product_id=product_id)
        db.session.add(new_item)
        db.session.commit()
        if is_ajax:
            return jsonify({
                "success": True,
                "in_wishlist": True,
                "message": "Added to wishlist."
            }), 200
        flash("Item added to your wishlist.", "success")
        return redirect(request.referrer or url_for('front_bp.wishlist'))


@front_bp.route('/wishlist/add', methods=['POST'], endpoint='wishlist_add')
@login_required
def wishlist_add():
    """
    Add product to user's wishlist via form submission or JSON.
    """
    user = current_user()
    if not user:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return redirect(url_for('front_bp.login'))

    product_id = request.form.get('product_id') or (request.get_json(silent=True) or {}).get('product_id')
    if not product_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Product ID is required'}), 400
        return redirect(request.referrer or url_for('front_bp.home'))

    try:
        product_id = int(product_id)
    except (ValueError, TypeError):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid Product ID'}), 400
        return redirect(request.referrer or url_for('front_bp.home'))

    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if not existing:
        item = WishlistItem(user_id=user.id, product_id=product_id)
        db.session.add(item)
        db.session.commit()
        action = 'added'
        message = 'Added to your wishlist'
    else:
        action = 'already_exists'
        message = 'Item is already in your wishlist'

    wishlist_count = WishlistItem.query.filter_by(user_id=user.id).count()

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'action': action,
            'message': message,
            'wishlist_count': wishlist_count,
            'in_wishlist': True,
        })

    return redirect(request.referrer or url_for('front_bp.wishlist'))


@front_bp.route('/wishlist/remove', methods=['POST'], endpoint='wishlist_remove')
@login_required
def wishlist_remove():
    """
    Remove product from user's wishlist via form submission or JSON.
    """
    user = current_user()
    if not user:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return redirect(url_for('front_bp.login'))

    product_id = request.form.get('product_id') or (request.get_json(silent=True) or {}).get('product_id')
    if not product_id:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Product ID is required'}), 400
        return redirect(request.referrer or url_for('front_bp.wishlist'))

    try:
        product_id = int(product_id)
    except (ValueError, TypeError):
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Invalid Product ID'}), 400
        return redirect(request.referrer or url_for('front_bp.wishlist'))

    item = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        action = 'removed'
        message = 'Removed from wishlist'
    else:
        action = 'not_found'
        message = 'Item was not in your wishlist'

    wishlist_count = WishlistItem.query.filter_by(user_id=user.id).count()

    if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'action': action,
            'message': message,
            'wishlist_count': wishlist_count,
            'in_wishlist': False,
        })

    return redirect(request.referrer or url_for('front_bp.wishlist'))
