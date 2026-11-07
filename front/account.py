from flask import render_template, request, session, abort, redirect, url_for
from front import front_bp
from services.auth_service import login_required
from helpers.auth import current_user
from helpers.time import to_local
from models.order import Order
from models.wishlist_item import WishlistItem


@front_bp.route('/account', methods=['GET', 'POST'], endpoint='account')
@login_required
def account():
    """
    User account overview and profile management.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    user_id = session.get('user_id')
    if not user and user_id:
        from extensions import db
        from models.user import User
        user = db.session.get(User, user_id)
    if not user:
        class SessionUser:
            id = session.get('user_id', 0)
            username = session.get('username', 'Customer')
            email = session.get('email', 'customer@techstore.test')
            role = session.get('role', 'user')
            profile = session.get('profile')
            created_at = None
        user = SessionUser()

    uid = user.id or 0
    orders = Order.query.filter_by(user_id=uid).order_by(Order.created_at.desc()).limit(5).all() if uid else []
    orders_count = Order.query.filter_by(user_id=uid).count() if uid else 0
    wishlist_count = WishlistItem.query.filter_by(user_id=uid).count() if uid else 0

    return render_template(
        'front/account/overview.html',
        user=user,
        orders=orders,
        orders_count=orders_count,
        wishlist_count=wishlist_count,
        to_local=to_local,
    )


@front_bp.route('/account/orders', methods=['GET', 'POST'], endpoint='account_orders')
@login_required
def account_orders():
    """
    User orders list.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()

    return render_template(
        'front/account/orders.html',
        user=user,
        orders=orders,
        to_local=to_local,
    )


@front_bp.route('/account/orders/<order_number>', methods=['GET', 'POST'], endpoint='account_order_detail')
@login_required
def account_order_detail(order_number: str):
    """
    User order detail view.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first_or_404()

    return render_template(
        'front/account/order_detail.html',
        user=user,
        order=order,
        to_local=to_local,
    )
