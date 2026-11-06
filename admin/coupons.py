"""
Admin Coupon & Promotional Campaign Management.
Owner: Workstream D (Coupons, Invoicing & Reports)
"""
from flask import render_template, request, redirect, url_for
from admin import admin_bp

@admin_bp.get('/coupons', endpoint='admin_coupons')
def admin_coupons():
    """
    TODO: Workstream D - List coupons with usage counts, discount rates, and status.
    """
    raise NotImplementedError("TODO: Workstream D - Admin Coupons Listing")

@admin_bp.route('/coupons/add', methods=['GET', 'POST'], endpoint='admin_add_coupon')
def admin_add_coupon():
    """
    TODO: Workstream D - Create new promotional coupon code.
    """
    raise NotImplementedError("TODO: Workstream D - Admin Add Coupon")
