from flask import render_template, request, session, abort
from front import front_bp
from services.auth_service import login_required

@front_bp.route('/account', methods=['GET', 'POST'], endpoint='account')
@login_required
def account():
    """
    Stub: User account overview and profile management.
    """
    if request.method == 'POST':
        abort(501)
    raise NotImplementedError("TODO: Workstream B - Account overview")

@front_bp.route('/account/orders', methods=['GET', 'POST'], endpoint='account_orders')
@login_required
def account_orders():
    """
    Stub: User orders list.
    """
    if request.method == 'POST':
        abort(501)
    raise NotImplementedError("TODO: Workstream B - Account orders")

@front_bp.route('/account/orders/<order_number>', methods=['GET', 'POST'], endpoint='account_order_detail')
@login_required
def account_order_detail(order_number: str):
    """
    Stub: User order detail view.
    """
    if request.method == 'POST':
        abort(501)
    raise NotImplementedError("TODO: Workstream B - Account order detail")
