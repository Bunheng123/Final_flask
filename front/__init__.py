from flask import Blueprint

front_bp = Blueprint('front_bp', __name__, template_folder='templates')

from front import home, product, cart, checkout, auth, account, wishlist, reviews, invoice, coupon
