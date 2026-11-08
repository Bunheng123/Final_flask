"""
Customer Account & Order History Portal.
Owner: Developer 5 (Customer Portal, Social Commerce & API Security) & Developer 1 (Customer Wallet)
"""
import uuid
from datetime import timedelta
from flask import (
    current_app,
    render_template,
    request,
    session,
    redirect,
    url_for,
    flash,
    abort,
)
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from front import front_bp
from services.auth_service import login_required
from helpers.auth import current_user
from helpers.upload import save_user_image, delete_profile_image, get_thumb_name
from helpers.time import utc_now, to_local
from helpers.money import format_money
from helpers.currency import khr_format
from helpers.telegram import send_telegram
from models.user import User
from models.order import Order
from models.wishlist_item import WishlistItem
from models.wallet_transaction import WalletTransaction
from services.khqr_service import generate_khqr
from services.order_service import cancel_order, cancel_order_by_customer
from services.wallet_service import create_pending_top_up


@front_bp.route('/account', methods=['GET', 'POST'], endpoint='account')
@login_required
def account():
    """
    Customer profile overview, profile editing (username, email, avatar),
    and password update with current-password verification.
    """
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action not in ('update_profile', 'change_password'):
            abort(501)

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
    total_orders_count = Order.query.filter_by(user_id=user.id).count()
    wishlist_count = WishlistItem.query.filter_by(user_id=user.id).count()
    wallet_balance_khr = getattr(user, 'wallet_balance_khr', 0)

    return render_template(
        'front/account/overview.html',
        user=user,
        orders=recent_orders,
        recent_orders=recent_orders,
        orders_count=total_orders_count,
        total_orders_count=total_orders_count,
        wishlist_count=wishlist_count,
        wallet_balance_khr=wallet_balance_khr,
        to_local=to_local,
        format_money=format_money,
        khr_format=khr_format,
        module='account',
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

    # Precalculate cancellation eligibility & remaining grace seconds for countdown
    now_utc = utc_now()
    for o in orders:
        cancellable = False
        remaining_secs = 0
        if o.status in ('pending', 'confirmed') and o.created_at:
            elapsed = (now_utc - o.created_at).total_seconds()
            if 0 <= elapsed <= 7200:
                cancellable = True
                remaining_secs = max(0, int(7200 - elapsed))
        setattr(o, 'is_cancellable', cancellable)
        setattr(o, 'remaining_seconds', remaining_secs)

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
        khr_format=khr_format,
        utc_now=utc_now,
        module='account_orders',
    )


@front_bp.route('/account/orders/<order_number>', methods=['GET', 'POST'], endpoint='account_order_detail')
@login_required
def account_order_detail(order_number: str):
    """
    Detailed itemized order receipt with shipping details, status timeline,
    live cancellation grace countdown, KHQR payment check, and item actions.
    """
    if request.method == 'POST':
        abort(501)

    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if not order and user.email:
        guest_order = Order.query.filter(
            Order.order_number == order_number,
            Order.user_id.is_(None),
            db.func.lower(Order.email) == user.email.lower()
        ).first()
        if guest_order:
            guest_order.user_id = user.id
            db.session.commit()
            order = guest_order

    if not order:
        abort(404)

    # 4-hour grace period window calculation
    grace_seconds = 4 * 3600
    if order.created_at:
        time_since_creation = (utc_now() - order.created_at).total_seconds()
        can_cancel = (order.status in ('pending', 'confirmed')) and (time_since_creation <= grace_seconds)
        time_remaining_seconds = max(0, int(grace_seconds - time_since_creation)) if can_cancel else 0
    else:
        can_cancel = False
        time_remaining_seconds = 0

    payment_ref = getattr(order, 'payment_reference', None) or getattr(order, 'bakong_hash', None)
    payment_check_url = url_for('api_bp.payment_check', payment_hash=payment_ref) if payment_ref else None

    return render_template(
        'front/account/order_detail.html',
        user=user,
        order=order,
        can_cancel=can_cancel,
        time_remaining_seconds=time_remaining_seconds,
        payment_check_url=payment_check_url,
        wallet_balance_khr=getattr(user, 'wallet_balance_khr', 0),
        to_local=to_local,
        format_money=format_money,
        khr_format=khr_format,
        module='account_order_detail',
    )


@front_bp.route('/account/orders/<order_number>/cancel', methods=['POST'], endpoint='account_order_cancel')
@front_bp.route('/account/orders/<int:order_id>/cancel', methods=['POST'], endpoint='account_order_cancel_by_id')
@front_bp.post('/account/orders/<order_number>/cancel', endpoint='account_cancel_order')
@login_required
def account_order_cancel(order_number: str = None, order_id: int = None):
    """
    Cancel a pending order within the 4-hour window, restoring inventory and refunding wallet/account.
    Supports lookup by either alphanumeric order_number or integer order_id.
    """
    user = current_user()
    if not user:
        return redirect(url_for('front_bp.login'))

    target = str(order_id) if order_id is not None else str(order_number or '')

    order = None
    if target.isdigit():
        order = Order.query.filter(
            (Order.id == int(target)) | (Order.order_number == target),
            Order.user_id == user.id
        ).first()

    if not order:
        order = Order.query.filter_by(order_number=target, user_id=user.id).first()

    if not order and user.email:
        guest_q = Order.query.filter(
            Order.user_id.is_(None),
            db.func.lower(Order.email) == user.email.lower()
        )
        if target.isdigit():
            guest_order = guest_q.filter((Order.id == int(target)) | (Order.order_number == target)).first()
        else:
            guest_order = guest_q.filter(Order.order_number == target).first()

        if guest_order:
            guest_order.user_id = user.id
            db.session.commit()
            order = guest_order

    if not order:
        abort(404)

    try:
        cancel_order_by_customer(order.id, user_id=user.id)
        db.session.commit()
        if hasattr(order, 'payment_status') and order.payment_status == 'refunded':
            flash(f"Order #{order.order_number} has been cancelled successfully. Eligible refund has been returned to your wallet.", "success")
        else:
            flash(f"Order #{order.order_number} has been cancelled successfully.", "success")
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to cancel customer order %s.", target)
        abort(500)

    # Return to order history if request was submitted from order history page
    ref = request.referrer or ''
    if 'orders' in ref and order.order_number not in ref:
        return redirect(url_for('front_bp.account_orders'))
    return redirect(url_for('front_bp.account_order_detail', order_number=order.order_number))


@front_bp.route('/account/wallet', methods=['GET', 'POST'], endpoint='account_wallet')
@login_required
def account_wallet():
    """Customer wallet dashboard and Bakong KHQR top-up."""
    user = current_user()
    if user is None:
        return redirect(url_for('front_bp.login'))

    khqr_payment = None
    payment_check_url = None

    if request.method == 'POST':
        try:
            amount_khr = int(request.form.get('amount_khr', ''))
            if amount_khr <= 0:
                raise ValueError('Enter a top-up amount greater than zero KHR.')
            reference = f'WALLET-{user.id}-{uuid.uuid4().hex[:16]}'
            khqr_payment = generate_khqr(reference=reference, amount_khr=amount_khr)
            create_pending_top_up(user.id, amount_khr, khqr_payment['reference_md5'])
            db.session.commit()
            payment_check_url = url_for(
                'api_bp.payment_check',
                payment_hash=khqr_payment['reference_md5'],
            )
        except ValueError as exc:
            db.session.rollback()
            flash(str(exc), 'error')
        except RuntimeError:
            db.session.rollback()
            current_app.logger.exception('Unable to generate wallet top-up KHQR.')
            flash('Unable to create a top-up QR right now. Please try again.', 'error')
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.exception('Unable to start customer wallet top-up.')
            abort(500)

    transactions = WalletTransaction.query.filter_by(
        user_id=user.id,
        status='completed',
    ).order_by(WalletTransaction.created_at.desc()).limit(50).all()

    pending_topup_references = [
        transaction.reference
        for transaction in WalletTransaction.query.filter_by(
            user_id=user.id,
            transaction_type='top_up',
            status='pending',
        ).all()
        if not khqr_payment or transaction.reference != khqr_payment['reference_md5']
    ]

    return render_template(
        'front/account/wallet.html',
        user=user,
        transactions=transactions,
        khqr_payment=khqr_payment,
        payment_check_url=payment_check_url,
        pending_topup_references=pending_topup_references,
        wallet_balance_khr=getattr(user, 'wallet_balance_khr', 0),
        khr_format=khr_format,
        to_local=to_local,
    )
