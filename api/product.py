"""
API Product Endpoints.
Owner: Workstream A / Member 2 (Catalog & Product Variants)
"""
from flask import jsonify, request
from api import api_bp
from services import stock_service
from helpers.money import from_cents


def _serialize_product(p):
    active_vars = [v for v in p.variants if v.is_active]
    default_var = next((v for v in active_vars if v.spec_name.lower() == 'default'), active_vars[0]) if active_vars else None
    price = from_cents(default_var.price_cents) if default_var else 0.0
    stock = sum(v.stock for v in active_vars) if active_vars else 0
    cat_name = p.category.name if p.category else ""
    brand_name = p.brand.name if p.brand else ""

    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "category": cat_name,
        "category_id": p.category_id,
        "brand": brand_name,
        "brand_id": p.brand_id,
        "image": p.image,
        "price": price,
        "stock": stock,
        "variants": [
            {
                "id": v.id,
                "sku": v.sku,
                "spec_name": v.spec_name,
                "price": from_cents(v.price_cents),
                "price_cents": v.price_cents,
                "stock": v.stock,
                "low_stock_threshold": v.low_stock_threshold,
                "is_active": v.is_active
            }
            for v in active_vars
        ]
    }


@api_bp.get('/products', endpoint='get_products')
@api_bp.get('/product', endpoint='get_product_list')
def api_products():
    category = request.args.get('category') or request.args.get('category_id')
    brand = request.args.get('brand') or request.args.get('brand_id')
    search = request.args.get('q') or request.args.get('search')

    db_products = stock_service.get_active_products(
        category=category,
        brand=brand,
        search=search
    )

    if db_products:
        result = [_serialize_product(p) for p in db_products]
        return jsonify({
            "success": True,
            "count": len(result),
            "data": result
        })

    # Fallback to mock catalog for unseeded environments / tests
    from product import products as mock_products
    result = mock_products
    if category:
        result = [p for p in result if str(p.get('category', '')).lower() == str(category).lower()]
    if search:
        search_lower = search.lower()
        result = [
            p for p in result
            if search_lower in p.get('name', '').lower()
            or search_lower in p.get('description', '').lower()
        ]

    return jsonify({
        "success": True,
        "count": len(result),
        "data": result
    })


@api_bp.get('/products/<int:product_id>', endpoint='get_product_by_id')
@api_bp.get('/product/<int:product_id>', endpoint='get_product_detail')
def api_product_detail(product_id: int):
    p = stock_service.get_product_by_id(product_id, only_active=True)
    if p:
        return jsonify({
            "success": True,
            "data": _serialize_product(p)
        })

    # Fallback to mock catalog
    from product import get_product_by_id as mock_get_by_id
    mock_p = mock_get_by_id(product_id)
    if not mock_p:
        return jsonify({
            "success": False,
            "error": "Product not found"
        }), 404

    return jsonify({
        "success": True,
        "data": mock_p
    })


@api_bp.get('/products/categories', endpoint='get_product_categories')
def api_product_categories():
    from models.category import Category
    db_cats = Category.query.order_by(Category.name.asc()).all()
    if db_cats:
        cats = [c.name for c in db_cats]
        return jsonify({
            "success": True,
            "categories": cats
        })

    from product import products as mock_products
    categories = sorted(list({p.get('category') for p in mock_products if p.get('category')}))
    return jsonify({
        "success": True,
        "categories": categories
    })
