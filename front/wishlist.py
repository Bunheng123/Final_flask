"""
Customer Wishlist ("Save for Later") Controller.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security)
"""
from flask import render_template, request, session, redirect, url_for, jsonify, flash
from extensions import db
from front import front_bp
from helpers.auth import login_required, current_user
from models.wishlist_item import WishlistItem
from models.product import Product
from product import get_product_by_id


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
            # First active variant price if available, else default
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
                "item_id": item.id
            })
        else:
            # Fallback to static catalog dict if product table entry is stubbed
            cat_prod = get_product_by_id(item.product_id)
            if cat_prod:
                wishlist_products.append({
                    "id": cat_prod.get("id"),
                    "name": cat_prod.get("name"),
                    "description": cat_prod.get("description"),
                    "image": cat_prod.get("image"),
                    "price": cat_prod.get("price", 0.0),
                    "category": cat_prod.get("category", "Electronics"),
                    "item_id": item.id
                })

    return render_template(
        'front/wishlist/index.html',
        wishlist_products=wishlist_products,
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
    Add a product to user's wishlist via form submission or JSON.
    """
    user = current_user()
    data = request.get_json(silent=True) or request.form
    product_id = data.get('product_id')
    if not product_id:
        if request.is_json:
            return jsonify({"success": False, "error": "Product ID is required."}), 400
        flash("Invalid product.", "error")
        return redirect(request.referrer or url_for('front_bp.products'))

    try:
        product_id = int(product_id)
    except ValueError:
        if request.is_json:
            return jsonify({"success": False, "error": "Invalid Product ID."}), 400
        return redirect(request.referrer or url_for('front_bp.products'))

    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if not existing:
        item = WishlistItem(user_id=user.id, product_id=product_id)
        db.session.add(item)
        db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "in_wishlist": True, "message": "Product added to wishlist."}), 200

    flash("Product added to your wishlist.", "success")
    return redirect(request.referrer or url_for('front_bp.wishlist'))


@front_bp.route('/wishlist/remove', methods=['POST'], endpoint='wishlist_remove')
@login_required
def wishlist_remove():
    """
    Remove a product from user's wishlist via form submission or JSON.
    """
    user = current_user()
    data = request.get_json(silent=True) or request.form
    product_id = data.get('product_id')
    if not product_id:
        if request.is_json:
            return jsonify({"success": False, "error": "Product ID is required."}), 400
        return redirect(url_for('front_bp.wishlist'))

    try:
        product_id = int(product_id)
    except ValueError:
        if request.is_json:
            return jsonify({"success": False, "error": "Invalid Product ID."}), 400
        return redirect(url_for('front_bp.wishlist'))

    existing = WishlistItem.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    if request.is_json:
        return jsonify({"success": True, "in_wishlist": False, "message": "Product removed from wishlist."}), 200

    flash("Product removed from wishlist.", "success")
    return redirect(request.referrer or url_for('front_bp.wishlist'))
