from flask import render_template, request, session, abort, redirect, url_for, flash
from front import front_bp
from extensions import db
from models.order import Order
from models.user import User
from services.auth_service import login_required
from helpers.time import utc_now, to_local
from helpers.money import format_money
from services.order_service import (
    is_order_cancellable_by_customer,
    cancel_order_by_customer
)

@front_bp.route('/account', methods=['GET', 'POST'], endpoint='account')
@login_required
def account():
    """
    User account overview and profile management.
    """
    if request.method == 'POST':
        abort(501)

    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if not user:
        user = User.query.first() or User(username=session.get('username', 'Customer'), email=session.get('email', ''))

    recent_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(5).all() if user and user.id else []
    for o in recent_orders:
        o.is_cancellable = is_order_cancellable_by_customer(o, max_hours=4)

    user_balance = getattr(user, 'balance', 0.0)
    if hasattr(user, 'balance_cents'):
        user_balance = user.balance_cents / 100.0

    return render_template(
        'front/account/overview.html',
        user=user,
        recent_orders=recent_orders,
        user_balance=user_balance,
        to_local=to_local,
        format_money=format_money
    )


@front_bp.route('/account/orders', methods=['GET', 'POST'], endpoint='account_orders')
@login_required
def account_orders():
    """
    User order history list.
    """
    if request.method == 'POST':
        abort(501)

    user_id = session.get('user_id')
    orders = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc()).all() if user_id else []

    for order in orders:
        order.is_cancellable = is_order_cancellable_by_customer(order, max_hours=4)

    return render_template(
        'front/account/orders.html',
        orders=orders,
        to_local=to_local,
        format_money=format_money
    )


@front_bp.route('/account/orders/<order_number>', methods=['GET', 'POST'], endpoint='account_order_detail')
@login_required
def account_order_detail(order_number: str):
    """
    User order detail view with 4-hour cancellation window indicator.
    """
    if request.method == 'POST':
        abort(501)

    user_id = session.get('user_id')
    order = Order.query.filter_by(order_number=order_number, user_id=user_id).first_or_404()

    is_cancellable = is_order_cancellable_by_customer(order, max_hours=4)
    remaining_minutes = 0
    if is_cancellable and order.created_at:
        elapsed = (utc_now() - order.created_at).total_seconds()
        remaining_minutes = max(0, int((4 * 3600 - elapsed) / 60))

    return render_template(
        'front/account/order_detail.html',
        order=order,
        is_cancellable=is_cancellable,
        remaining_minutes=remaining_minutes,
        to_local=to_local,
        format_money=format_money
    )


@front_bp.post('/account/orders/<int:order_id>/cancel', endpoint='cancel_customer_order')
@login_required
def cancel_customer_order(order_id: int):
    """
    Customer self-service cancellation POST endpoint.
    Protected by CSRF token and verifies 4-hour pending window.
    """
    user_id = session.get('user_id')
    try:
        order = cancel_order_by_customer(order_id=order_id, user_id=user_id)
        flash(
            f"Order #{order.order_number} has been cancelled successfully. "
            f"100% store credit ({format_money(order.total_cents)}) has been refunded to your account.",
            "success"
        )
        return redirect(url_for('front_bp.account_order_detail', order_number=order.order_number))
    except (ValueError, PermissionError) as e:
        flash(str(e), "danger")
        return redirect(url_for('front_bp.account_orders'))
    except Exception as e:
        flash(f"Unexpected error cancelling order: {e}", "danger")
        return redirect(url_for('front_bp.account_orders'))
