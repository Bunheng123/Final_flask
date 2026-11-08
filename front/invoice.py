"""
Downloadable PDF Invoice / Receipt.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
from flask import request, session, abort, send_file
from extensions import db
from front import front_bp
from models.order import Order
from services.invoice_service import generate_invoice_pdf


@front_bp.get('/order/<int:order_id>/invoice.pdf', endpoint='download_invoice')
@front_bp.get('/invoice/<string:order_identifier>/pdf', endpoint='invoice_pdf')
def download_invoice(order_id: int = None, order_identifier: str = None):
    """
    GET /order/<int:order_id>/invoice.pdf
    GET /invoice/<string:order_identifier>/pdf
    Generates and streams a downloadable PDF invoice using ReportLab.
    """
    lookup_id = order_id or order_identifier
    if not lookup_id:
        abort(404)

    order = None
    if isinstance(lookup_id, int) or (isinstance(lookup_id, str) and lookup_id.isdigit()):
        order = db.session.get(Order, int(lookup_id))

    if not order:
        order = Order.query.filter_by(order_number=str(lookup_id)).first()

    if not order:
        abort(404, description=f"Order '{lookup_id}' not found.")

    # Access control: Admins can view any invoice; logged-in users can only view their own
    current_user_id = session.get('user_id')
    current_role = session.get('role')

    if current_role != 'admin' and order.user_id is not None:
        if current_user_id != order.user_id:
            abort(403, description="You are not authorized to view this invoice.")

    try:
        pdf_buffer = generate_invoice_pdf(order.id)
    except Exception as e:
        abort(500, description=f"Failed to generate invoice PDF: {str(e)}")

    filename = f"Invoice-{order.order_number}.pdf"
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=filename
    )
