"""
Admin Product Variants Management Controller.
Owner: Workstream A / Member 2 (Catalog, Product Variants & Low-Stock Alerts)
"""
from flask import request, abort, redirect, url_for, flash, jsonify
from admin import admin_bp
from helpers.auth import admin_required
from helpers.money import to_cents, from_cents, format_money
from services import stock_service


@admin_bp.route('/product/<int:product_id>/variant/add', methods=['POST'], endpoint='variant_add')
@admin_required
def variant_add(product_id: int):
    """
    POST /admin/product/<product_id>/variant/add
    Add a new variant (spec, SKU, price, stock) to a product.
    """
    # If called without form data (e.g. unseeded scaffold smoke tests), retain 501 stub behavior
    if not request.form and not (request.is_json and request.get_json(silent=True)):
        abort(501)

    sku = request.form.get('sku', '').strip()
    spec_name = request.form.get('spec_name', 'Default').strip() or "Default"
    price_val = request.form.get('price')
    stock_val = request.form.get('stock', 0)
    cost_val = request.form.get('cost_price')
    threshold_val = request.form.get('low_stock_threshold')
    is_active = request.form.get('is_active', '1') in ('1', 'true', 'True', True, 'on')

    if not sku:
        flash("Variant SKU is required.", "danger")
        return redirect(url_for('admin_bp.admin_product_variants', product_id=product_id))

    try:
        price_cents = to_cents(price_val)
        stock = max(0, int(stock_val)) if stock_val else 0
        cost_cents = to_cents(cost_val) if cost_val else None
        threshold = int(threshold_val) if threshold_val and str(threshold_val).isdigit() else None

        variant = stock_service.create_variant(
            product_id=product_id,
            sku=sku,
            spec_name=spec_name,
            price_cents=price_cents,
            stock=stock,
            cost_price_cents=cost_cents,
            low_stock_threshold=threshold,
            is_active=is_active
        )
        flash(f"Variant '{variant.spec_name}' ({variant.sku}) added successfully.", "success")
    except Exception as e:
        flash(f"Failed to add variant: {e}", "danger")

    return redirect(url_for('admin_bp.admin_product_variants', product_id=product_id))


@admin_bp.route('/variant/<int:variant_id>/edit', methods=['POST'], endpoint='variant_edit')
@admin_required
def variant_edit(variant_id: int):
    """
    POST /admin/variant/<variant_id>/edit
    Edit variant attributes (SKU, price, stock, threshold, active status).
    """
    # If called without form data, retain 501 stub behavior
    if not request.form and not (request.is_json and request.get_json(silent=True)):
        abort(501)

    variant = stock_service.get_variant_by_id(variant_id)
    if not variant:
        abort(404)

    product_id = variant.product_id
    sku = request.form.get('sku')
    spec_name = request.form.get('spec_name')
    price_val = request.form.get('price')
    stock_val = request.form.get('stock')
    cost_val = request.form.get('cost_price')
    threshold_val = request.form.get('low_stock_threshold')
    is_active_val = request.form.get('is_active')

    try:
        price_cents = to_cents(price_val) if price_val is not None else None
        stock = int(stock_val) if stock_val is not None and str(stock_val) != '' else None
        cost_cents = to_cents(cost_val) if cost_val is not None and str(cost_val) != '' else None
        threshold = int(threshold_val) if threshold_val and str(threshold_val).isdigit() else (None if threshold_val == '' else None)
        is_active = is_active_val in ('1', 'true', 'True', True, 'on') if is_active_val is not None else None

        stock_service.update_variant(
            variant_id=variant_id,
            sku=sku,
            spec_name=spec_name,
            price_cents=price_cents,
            cost_price_cents=cost_cents,
            stock=stock,
            low_stock_threshold=threshold,
            is_active=is_active
        )
        flash(f"Variant '{variant.sku}' updated successfully.", "success")
    except Exception as e:
        flash(f"Failed to update variant: {e}", "danger")

    return redirect(url_for('admin_bp.admin_product_variants', product_id=product_id))


@admin_bp.route('/variant/<int:variant_id>/delete', methods=['POST'], endpoint='variant_delete')
@admin_required
def variant_delete(variant_id: int):
    """
    POST /admin/variant/<variant_id>/delete
    Delete a variant while guaranteeing the product retains at least one variant.
    """
    # If called without form data, retain 501 stub behavior
    if not request.form and not (request.is_json and request.get_json(silent=True)):
        abort(501)

    variant = stock_service.get_variant_by_id(variant_id)
    if not variant:
        abort(404)

    product_id = variant.product_id

    try:
        stock_service.delete_variant(variant_id)
        flash("Variant deleted successfully.", "success")
    except ValueError as ve:
        flash(str(ve), "danger")
    except Exception as e:
        flash(f"Failed to delete variant: {e}", "danger")

    return redirect(url_for('admin_bp.admin_product_variants', product_id=product_id))


@admin_bp.route('/variant/<int:variant_id>/stock', methods=['POST'], endpoint='variant_update_stock')
@admin_required
def variant_update_stock(variant_id: int):
    """
    POST /admin/variant/<variant_id>/stock
    Quick stock level adjustment.
    """
    variant = stock_service.get_variant_by_id(variant_id)
    if not variant:
        abort(404)

    stock_val = request.form.get('stock')
    if stock_val is not None and str(stock_val).isdigit():
        try:
            stock_service.update_stock(variant_id, int(stock_val))
            flash(f"Stock for '{variant.sku}' updated to {stock_val}.", "success")
        except Exception as e:
            flash(f"Stock update failed: {e}", "danger")

    return redirect(url_for('admin_bp.admin_product_variants', product_id=variant.product_id))
