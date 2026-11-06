"""
Customer Account - Profile settings and order history for authenticated shoppers.
Owner: Workstream B (Customer, Wishlist & Reviews)
"""
from flask import render_template, session, redirect, url_for
from front import front_bp

@front_bp.get('/customer/account', endpoint='customer_account')
def customer_account():
    """
    TODO: Workstream B - Display customer profile, saved addresses, and past order history.
    Requires session.get('customer_id').
    """
    raise NotImplementedError("TODO: Workstream B - Customer Account & Order History")
