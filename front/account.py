"""
Customer Account & Order History Portal.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security) & Workstream C (Orders)
"""
from datetime import timedelta
from flask import render_template, request, session, redirect, url_for, flash, abort
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from front import front_bp
from models.order import Order
from models.user import User
from helpers.auth import login_required, current_user
from helpers.upload import save_user_image, delete_profile_image, get_thumb_name
from helpers.time import utc_now, to_local
from helpers.money import format_money
from helpers.telegram import send_telegram
from services.order_service import (
    is_order_cancellable_by_customer,
    cancel_order_by_customer
)


@front_bp.route('/account', methods=['GET', 'POST'], endpoint='account')
@login_required
def account():
    """
    Customer profile overview, profile editing (username, email, avatar),
    and password update with current-password verification.
    """
    if request.method == 'POST':
        action = request.form.get('action')
        if action not in ('update_profile', 'change_password'):
            abort(501)

        user = current_user()
        if not user:
            return redirect(url_for('front_bp.login'))

        if action == 'update_profile':
            username = request.form.get('username', '').strip()
            email = request.form.get('email', '').strip().lower()

            if not username or not email:
                flash("Username and email cannot be empty.", "error")
                return redirect(url_for('front_bp.account'))

            # Check duplicate username
            existing_user = User.query.filter(
                db.func.lower(User.username) == username.lower(),
                User.id != user.id
            ).first()
            if existing_user:
                flash("Username is already taken by another account.", "error")
                return redirect(url_for('front_bp.account'))

            # Check duplicate email
            existing_email = User.query.filter(
                db.func.lower(User.email) == email,
                User.id != user.id
            ).first()
            if existing_email:
                flash("Email is already in use by another account.", "error")
                return redirect(url_for('front_bp.account'))

            # Handle avatar image upload
            profile_file = request.files.get('profile')
            if profile_file and profile_file.filename:
                saved_filename = save_user_image(profile_file, user.id, username)
                if saved_filename:
                    if user.profile:
                        delete_profile_image(user.profile)
                    user.profile = saved_filename
                    session['profile'] = saved_filename
                    session['profile_image'] = f"images/user/{get_thumb_name(saved_filename)}"
                else:
                    flash("Invalid image file format. Allowed: PNG, JPG, JPEG, WEBP, GIF.", "error")
                    return redirect(url_for('front_bp.account'))

            user.username = username
            user.email = email
            db.session.commit()

            session['username'] = user.username
            session['email'] = user.email
            flash("Profile updated successfully.", "success")
            return redirect(url_for('front_bp.account'))

        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not current_password or not new_password or not confirm_password:
                flash("All password fields are required.", "error")
                return redirect(url_for('front_bp.account'))

            if not check_password_hash(user.password, current_password):
                flash("Current password is incorrect.", "error")
                return redirect(url_for('front_bp.account'))

            if len(new_password) < 8:
                flash("New password must be at least 8 characters long.", "error")
                return redirect(url_for('front_bp.account'))

            if new_password != confirm_password:
                flash("Passwords do not match.", "error")
                return redirect(url_for('front_bp.account'))

            user.password = generate_password_hash(new_password)
            db.session.commit()

            flash("Password updated successfully.", "success")
            return redirect(url_for('front_bp.account'))

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    # Auto-associate orphan guest orders placed with this user's email
    if user.email:
        orphan_orders = Order.query.filter(
            Order.user_id.is_(None),
            db.func.lower(Order.email) == user.email.lower()
        ).all()
        if orphan_orders:
            for orphan in orphan_orders:
                orphan.user_id = user.id
            db.session.commit()

    # Fetch recent orders summary for customer overview
    recent_orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(5).all()
    for o in recent_orders:
        o.is_cancellable = is_order_cancellable_by_customer(o, max_hours=4)
    total_orders_count = Order.query.filter_by(user_id=user.id).count()

    return render_template(
        'front/account/index.html',
        user=user,
        recent_orders=recent_orders,
        total_orders_count=total_orders_count,
        to_local=to_local,
        format_money=format_money,
        module='account'
    )


@front_bp.route('/account/orders', methods=['GET', 'POST'], endpoint='account_orders')
@login_required
def account_orders():
    """
    List of orders placed by the current customer with filters, search, and status counters.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    # Auto-associate orphan guest orders placed with this user's email
    if user.email:
        orphan_orders = Order.query.filter(
            Order.user_id.is_(None),
            db.func.lower(Order.email) == user.email.lower()
        ).all()
        if orphan_orders:
            for orphan in orphan_orders:
                orphan.user_id = user.id
            db.session.commit()

    status_filter = request.args.get('status', 'all').lower()
    search_q = request.args.get('q', '').strip()

    query = Order.query.filter_by(user_id=user.id)
    if status_filter in ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled'):
        query = query.filter_by(status=status_filter)
    if search_q:
        query = query.filter(Order.order_number.ilike(f"%{search_q}%"))

    orders = query.order_by(Order.created_at.desc()).all()
    for o in orders:
        o.is_cancellable = is_order_cancellable_by_customer(o, max_hours=4)

    # User statistics for overview metric cards
    all_user_orders = Order.query.filter_by(user_id=user.id).all()
    total_spent_cents = sum((o.total_cents or 0) for o in all_user_orders if o.status != 'cancelled')
    pending_count = sum(1 for o in all_user_orders if o.status == 'pending')
    delivered_count = sum(1 for o in all_user_orders if o.status == 'delivered')
    confirmed_count = sum(1 for o in all_user_orders if o.status in ('confirmed', 'shipped'))

    return render_template(
        'front/account/orders.html',
        user=user,
        orders=orders,
        status_filter=status_filter,
        search_q=search_q,
        total_spent_cents=total_spent_cents,
        total_orders_count=len(all_user_orders),
        pending_count=pending_count,
        delivered_count=delivered_count,
        confirmed_count=confirmed_count,
        to_local=to_local,
        format_money=format_money,
        utc_now=utc_now,
        module='account_orders'
    )


@front_bp.route('/account/orders/<order_number>', methods=['GET', 'POST'], endpoint='account_order_detail')
@login_required
def account_order_detail(order_number: str):
    """
    Detailed itemized order receipt with shipping details, status timeline,
    live cancellation grace countdown, and item actions.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order and user.email:
        # Check if order was placed as guest with the customer's registered email
        guest_order = Order.query.filter(
            Order.order_number == order_number,
            Order.user_id.is_(None),
            db.func.lower(Order.email) == user.email.lower()
        ).first()
        if guest_order:
            guest_order.user_id = user.id
            db.session.commit()
            order = guest_order

    if not order and str(order_number).isdigit():
        order = db.session.get(Order, int(order_number))
        if order and order.user_id != user.id and order.email.lower() != user.email.lower():
            order = None

    if not order:
        abort(404)

    # Strict customer tenant scoping: only allow owner to cancel
    if order.user_id != user.id and (not user.email or (order.email or '').lower() != user.email.lower()):
        abort(404)

    is_cancellable = is_order_cancellable_by_customer(order, max_hours=4)
    remaining_minutes = 0
    time_remaining_seconds = 0
    if is_cancellable and order.created_at:
        elapsed = (utc_now() - order.created_at).total_seconds()
        remaining_minutes = max(0, int((4 * 3600 - elapsed) / 60))
        time_remaining_seconds = max(0, int(4 * 3600 - elapsed))

    return render_template(
        'front/account/order_detail.html',
        user=user,
        order=order,
        can_cancel=is_cancellable,
        is_cancellable=is_cancellable,
        remaining_minutes=remaining_minutes,
        time_remaining_seconds=time_remaining_seconds,
        to_local=to_local,
        format_money=format_money,
        module='account_order_detail'
    )


def _process_order_cancellation(order_identifier):
    """Internal helper to process order cancellation by order_id or order_number."""
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    order = None
    if str(order_identifier).isdigit():
        order = db.session.get(Order, int(order_identifier))
    if not order:
        order = Order.query.filter_by(order_number=str(order_identifier)).first()

    if not order:
        abort(404)

    # Strict customer tenant scoping: only allow owner to cancel
    if order.user_id != user.id and (not user.email or (order.email or '').lower() != user.email.lower()):
        abort(404)

    try:
        cancelled_order = cancel_order_by_customer(order_id=order.id, user_id=user.id)
        flash(
            f"Order #{cancelled_order.order_number} has been cancelled successfully. "
            f"100% store credit ({format_money(cancelled_order.total_cents)}) has been refunded to your account.",
            "success"
        )
        return redirect(url_for('front_bp.account_order_detail', order_number=cancelled_order.order_number))
    except (ValueError, PermissionError) as e:
        flash(str(e), "danger")
        return redirect(url_for('front_bp.account_orders'))
    except Exception as e:
        flash(f"Unexpected error cancelling order: {e}", "danger")
        return redirect(url_for('front_bp.account_orders'))


@front_bp.route('/account/orders/<order_number>/cancel', methods=['POST'], endpoint='account_order_cancel')
@login_required
def account_order_cancel(order_number: str):
    """Cancel a pending order within the 4-hour window by order_number."""
    return _process_order_cancellation(order_number)


@front_bp.post('/account/orders/<int:order_id>/cancel', endpoint='cancel_customer_order')
@login_required
def cancel_customer_order(order_id: int):
    """Customer self-service cancellation POST endpoint by order_id."""
    return _process_order_cancellation(order_id)
