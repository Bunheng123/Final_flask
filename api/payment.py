from flask import current_app, jsonify
from sqlalchemy.exc import SQLAlchemyError

from api import api_bp
from extensions import db
from models.order import Order
from models.wallet_transaction import WalletTransaction
from services.khqr_service import get_payment_status
from services.wallet_service import complete_payment, expire_payment


@api_bp.get('/payment/check/<string:payment_hash>', endpoint='payment_check')
def api_payment_check(payment_hash):
    """Low-cost KHQR payment polling endpoint for a generated md5 reference."""
    try:
        status = get_payment_status(payment_hash)
    except RuntimeError as e:
        current_app.logger.exception('Unable to check KHQR payment status.')
        return jsonify({
            'success': False,
            'status': 'check_unavailable',
            'message': str(e) or 'Payment status is temporarily unavailable.'
        }), 503

    if not status['success']:
        if status.get('status') == 'quota_exceeded':
            return jsonify(status), 429
        if status.get('status') == 'ip_restricted':
            try:
                from helpers.telegram import send_telegram
                order = Order.query.filter_by(payment_reference=payment_hash).first()
                ord_info = f"#{order.order_number}" if order else f"Ref: {payment_hash[:16]}"
                send_telegram(
                    f"⚠️ <b>KHQR Payment Submitted (AWS Cloud)</b>\n"
                    f"Customer submitted payment for <b>{ord_info}</b>.\n"
                    f"NBC Bakong blocked API check from foreign AWS IP.\n"
                    f"👉 Please verify your Bakong app and confirm in Admin Dashboard."
                )
            except Exception:
                pass
            return jsonify(status), 403
        return jsonify({
            'success': False,
            'status': status.get('status') or 'not_found',
            'message': status.get('message') or 'Payment reference not found.',
            'data': status.get('data')
        }), 404

    payment_state = status['data'].get('status')
    if payment_state == 'paid':
        try:
            settled = complete_payment(payment_hash)
            if not settled:
                has_wallet_transaction = WalletTransaction.query.filter_by(
                    reference=payment_hash
                ).first() is not None
                has_order = Order.query.filter_by(payment_reference=payment_hash).first() is not None
                if has_wallet_transaction or has_order:
                    db.session.rollback()
                    current_app.logger.error(
                        'Confirmed KHQR payment %s has an unsettled wallet/order record.',
                        payment_hash,
                    )
                    return jsonify({
                        'success': False,
                        'status': 'settlement_unavailable',
                        'message': 'Payment is confirmed but its wallet/order record could not be settled.',
                    }), 503
            db.session.commit()
        except (SQLAlchemyError, RuntimeError):
            db.session.rollback()
            current_app.logger.exception('Unable to settle KHQR payment %s.', payment_hash)
            return jsonify({
                'success': False,
                'status': 'settlement_unavailable',
                'message': 'Payment is confirmed but wallet settlement is temporarily unavailable.',
            }), 503
    elif payment_state == 'expired':
        try:
            expire_payment(payment_hash)
            db.session.commit()
        except (SQLAlchemyError, RuntimeError):
            db.session.rollback()
            current_app.logger.exception('Unable to expire KHQR payment %s.', payment_hash)
            return jsonify({
                'success': False,
                'status': 'settlement_unavailable',
                'message': 'Payment expiry settlement is temporarily unavailable.',
            }), 503

    return jsonify(status)


@api_bp.post('/payment/cancel/<string:payment_hash>', endpoint='payment_cancel')
def api_payment_cancel(payment_hash):
    """Cancel an unpaid KHQR order, restore stock, and release any reserved wallet funds."""
    from services.order_service import cancel_order
    try:
        order = Order.query.filter_by(payment_reference=payment_hash, payment_status='pending').first()
        if order:
            try:
                cancel_order(order.id, reason="Customer cancelled payment")
            except Exception:
                expire_payment(payment_hash)
        else:
            expire_payment(payment_hash)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Payment cancelled successfully.'})
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Unable to cancel payment reference %s.', payment_hash)
        return jsonify({'success': False, 'message': 'Unable to cancel payment.'}), 500

