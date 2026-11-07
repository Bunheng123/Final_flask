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
    except RuntimeError:
        current_app.logger.exception('Unable to check KHQR payment status.')
        return jsonify({
            'success': False,
            'status': 'check_unavailable',
            'message': 'Payment status is temporarily unavailable.'
        }), 503

    if not status['success']:
        return jsonify({
            'success': False,
            'status': 'not_found',
            'message': 'Payment reference not found.'
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
