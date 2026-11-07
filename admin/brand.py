"""
Admin Brand Management Controller.
Owner: Developer 2 / Member 2 (Catalog, Inventory & Brand Specialist)
"""
from flask import render_template, request, redirect, url_for, flash, abort
from admin import admin_bp
from helpers.auth import admin_required
from services import stock_service


@admin_bp.route('/brands', endpoint='admin_brands')
@admin_required
def admin_brands():
    """
    Display admin listing of all brands with linked product counts.
    """
    brands = stock_service.get_all_brands()
    total_brands = len(brands)
    brands_with_products = sum(1 for b in brands if len(b.products) > 0)
    total_linked_products = sum(len(b.products) for b in brands)

    stats = {
        "total_brands": total_brands,
        "brands_with_products": brands_with_products,
        "total_linked_products": total_linked_products
    }

    return render_template(
        "admin/brand/index.html",
        brands=brands,
        stats=stats
    )


@admin_bp.route('/brand')
@admin_required
def admin_brand_alias():
    """Alias redirect for /admin/brand to /admin/brands."""
    return redirect(url_for('admin_bp.admin_brands'))


@admin_bp.route('/brands/add', methods=['GET', 'POST'], endpoint='admin_add_brand')
@admin_required
def admin_add_brand():
    """
    Create a new brand with logo URL.
    """
    if request.method == 'GET':
        return render_template("admin/brand/add.html")

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip() or None
    description = request.form.get('description', '').strip() or None
    website = request.form.get('website', '').strip() or None
    logo = request.form.get('logo', '').strip() or None

    if not name:
        flash("Brand name is required.", "danger")
        return render_template("admin/brand/add.html"), 400

    try:
        brand = stock_service.create_brand(
            name=name,
            slug=slug,
            description=description,
            logo=logo,
            website=website
        )
        flash(f"Brand '{brand.name}' created successfully.", "success")
        return redirect(url_for('admin_bp.admin_brands'))
    except Exception as e:
        flash(f"Failed to create brand: {e}", "danger")
        return render_template("admin/brand/add.html"), 400


@admin_bp.route('/brands/<int:brand_id>/edit', methods=['GET', 'POST'], endpoint='admin_edit_brand')
@admin_required
def admin_edit_brand(brand_id: int):
    """
    Edit brand details and logo URL.
    """
    brand = stock_service.get_brand_by_id(brand_id)
    if not brand:
        abort(404)

    if request.method == 'GET':
        return render_template("admin/brand/edit.html", brand=brand)

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip() or None
    description = request.form.get('description', '').strip() or None
    website = request.form.get('website', '').strip() or None
    logo_input = request.form.get('logo', '').strip()
    logo = logo_input if logo_input else None

    if not name:
        flash("Brand name is required.", "danger")
        return render_template("admin/brand/edit.html", brand=brand), 400

    try:
        stock_service.update_brand(
            brand_id=brand_id,
            name=name,
            slug=slug,
            description=description,
            logo=logo,
            website=website
        )
        flash(f"Brand '{name}' updated successfully.", "success")
        return redirect(url_for('admin_bp.admin_brands'))
    except Exception as e:
        flash(f"Failed to update brand: {e}", "danger")
        return render_template("admin/brand/edit.html", brand=brand), 400


@admin_bp.route('/brands/<int:brand_id>/delete', methods=['POST'], endpoint='admin_delete_brand')
@admin_required
def admin_delete_brand(brand_id: int):
    """
    Delete a brand.
    Contract: Safely disassociates linked products by setting product.brand_id = NULL
    before deleting the brand row, without cascading product deletion.
    """
    brand = stock_service.get_brand_by_id(brand_id)
    if not brand:
        flash("Brand not found.", "danger")
        return redirect(url_for('admin_bp.admin_brands'))

    brand_name = brand.name
    success = stock_service.delete_brand(brand_id)
    if success:
        flash(f"Brand '{brand_name}' deleted successfully. Linked products have been safely unassigned.", "success")
    else:
        flash("Failed to delete brand.", "danger")

    return redirect(url_for('admin_bp.admin_brands'))

