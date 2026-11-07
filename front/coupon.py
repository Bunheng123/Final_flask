"""
Coupon Preview Endpoint.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
from flask import request, jsonify, session
from front import front_bp
from services.coupon_service import validate_coupon
from helpers.money import to_cents, format_money


@front_bp.route('/coupon/preview', methods=['POST'], endpoint='coupon_preview')
def coupon_preview():
    """
    POST /coupon/preview
    Validates a coupon code against the cart subtotal and returns a live JSON preview.
    Accepts JSON body or Form data.
    """
    if request.is_json:
        data = request.get_json() or {}
        code = data.get('code', '')
        raw_subtotal = data.get('subtotal', 0)
        subtotal_cents = data.get('subtotal_cents')
    else:
        code = request.form.get('code', '')
        raw_subtotal = request.form.get('subtotal', 0)
        subtotal_cents = request.form.get('subtotal_cents')

    # Convert subtotal to cents
    if subtotal_cents is not None:
        try:
            subtotal_cents = int(subtotal_cents)
        except (ValueError, TypeError):
            subtotal_cents = to_cents(raw_subtotal)
    else:
        subtotal_cents = to_cents(raw_subtotal)

    user_id = session.get('user_id')
    is_valid, message, discount_cents = validate_coupon(code, subtotal_cents, user_id=user_id)

    new_total_cents = max(0, subtotal_cents - discount_cents)

    return jsonify({
        'success': is_valid,
        'message': message,
        'code': code.strip().upper() if code else '',
        'discount_cents': discount_cents,
        'discount_formatted': format_money(discount_cents),
        'subtotal_cents': subtotal_cents,
        'subtotal_formatted': format_money(subtotal_cents),
        'new_total_cents': new_total_cents,
        'new_total_formatted': format_money(new_total_cents)
    }), (200 if is_valid else 400)
