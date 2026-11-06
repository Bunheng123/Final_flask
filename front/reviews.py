"""
Customer Product Reviews & Star Ratings.
Owner: Workstream B (Customer, Wishlist & Reviews)
"""
from flask import request, session, redirect, url_for, jsonify
from front import front_bp

@front_bp.post('/product/<int:product_id>/review', endpoint='add_review')
def add_review(product_id: int):
    """
    TODO: Workstream B - Submit rating (1-5) and text review for a product.
    Requires customer login and verifies customer purchased product.
    """
    raise NotImplementedError("TODO: Workstream B - Submit Product Review")
