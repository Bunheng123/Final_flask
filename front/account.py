import uuid

from flask import (
    current_app,
    flash,
    render_template,
    request,
    session,
    abort,
    redirect,
    url_for,
)
from sqlalchemy.exc import SQLAlchemyError

from front import front_bp
from services.auth_service import login_required
from helpers.auth import current_user
from helpers.currency import khr_format
from helpers.time import to_local
from extensions import db
from models.order import Order
from models.wishlist_item import WishlistItem
from models.wallet_transaction import WalletTransaction
from services.khqr_service import generate_khqr
from services.order_service import cancel_order
from services.wallet_service import create_pending_top_up


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
            wallet_balance_khr = 0
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
        khr_format=khr_format,
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
        payment_check_url=(
            url_for('api_bp.payment_check', payment_hash=order.payment_reference)
            if order.payment_reference else None
        ),
        to_local=to_local,
        khr_format=khr_format,
    )


@front_bp.post('/account/orders/<order_number>/cancel', endpoint='account_cancel_order')
@login_required
def account_cancel_order(order_number):
    user = current_user()
    if user is None:
        return redirect(url_for('front_bp.login'))
    order = Order.query.filter_by(order_number=order_number, user_id=user.id).first()
    if order is None:
        abort(404)

    try:
        cancel_order(order.id, user.id)
        db.session.commit()
        flash('Order cancelled. Any eligible refund has been returned to your wallet.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception('Unable to cancel customer order %s.', order_number)
        abort(500)
    return redirect(url_for('front_bp.account_order_detail', order_number=order_number))


@front_bp.route('/account/wallet', methods=['GET', 'POST'], endpoint='account_wallet')
@login_required
def account_wallet():
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
        wallet_balance_khr=user.wallet_balance_khr,
        khr_format=khr_format,
        to_local=to_local,
    )
