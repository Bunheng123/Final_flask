"""
User Wishlist - Save for later functionality for authenticated shoppers.
Owner: Workstream B (User Accounts, Wishlist & Reviews)
"""
import re
from flask import render_template, request, session, redirect, url_for, jsonify
from front import front_bp
from extensions import db
from helpers.auth import login_required, current_user
from models.wishlist_item import WishlistItem
from models.product import Product
from models.category import Category
from models.product_variant import ProductVariant
from product import get_product_by_id


def _ensure_product_in_db(product_id: int):
    """Ensure product and at least one variant exist in DB for foreign key constraint."""
    prod = Product.query.get(product_id)
    if prod:
        return prod
    legacy = get_product_by_id(product_id)
    if not legacy:
        return None

    cat_name = legacy.get('category', 'General')
    cat = Category.query.filter_by(name=cat_name).first()
    if not cat:
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', cat_name.lower()).strip('-')
        cat = Category(name=cat_name, slug=slug)
        db.session.add(cat)
        db.session.flush()

    prod = Product(
        id=product_id,
        category_id=cat.id,
        name=legacy.get('name', f'Product {product_id}'),
        description=legacy.get('description', ''),
        image=legacy.get('image', ''),
        is_active=True,
    )
    db.session.add(prod)
    db.session.flush()

    variant = ProductVariant(
        product_id=prod.id,
        sku=f"SKU-{prod.id}-DEF",
        spec_name="Default",
        price_cents=int(float(legacy.get('price', 0)) * 100),
        stock=int(legacy.get('stock', 10)),
        is_active=True,
    )
    db.session.add(variant)
    db.session.flush()
    return prod


@front_bp.get('/wishlist', endpoint='wishlist')
@login_required
def wishlist():
    """
    Display user's saved wishlist items.
    """
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    items = WishlistItem.query.filter_by(user_id=user.id).order_by(WishlistItem.created_at.desc()).all()
    for item in items:
        if not item.product or not item.product.variants:
            legacy = get_product_by_id(item.product_id)
            if legacy:
                item._legacy_name = legacy.get('name')
                item._legacy_image = legacy.get('image')
                item._legacy_price = legacy.get('price')
                item._legacy_desc = legacy.get('description')

    return render_template('front/wishlist/index.html', items=items, user=user)


@front_bp.post('/wishlist/add', endpoint='wishlist_add')
@login_required
def wishlist_add():
    """
    Add product to user's wishlist.
    Supports both standard POST form and AJAX JSON requests.
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

    prod = _ensure_product_in_db(product_id)
    if not prod:
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Product not found'}), 404
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


@front_bp.post('/wishlist/remove', endpoint='wishlist_remove')
@login_required
def wishlist_remove():
    """
    Remove product from user's wishlist.
    Supports both standard POST form and AJAX JSON requests.
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
