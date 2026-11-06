"""
Coupon Preview Endpoint Stub.
Owner: Workstream D / M4 (Coupons, Invoicing & Reports)
"""
from flask import request, abort, jsonify
from front import front_bp

@front_bp.route('/coupon/preview', methods=['POST'], endpoint='coupon_preview')
def coupon_preview():
    """
    POST /coupon/preview
    Validates a coupon code against subtotal and returns discount preview.
    TODO: Workstream D - Implement coupon preview calculation.
    """
    abort(501)
