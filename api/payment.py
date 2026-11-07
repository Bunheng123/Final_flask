from flask import current_app, jsonify

from api import api_bp
from services.khqr_service import get_payment_status


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

    return jsonify(status)
