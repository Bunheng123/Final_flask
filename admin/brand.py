"""
Admin Brand Management Controller.
Owner: Developer 2 / Member 2 (Catalog, Inventory & Brand Specialist)
"""
import os
import time
from flask import render_template, request, redirect, url_for, flash, abort, current_app
from werkzeug.utils import secure_filename

from admin import admin_bp
from helpers.auth import admin_required
from helpers.upload import allowed_file
from services import stock_service


def _handle_logo_upload(file, fallback_logo_url: str = None) -> str:
    """
    Handle logo file upload or fallback to a provided image URL.
    """
    if file and file.filename:
        if not allowed_file(file.filename):
            raise ValueError("Invalid image file format. Allowed: png, jpg, jpeg, gif, webp.")
        clean_name = secure_filename(file.filename)
        timestamp = int(time.time())
        saved_name = f"brand_{timestamp}_{clean_name}"
        brand_folder = os.path.join(current_app.root_path, 'static', 'images', 'brand')
        os.makedirs(brand_folder, exist_ok=True)
        file.save(os.path.join(brand_folder, saved_name))
        return f"images/brand/{saved_name}"

    if fallback_logo_url:
        return fallback_logo_url.strip()

    return None


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
    Create a new brand with optional logo upload or URL fallback.
    """
    if request.method == 'GET':
        return render_template("admin/brand/add.html")

    name = request.form.get('name', '').strip()
    slug = request.form.get('slug', '').strip() or None
    description = request.form.get('description', '').strip() or None
    website = request.form.get('website', '').strip() or None
    logo_url = request.form.get('logo', '').strip() or None
    logo_file = request.files.get('logo_file')

    if not name:
        flash("Brand name is required.", "danger")
        return render_template("admin/brand/add.html"), 400

    try:
        logo = _handle_logo_upload(logo_file, fallback_logo_url=logo_url)
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
    Edit brand details and update or retain logo.
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
    logo_url = request.form.get('logo', '').strip()
    logo_file = request.files.get('logo_file')

    if not name:
        flash("Brand name is required.", "danger")
        return render_template("admin/brand/edit.html", brand=brand), 400

    try:
        if logo_file and logo_file.filename:
            logo = _handle_logo_upload(logo_file)
        elif logo_url:
            logo = logo_url
        elif 'clear_logo' in request.form:
            logo = None
        else:
            logo = brand.logo

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
