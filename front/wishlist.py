"""
User Wishlist - Save for later functionality for authenticated shoppers.
Owner: Workstream B (User Accounts, Wishlist & Reviews)
"""
from flask import render_template, request, session, redirect, url_for, jsonify
from front import front_bp

@front_bp.get('/wishlist', endpoint='wishlist')
def wishlist():
    """
    TODO: Workstream B - Display user's saved wishlist items.
    """
    raise NotImplementedError("TODO: Workstream B - View Wishlist")

@front_bp.post('/wishlist/add', endpoint='wishlist_add')
def wishlist_add():
    """
    TODO: Workstream B - Add product to user's wishlist.
    """
    raise NotImplementedError("TODO: Workstream B - Add Wishlist Item")

@front_bp.post('/wishlist/remove', endpoint='wishlist_remove')
def wishlist_remove():
    """
    TODO: Workstream B - Remove product from user's wishlist.
    """
    raise NotImplementedError("TODO: Workstream B - Remove Wishlist Item")
