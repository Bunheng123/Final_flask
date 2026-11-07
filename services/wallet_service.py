"""Wallet ledger and split-payment operations using KHR integer amounts."""

from sqlalchemy import update

from extensions import db
from helpers.time import utc_now
from models.order import Order
from models.user import User
from models.wallet_transaction import WalletTransaction


def compute_split_payment(order_total_khr, wallet_balance_khr):
    """Return the wallet and KHQR split for a checkout total."""
    total = int(order_total_khr or 0)
    balance = int(wallet_balance_khr or 0)
    if total < 0 or balance < 0:
        raise ValueError('Payment totals and wallet balances cannot be negative.')

    wallet_used = min(balance, total)
    khqr_remaining = total - wallet_used
    payment_mode = (
        'wallet' if khqr_remaining == 0
        else 'khqr' if wallet_used == 0
        else 'split'
    )
    return {
        'wallet_used_khr': wallet_used,
        'khqr_remaining_khr': khqr_remaining,
        'payment_mode': payment_mode,
        'total_khr': total,
    }


def reserve_wallet_balance(wallet_balance_khr, amount_khr):
    """Validate a proposed wallet debit and return its resulting balance."""
    wallet_balance = int(wallet_balance_khr or 0)
    amount = int(amount_khr or 0)
    if amount < 0:
        raise ValueError('Wallet amount cannot be negative.')
    if wallet_balance < amount:
        raise ValueError('Insufficient wallet balance for this order.')
    return {
        'amount_khr': amount,
        'remaining_balance_khr': wallet_balance - amount,
    }


def create_pending_top_up(user_id, amount_khr, payment_reference):
    amount = int(amount_khr)
    if amount <= 0:
        raise ValueError('Top-up amount must be greater than zero.')
    user = db.session.get(User, user_id)
    if user is None:
        raise ValueError('Customer account was not found.')
    transaction = WalletTransaction(
        user_id=user_id,
        transaction_type='top_up',
        status='pending',
        amount_khr=amount,
        balance_after_khr=user.wallet_balance_khr,
        reference=payment_reference,
        description='KHQR wallet top-up',
    )
    db.session.add(transaction)
    return transaction


def reserve_wallet_for_order(user_id, amount_khr, payment_reference, order_id, pending_payment):
    """Atomically reserve wallet credit and record the order debit."""
    amount = int(amount_khr)
    if amount <= 0:
        raise ValueError('Wallet reservation must be greater than zero.')

    result = db.session.execute(
        update(User)
        .where(User.id == user_id, User.wallet_balance_khr >= amount)
        .values(wallet_balance_khr=User.wallet_balance_khr - amount)
    )
    if result.rowcount != 1:
        raise ValueError('Insufficient wallet balance for this order.')

    user = db.session.get(User, user_id)
    transaction = WalletTransaction(
        user_id=user_id,
        order_id=order_id,
        transaction_type='debit',
        status='pending' if pending_payment else 'completed',
        amount_khr=-amount,
        balance_after_khr=user.wallet_balance_khr,
        reference=payment_reference,
        description='Wallet payment for order',
    )
    db.session.add(transaction)
    return transaction


def credit_wallet(user_id, amount_khr, reference, description, transaction_type='refund', order_id=None):
    """Credit a wallet once using a unique ledger reference."""
    amount = int(amount_khr)
    if amount <= 0:
        raise ValueError('Wallet credit must be greater than zero.')
    if transaction_type not in {'top_up', 'refund'}:
        raise ValueError('Unsupported wallet credit type.')

    result = db.session.execute(
        update(User)
        .where(User.id == user_id)
        .values(wallet_balance_khr=User.wallet_balance_khr + amount)
    )
    if result.rowcount != 1:
        raise ValueError('Customer account was not found.')

    user = db.session.get(User, user_id)
    transaction = WalletTransaction(
        user_id=user_id,
        order_id=order_id,
        transaction_type=transaction_type,
        status='completed',
        amount_khr=amount,
        balance_after_khr=user.wallet_balance_khr,
        reference=reference,
        description=description,
    )
    db.session.add(transaction)
    return transaction


def complete_payment(payment_reference):
    """Apply a confirmed KHQR payment once to a top-up or pending order."""
    transaction = WalletTransaction.query.filter_by(reference=payment_reference).first()
    order = Order.query.filter_by(payment_reference=payment_reference).first()

    if transaction and transaction.transaction_type == 'top_up':
        if transaction.status == 'completed':
            return True
        if transaction.status != 'pending':
            return False
        updated = db.session.execute(
            update(WalletTransaction)
            .where(
                WalletTransaction.id == transaction.id,
                WalletTransaction.status == 'pending',
            )
            .values(status='completed')
        )
        if updated.rowcount != 1:
            return False
        balance_update = db.session.execute(
            update(User)
            .where(User.id == transaction.user_id)
            .values(wallet_balance_khr=User.wallet_balance_khr + transaction.amount_khr)
        )
        if balance_update.rowcount != 1:
            raise RuntimeError('Wallet owner was not found during top-up settlement.')
        user = db.session.get(User, transaction.user_id)
        db.session.refresh(user)
        transaction.balance_after_khr = user.wallet_balance_khr
        return True

    if order is None:
        return False

    if order.status == 'cancelled':
        if order.payment_status != 'refunded':
            external_amount_khr = order.total_khr - order.wallet_used_khr
            if external_amount_khr > 0:
                credit_wallet(
                    order.user_id,
                    external_amount_khr,
                    f'refund:late-payment:{order.order_number}',
                    'KHQR payment received after order cancellation',
                    order_id=order.id,
                )
            order.payment_status = 'refunded'
        return True

    if order.payment_status in {'paid', 'refunded'}:
        return True

    if transaction and transaction.transaction_type == 'debit':
        if transaction.status not in {'pending', 'completed'}:
            return False
        if transaction.status == 'pending':
            updated = db.session.execute(
                update(WalletTransaction)
                .where(
                    WalletTransaction.id == transaction.id,
                    WalletTransaction.status == 'pending',
                )
                .values(status='completed')
            )
            if updated.rowcount != 1:
                return False

    paid_at = utc_now()
    updated = db.session.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.status == 'pending',
            Order.payment_status == 'pending',
        )
        .values(
            status='confirmed',
            payment_status='paid',
            paid_at=paid_at,
            confirmed_at=paid_at,
        )
    )
    if updated.rowcount != 1:
        raise RuntimeError('Order payment state changed during KHQR settlement.')

    # Dispatch Telegram alert ONLY for confirmed paid orders
    try:
        from helpers.telegram import send_order_receipt
        db.session.refresh(order)
        send_order_receipt(order)
    except Exception:
        pass
    return True


def expire_payment(payment_reference):
    """Expire a pending top-up or release wallet funds reserved for a KHQR order."""
    transaction = WalletTransaction.query.filter_by(reference=payment_reference).first()
    order = Order.query.filter_by(payment_reference=payment_reference).first()

    if transaction is None and order is None:
        return

    if order and order.payment_status == 'pending':
        expired_at = utc_now()
        updated = db.session.execute(
            update(Order)
            .where(
                Order.id == order.id,
                Order.status == 'pending',
                Order.payment_status == 'pending',
            )
            .values(
                status='cancelled',
                payment_status='expired',
                cancelled_at=expired_at,
            )
        )
        if updated.rowcount != 1:
            return
    elif order:
        return

    if transaction and transaction.status == 'pending':
        updated = db.session.execute(
            update(WalletTransaction)
            .where(
                WalletTransaction.id == transaction.id,
                WalletTransaction.status == 'pending',
            )
            .values(status='reversed' if transaction.transaction_type == 'debit' else 'expired')
        )
        if updated.rowcount != 1:
            raise RuntimeError('Wallet payment state changed during KHQR expiry settlement.')
        if transaction.transaction_type == 'debit':
            amount = -transaction.amount_khr
            user = db.session.get(User, transaction.user_id)
            user.wallet_balance_khr += amount
            db.session.add(WalletTransaction(
                user_id=transaction.user_id,
                order_id=transaction.order_id,
                transaction_type='refund',
                status='completed',
                amount_khr=amount,
                balance_after_khr=user.wallet_balance_khr,
                reference=f'refund:expired:{payment_reference}',
                description='Release wallet reservation for expired KHQR payment',
            ))


def refund_order_to_wallet(order):
    """Cancel an unpaid/pending order or refund a paid order to its owner's wallet."""
    cancellable_statuses = {'pending', 'confirmed', 'cancelled'}
    cancelled_at = utc_now()
    paid_update = db.session.execute(
        update(Order)
        .where(
            Order.id == order.id,
            Order.status.in_(cancellable_statuses),
            Order.payment_status == 'paid',
        )
        .values(
            status='cancelled',
            payment_status='refunded',
            cancelled_at=cancelled_at,
        )
    )
    if paid_update.rowcount == 1:
        credit_wallet(
            order.user_id,
            order.total_khr,
            f'refund:order:{order.order_number}',
            f'Refund for cancelled order {order.order_number}',
            order_id=order.id,
        )

    else:
        pending_update = db.session.execute(
            update(Order)
            .where(
                Order.id == order.id,
                Order.status.in_(cancellable_statuses),
                Order.payment_status == 'pending',
            )
            .values(
                status='cancelled',
                payment_status='cancelled',
                cancelled_at=cancelled_at,
            )
        )
        unpaid_update = None
        if pending_update.rowcount != 1:
            unpaid_update = db.session.execute(
                update(Order)
                .where(
                    Order.id == order.id,
                    Order.status.in_(cancellable_statuses),
                    Order.payment_status == 'unpaid',
                )
                .values(
                    status='cancelled',
                    payment_status='cancelled',
                    cancelled_at=cancelled_at,
                )
            )
        if pending_update.rowcount != 1 and unpaid_update.rowcount != 1:
            raise ValueError('Only pending or confirmed orders can be cancelled.')

        if pending_update.rowcount == 1 and order.payment_reference:
            transaction = WalletTransaction.query.filter_by(
                reference=order.payment_reference,
                transaction_type='debit',
                status='pending',
            ).first()
            if transaction:
                updated = db.session.execute(
                    update(WalletTransaction)
                    .where(
                        WalletTransaction.id == transaction.id,
                        WalletTransaction.status == 'pending',
                    )
                    .values(status='reversed')
                )
                if updated.rowcount != 1:
                    raise ValueError('Payment state changed while cancelling. Please retry.')
                amount = -transaction.amount_khr
                user = db.session.get(User, order.user_id)
                user.wallet_balance_khr += amount
                db.session.add(WalletTransaction(
                    user_id=order.user_id,
                    order_id=order.id,
                    transaction_type='refund',
                    status='completed',
                    amount_khr=amount,
                    balance_after_khr=user.wallet_balance_khr,
                    reference=f'refund:cancel-reservation:{order.order_number}',
                    description=f'Released wallet reservation for order {order.order_number}',
                ))

    db.session.refresh(order)
    return order