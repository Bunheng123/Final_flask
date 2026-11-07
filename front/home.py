from front import front_bp
from flask import render_template
from services import stock_service

@front_bp.get('/')
def home():
    module = 'home'
    products_list = stock_service.get_active_products()
    categories = stock_service.get_all_categories()
    brands = stock_service.get_all_brands()
    if not products_list:
        from product import products as mock_products
        products_list = mock_products
    return render_template(
        "front/home.html",
        products=products_list,
        categories=categories,
        brands=brands,
        module=module
    )
