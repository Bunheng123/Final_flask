"""
Product Reviews & Star Ratings Controller.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security)
"""
from flask import request, session, redirect, url_for, jsonify, flash, abort
from extensions import db
from front import front_bp
from helpers.auth import current_user, login_required
from helpers.time import utc_now
from models.product_review import ProductReview
from models.product import Product
from models.order import Order
from models.order_item import OrderItem
from models.product_variant import ProductVariant
from models.wishlist_item import WishlistItem


def user_has_purchased_product(user_id: int, product_id: int) -> bool:
    """
    Verified Purchase Check:
    Verify whether the authenticated customer has completed an order containing this product.
    Accepted statuses: 'confirmed', 'shipped', 'delivered'.
    """
    if not user_id or not product_id:
        return False

    # 1. Match via OrderItem -> ProductVariant -> Product
    variant_match = (
        db.session.query(OrderItem.id)
        .join(Order, OrderItem.order_id == Order.id)
        .join(ProductVariant, OrderItem.variant_id == ProductVariant.id)
        .filter(
            Order.user_id == user_id,
            ProductVariant.product_id == product_id,
            Order.status.in_(['confirmed', 'shipped', 'delivered'])
        )
        .first()
    )
    if variant_match:
        return True

    # 2. Match by Product Name or direct ID match
    prod = Product.query.get(product_id)
    if prod:
        name_match = (
            db.session.query(OrderItem.id)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(
                Order.user_id == user_id,
                OrderItem.product_name == prod.name,
                Order.status.in_(['confirmed', 'shipped', 'delivered'])
            )
            .first()
        )
        if name_match:
            return True

    return False


@front_bp.app_context_processor
def inject_review_context():
    """Inject models and helpers for template partials."""
    return {
        'ProductReview': ProductReview,
        'WishlistItem': WishlistItem,
        'user_has_purchased_product': user_has_purchased_product,
    }


@front_bp.post('/product/<int:product_id>/review', endpoint='add_review')
@login_required
def add_review(product_id: int):
    """
    Submit or update a customer rating (1-5 stars) and text review.
    Enforces Verified Purchase restriction: only purchasers can review.
    """
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login', next=url_for('front_bp.product', product_id=product_id)))

    prod = Product.query.get(product_id)
    # If not in DB table, verify if in catalog dictionary
    if not prod:
        from product import get_product_by_id
        if not get_product_by_id(product_id):
            abort(404)

    is_ajax = (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
        request.is_json or
        request.accept_mimetypes.best == 'application/json'
    )

    # Verified Purchase Restriction Check
    if not user_has_purchased_product(user.id, product_id):
        error_msg = "Only verified purchasers who have ordered this product can write a review."
        if is_ajax:
            return jsonify({"success": False, "error": error_msg}), 403
        flash(error_msg, "error")
        return redirect(url_for('front_bp.product', product_id=product_id))

    data = request.get_json(silent=True) or request.form
    raw_rating = data.get('rating')
    comment = (data.get('comment') or '').strip()

    try:
        rating = int(raw_rating)
        if not (1 <= rating <= 5):
            raise ValueError()
    except (TypeError, ValueError):
        error_msg = "Rating must be an integer between 1 and 5."
        if is_ajax:
            return jsonify({"success": False, "error": error_msg}), 400
        flash(error_msg, "error")
        return redirect(url_for('front_bp.product', product_id=product_id))

    # Check for existing review by this user on this product (Unique Constraint)
    existing_review = ProductReview.query.filter_by(user_id=user.id, product_id=product_id).first()
    if existing_review:
        existing_review.rating = rating
        existing_review.comment = comment
        existing_review.created_at = utc_now()
        existing_review.is_visible = True
        db.session.commit()
        msg = "Your review has been updated successfully."
    else:
        new_review = ProductReview(
            user_id=user.id,
            product_id=product_id,
            rating=rating,
            comment=comment,
            is_visible=True
        )
        db.session.add(new_review)
        db.session.commit()
        msg = "Thank you! Your verified review has been submitted."

    if is_ajax:
        return jsonify({
            "success": True,
            "message": msg,
            "rating": rating,
            "comment": comment
        }), 200

    flash(msg, "success")
    return redirect(url_for('front_bp.product', product_id=product_id))
