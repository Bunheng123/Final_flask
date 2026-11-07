"""
Storefront Product Catalog & Detail Controller.
Owner: Workstream A / Member 2 (Catalog & Product Variants)
"""
from flask import render_template, abort, request
from front import front_bp
from services import stock_service
from helpers.highlight import highlight_query


@front_bp.app_template_filter('highlight_query')
def highlight_query_filter(value, query=""):
    """Jinja2 filter to safely highlight matched search queries."""
    return highlight_query(value, query)


@front_bp.app_context_processor
def inject_highlight_helper():
    """Inject highlight_query into template context for direct function call syntax."""
    return {'highlight_query': highlight_query}


@front_bp.get('/products', endpoint='products')
def all_products():
    """
    Storefront product listing view.
    Delegates querying to stock_service and supports category, brand, and live search filters.
    """
    module = 'products'
    category = request.args.get('category') or request.args.get('category_id')
    brand = request.args.get('brand') or request.args.get('brand_id')
    search = request.args.get('q') or request.args.get('search')

    products_list = stock_service.get_active_products(
        category=category,
        brand=brand,
        search=search
    )
    categories = stock_service.get_all_categories()
    brands = stock_service.get_all_brands()

    if not products_list and not category and not brand and not search:
        # Fallback to mock catalog if database has not been seeded
        from product import products as mock_products
        products_list = mock_products

    return render_template(
        "front/products.html",
        products=products_list,
        categories=categories,
        brands=brands,
        selected_category=category or "",
        selected_brand=brand or "",
        search_query=search or "",
        q=search or "",
        module=module
    )


@front_bp.get('/product/<int:product_id>', endpoint='product')
def product(product_id: int):
    """
    Storefront product detail view.
    Loads database-backed product and active variants with formatted pricing.
    """
    module = 'product_detail'
    product_item = stock_service.get_product_by_id(product_id, only_active=True)
    if product_item is None:
        # Fallback to mock catalog for backwards-compatibility with unseeded test fixtures
        from product import get_product_by_id as mock_get_by_id, get_product_by_category as mock_get_by_cat
        product_item = mock_get_by_id(product_id)
        if product_item is None:
            abort(404)
        related_product = mock_get_by_cat(product_item.get('category'))
        return render_template(
            "front/product.html",
            product=product_item,
            variants=[],
            related_product=related_product,
            module=module
        )

    active_variants = [v for v in product_item.variants if v.is_active]
    related_list = stock_service.get_active_products(category_id=product_item.category_id)
    related_products = [p for p in related_list if p.id != product_item.id][:4]

    return render_template(
        "front/product.html",
        product=product_item,
        variants=active_variants,
        related_product=related_products,
        module=module
    )
