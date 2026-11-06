"""
Downloadable PDF Invoice / Receipt.
Owner: Workstream D (Coupons, Invoicing & Reports)
"""
from flask import request, session, abort, send_file
from front import front_bp

@front_bp.get('/order/<int:order_id>/invoice.pdf', endpoint='download_invoice')
def download_invoice(order_id: int):
    """
    TODO: Workstream D - Generate and stream a downloadable PDF invoice using ReportLab.
    """
    raise NotImplementedError("TODO: Workstream D - Generate PDF Invoice")
