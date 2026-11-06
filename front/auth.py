"""
Customer Authentication - Login, Registration, and Session management for store shoppers.
Owner: Workstream B (Customer, Wishlist & Reviews)
"""
from flask import render_template, request, redirect, url_for, session
from front import front_bp

@front_bp.route('/customer/login', methods=['GET', 'POST'], endpoint='customer_login')
def customer_login():
    """
    TODO: Workstream B - Implement customer login form and credential verification.
    Sets session['customer_id'] upon successful authentication.
    """
    raise NotImplementedError("TODO: Workstream B - Customer Login")

@front_bp.route('/customer/register', methods=['GET', 'POST'], endpoint='customer_register')
def customer_register():
    """
    TODO: Workstream B - Implement customer registration form and password hashing.
    """
    raise NotImplementedError("TODO: Workstream B - Customer Register")

@front_bp.get('/customer/logout', endpoint='customer_logout')
def customer_logout():
    """
    TODO: Workstream B - Implement customer logout and clear session['customer_id'].
    """
    raise NotImplementedError("TODO: Workstream B - Customer Logout")
