"""
Admin Product Reviews Moderation Controller.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security)
"""
from flask import render_template, request, redirect, url_for, flash, abort
from extensions import db
from admin import admin_bp
from helpers.time import to_local
from models.product_review import ProductReview
from models.product import Product
from models.user import User


@admin_bp.route('/reviews', methods=['GET'], endpoint='admin_reviews')
def admin_reviews():
    """
    GET /admin/reviews
    Customer reviews moderation dashboard (approve, hide, delete spam reviews).
    Supports status filter (all, visible, hidden) and keyword search.
    """
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('q', '').strip()

    query = ProductReview.query.join(User, ProductReview.user_id == User.id).join(Product, ProductReview.product_id == Product.id)

    if status_filter == 'visible':
        query = query.filter(ProductReview.is_visible == True)
    elif status_filter == 'hidden':
        query = query.filter(ProductReview.is_visible == False)

    if search_query:
        term = f"%{search_query}%"
        query = query.filter(
            (ProductReview.comment.ilike(term)) |
            (User.username.ilike(term)) |
            (User.email.ilike(term)) |
            (Product.name.ilike(term))
        )

    reviews = query.order_by(ProductReview.created_at.desc()).all()

    # Compute quick stats
    total_count = ProductReview.query.count()
    visible_count = ProductReview.query.filter_by(is_visible=True).count()
    hidden_count = ProductReview.query.filter_by(is_visible=False).count()

    return render_template(
        'admin/reviews/index.html',
        reviews=reviews,
        status_filter=status_filter,
        search_query=search_query,
        total_count=total_count,
        visible_count=visible_count,
        hidden_count=hidden_count,
        to_local=to_local,
        module='reviews'
    )


@admin_bp.route('/reviews/<int:review_id>/toggle-visibility', methods=['POST'], endpoint='review_toggle_visibility')
def review_toggle_visibility(review_id: int):
    """
    POST /admin/reviews/<int:review_id>/toggle-visibility
    Toggle the visibility of a customer review (Hide or Publish).
    """
    review = ProductReview.query.get_or_404(review_id)
    review.is_visible = not review.is_visible
    db.session.commit()

    action = "published" if review.is_visible else "hidden"
    flash(f"Review #{review.id} has been {action}.", "success")
    return redirect(request.referrer or url_for('admin_bp.admin_reviews'))


@admin_bp.route('/reviews/<int:review_id>/delete', methods=['POST'], endpoint='review_delete')
def review_delete(review_id: int):
    """
    POST /admin/reviews/<int:review_id>/delete
    Permanently delete a spam or abusive product review.
    """
    review = ProductReview.query.get_or_404(review_id)
    review_id_copy = review.id
    db.session.delete(review)
    db.session.commit()

    flash(f"Review #{review_id_copy} was permanently deleted.", "success")
    return redirect(request.referrer or url_for('admin_bp.admin_reviews'))
