"""
Admin Product & Catalog Management Controller.
Owner: Workstream A / Member 2 (Catalog & Product Variants)
"""
from flask import render_template, request, redirect, url_for, flash, abort
from admin import admin_bp
from helpers.auth import admin_required
from helpers.money import to_cents, from_cents, format_money
from models.category import Category
from services import stock_service


@admin_bp.get('/products', endpoint='admin_products')
@admin_required
def admin_products():
    """
    Display admin products listing with variant stock and low-stock indicators.
    """
    category_id = request.args.get('category_id')
    cat_id_int = int(category_id) if category_id and category_id.isdigit() else None
    brand_id = request.args.get('brand_id')
    brand_id_int = int(brand_id) if brand_id and brand_id.isdigit() else None
    search = request.args.get('q')

    if search:
        products = stock_service.get_active_products(
            category_id=cat_id_int,
            brand_id=brand_id_int,
            search=search
        )
    else:
        products = stock_service.get_all_products(
            category_id=cat_id_int,
            brand_id=brand_id_int
        )

    categories = stock_service.get_all_categories()
    brands = stock_service.get_all_brands()
    low_stock_variants = stock_service.get_low_stock_variants()

    total_products = len(products)
    active_products = sum(1 for p in products if p.is_active)
    total_variants = sum(len(p.variants) for p in products)

    stats = {
        "total_products": total_products,
        "active_products": active_products,
        "total_variants": total_variants,
        "low_stock_count": len(low_stock_variants)
    }

    return render_template(
        "admin/products/index.html",
        products=products,
        categories=categories,
        brands=brands,
        stats=stats,
        selected_category=cat_id_int,
        selected_brand=brand_id_int,
        search_query=search or ""
    )


@admin_bp.route('/products/add', methods=['GET', 'POST'], endpoint='admin_add_product')
@admin_required
def admin_add_product():
    """
    Create a new product with an initial guaranteed 'Default' variant.
    """
    categories = stock_service.get_all_categories()
    brands = stock_service.get_all_brands()

    if request.method == 'GET':
        return render_template("admin/products/add.html", categories=categories, brands=brands)

    # Handle POST
    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id')
    brand_id = request.form.get('brand_id')
    description = request.form.get('description', '').strip()
    image = request.form.get('image', '').strip()

    # Initial variant fields
    sku = request.form.get('sku', '').strip() or None
    spec_name = request.form.get('spec_name', 'Default').strip() or "Default"
    price_val = request.form.get('price', '0')
    stock_val = request.form.get('stock', '0')
    cost_val = request.form.get('cost_price')
    threshold_val = request.form.get('low_stock_threshold')

    if not name:
        flash("Product name is required.", "danger")
        return render_template("admin/products/add.html", categories=categories, brands=brands), 400

    if not category_id or not str(category_id).isdigit():
        flash("Valid category selection is required.", "danger")
        return render_template("admin/products/add.html", categories=categories, brands=brands), 400

    try:
        price_cents = to_cents(price_val)
        stock = max(0, int(stock_val)) if stock_val else 0
        cost_price_cents = to_cents(cost_val) if cost_val else None
        low_stock_threshold = int(threshold_val) if threshold_val and str(threshold_val).isdigit() else None
        brand_id_int = int(brand_id) if brand_id and str(brand_id).isdigit() else None

        product = stock_service.create_product(
            name=name,
            category_id=int(category_id),
            brand_id=brand_id_int,
            description=description or None,
            image=image or None,
            sku=sku,
            spec_name=spec_name,
            price_cents=price_cents,
            stock=stock,
            cost_price_cents=cost_price_cents,
            low_stock_threshold=low_stock_threshold,
            is_active=True
        )
        flash(f"Product '{product.name}' created successfully with Default variant.", "success")
        return redirect(url_for('admin_bp.admin_products'))
    except Exception as e:
        flash(f"Failed to create product: {e}", "danger")
        return render_template("admin/products/add.html", categories=categories, brands=brands), 400


@admin_bp.route('/products/<int:product_id>/variants', methods=['GET', 'POST'], endpoint='admin_product_variants')
@admin_required
def admin_product_variants(product_id: int):
    """
    Manage variants, specs, SKUs, and stock levels for a product.
    """
    product = stock_service.get_product_by_id(product_id)
    if not product:
        abort(404)

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'update_product':
            name = request.form.get('name', '').strip()
            category_id = request.form.get('category_id')
            description = request.form.get('description', '').strip()
            image = request.form.get('image', '').strip()
            is_active = request.form.get('is_active') == '1'

            try:
                cat_id = int(category_id) if category_id and str(category_id).isdigit() else None
                stock_service.update_product(
                    product_id=product_id,
                    name=name or None,
                    category_id=cat_id,
                    description=description,
                    image=image,
                    is_active=is_active
                )
                flash("Product details updated successfully.", "success")
            except Exception as e:
                flash(f"Update failed: {e}", "danger")

        return redirect(url_for('admin_bp.admin_product_variants', product_id=product_id))

    categories = Category.query.order_by(Category.name.asc()).all()
    variants = stock_service.get_variants_by_product_id(product_id)
    return render_template(
        "admin/products/variants.html",
        product=product,
        variants=variants,
        categories=categories
    )


@admin_bp.route('/products/<int:product_id>/delete', methods=['POST'], endpoint='admin_delete_product')
@admin_required
def admin_delete_product(product_id: int):
    """
    Delete a product and all associated variants.
    """
    success = stock_service.delete_product(product_id)
    if success:
        flash("Product deleted successfully.", "success")
    else:
        flash("Product not found.", "danger")
    return redirect(url_for('admin_bp.admin_products'))


@admin_bp.route('/products/<int:product_id>/toggle-status', methods=['POST'], endpoint='admin_toggle_product_status')
@admin_required
def admin_toggle_product_status(product_id: int):
    """
    Toggle active / inactive state of a product.
    """
    product = stock_service.get_product_by_id(product_id)
    if not product:
        abort(404)

    stock_service.update_product(product_id, is_active=not product.is_active)
    status_str = "activated" if not product.is_active else "deactivated"
    flash(f"Product has been {status_str}.", "info")
    return redirect(url_for('admin_bp.admin_products'))


@admin_bp.route('/products/<int:product_id>/edit', methods=['GET', 'POST'], endpoint='admin_edit_product')
@admin_required
def admin_edit_product(product_id: int):
    """
    GET/POST /admin/products/<id>/edit
    Full base Product edit (name, category, brand, description, image, is_active).
    """
    product = stock_service.get_product_by_id(product_id)
    if not product:
        abort(404)

    categories = stock_service.get_all_categories()
    brands = stock_service.get_all_brands()

    if request.method == 'GET':
        return render_template(
            "admin/products/edit.html",
            product=product,
            categories=categories,
            brands=brands
        )

    name = request.form.get('name', '').strip()
    category_id = request.form.get('category_id')
    brand_id = request.form.get('brand_id')
    description = request.form.get('description', '').strip()
    image = request.form.get('image', '').strip()
    is_active = request.form.get('is_active') in ('1', 'true', 'True', True, 'on')

    if not name:
        flash("Product name is required.", "danger")
        return render_template("admin/products/edit.html", product=product, categories=categories, brands=brands), 400

    if not category_id or not str(category_id).isdigit():
        flash("Valid category selection is required.", "danger")
        return render_template("admin/products/edit.html", product=product, categories=categories, brands=brands), 400

    try:
        brand_id_int = int(brand_id) if brand_id and str(brand_id).isdigit() else None
        stock_service.update_product(
            product_id=product_id,
            name=name,
            category_id=int(category_id),
            brand_id=brand_id_int,
            description=description or None,
            image=image or None,
            is_active=is_active
        )
        flash(f"Product '{name}' updated successfully.", "success")
        return redirect(url_for('admin_bp.admin_products'))
    except Exception as e:
        flash(f"Failed to update product: {e}", "danger")
        return render_template("admin/products/edit.html", product=product, categories=categories, brands=brands), 400


@admin_bp.route('/products/set-test-prices', methods=['POST'], endpoint='admin_set_test_prices')
@admin_required
def admin_set_test_prices():
    """
    POST /admin/products/set-test-prices
    Set all product variant prices to 1¢ / 2¢ ($0.01 / $0.02) for checkout testing.
    """
    cents_param = request.form.get('cents')
    cents_val = int(cents_param) if cents_param and cents_param.isdigit() else None
    count = stock_service.set_test_prices_cents(cents=cents_val)
    flash(f"Successfully updated {count} variant price(s) to 1¢ / 2¢ ($0.01 - $0.02) test prices.", "success")
    return redirect(url_for('admin_bp.admin_products'))


# ==========================================
# Category Management Controllers
# ==========================================

@admin_bp.route('/categories', endpoint='admin_categories')
@admin_required
def admin_categories():
    """
    Display admin listing of all product categories.
    """
    categories = stock_service.get_all_categories()
    total_categories = len(categories)
    categories_with_products = sum(1 for c in categories if len(c.products) > 0)
    total_linked_products = sum(len(c.products) for c in categories)

    stats = {
        "total_categories": total_categories,
        "categories_with_products": categories_with_products,
        "total_linked_products": total_linked_products
    }

    return render_template(
        "admin/products/categories.html",
        categories=categories,
        stats=stats
    )


@admin_bp.route('/category')
@admin_required
def admin_category_alias():
    """Alias redirect for /admin/category to /admin/categories."""
    return redirect(url_for('admin_bp.admin_categories'))


@admin_bp.route('/categories/add', methods=['GET', 'POST'], endpoint='admin_add_category')
@admin_required
def admin_add_category():
    """
    Create a new product category.
    """
    if request.method == 'GET':
        return render_template("admin/products/category_form.html", action="add")

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip() or None

    if not name:
        flash("Category name is required.", "danger")
        return render_template("admin/products/category_form.html", action="add"), 400

    try:
        cat = stock_service.create_category(name=name, slug=slug)
        flash(f"Category '{cat.name}' created successfully.", "success")
        return redirect(url_for('admin_bp.admin_categories'))
    except Exception as e:
        flash(f"Failed to create category: {e}", "danger")
        return render_template("admin/products/category_form.html", action="add"), 400


@admin_bp.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'], endpoint='admin_edit_category')
@admin_required
def admin_edit_category(category_id: int):
    """
    Edit an existing category's name and slug.
    """
    category = stock_service.get_category_by_id(category_id)
    if not category:
        abort(404)

    if request.method == 'GET':
        return render_template("admin/products/category_form.html", action="edit", category=category)

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip() or None

    if not name:
        flash("Category name is required.", "danger")
        return render_template("admin/products/category_form.html", action="edit", category=category), 400

    try:
        stock_service.update_category(category_id=category_id, name=name, slug=slug)
        flash(f"Category '{name}' updated successfully.", "success")
        return redirect(url_for('admin_bp.admin_categories'))
    except Exception as e:
        flash(f"Failed to update category: {e}", "danger")
        return render_template("admin/products/category_form.html", action="edit", category=category), 400


@admin_bp.route('/categories/<int:category_id>/delete', methods=['POST'], endpoint='admin_delete_category')
@admin_required
def admin_delete_category(category_id: int):
    """
    Delete a category. If products are linked, requires target reassign_to_id.
    """
    category = stock_service.get_category_by_id(category_id)
    if not category:
        flash("Category not found.", "danger")
        return redirect(url_for('admin_bp.admin_categories'))

    reassign_to_id = request.form.get('reassign_to_id')
    reassign_int = int(reassign_to_id) if reassign_to_id and reassign_to_id.isdigit() else None
    cat_name = category.name

    try:
        stock_service.delete_category(category_id=category_id, reassign_to_id=reassign_int)
        flash(f"Category '{cat_name}' deleted successfully.", "success")
    except Exception as e:
        flash(f"Failed to delete category: {e}", "danger")

    return redirect(url_for('admin_bp.admin_categories'))
