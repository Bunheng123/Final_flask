"""
Admin Coupon & Promotional Campaign Management.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
from flask import render_template, request, redirect, url_for, flash, abort
from admin import admin_bp
from extensions import db
from models.coupon import Coupon
from helpers.money import to_cents, from_cents


@admin_bp.get('/coupons', endpoint='admin_coupons')
def admin_coupons():
    """
    List coupons with usage counts, discount rates, min spend, and active status.
    """
    search = request.args.get('q', '').strip()
    query = Coupon.query

    if search:
        query = query.filter(Coupon.code.ilike(f"%{search}%"))

    coupons = query.order_by(Coupon.id.desc()).all()
    return render_template('admin/coupons/index.html', coupons=coupons, search=search, module='coupons')


@admin_bp.route('/coupons/add', methods=['GET', 'POST'], endpoint='admin_add_coupon')
def admin_add_coupon():
    """
    Create a new promotional coupon code.
    """
    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        discount_type = request.form.get('discount_type', 'percent')
        raw_value = request.form.get('value', '0').strip()
        raw_min_spend = request.form.get('min_spend', '0').strip()
        raw_max_discount = request.form.get('max_discount', '').strip()
        raw_usage_limit = request.form.get('usage_limit', '').strip()
        raw_per_customer_limit = request.form.get('per_customer_limit', '').strip()
        is_active = request.form.get('is_active') in ('1', 'true', 'on')

        if not code:
            flash("Coupon code is required.", "error")
            return redirect(request.url)

        existing = Coupon.query.filter_by(code=code).first()
        if existing:
            flash(f"Coupon code '{code}' already exists.", "error")
            return redirect(request.url)

        try:
            val_float = float(raw_value)
            # If fixed, value is in cents (e.g. $10.00 -> 1000.0 cents)
            if discount_type == 'fixed':
                val_float = float(to_cents(val_float))
        except (ValueError, TypeError):
            flash("Invalid discount value.", "error")
            return redirect(request.url)

        min_spend_cents = to_cents(raw_min_spend)
        max_discount_cents = to_cents(raw_max_discount) if raw_max_discount else None
        usage_limit = int(raw_usage_limit) if raw_usage_limit.isdigit() else None
        per_customer_limit = int(raw_per_customer_limit) if raw_per_customer_limit.isdigit() else None

        coupon = Coupon(
            code=code,
            discount_type=discount_type,
            value=val_float,
            min_spend_cents=min_spend_cents,
            max_discount_cents=max_discount_cents,
            usage_limit=usage_limit,
            per_customer_limit=per_customer_limit,
            is_active=is_active,
            used_count=0
        )
        db.session.add(coupon)
        db.session.commit()

        flash(f"Coupon '{coupon.code}' created successfully.", "success")
        return redirect(url_for('admin_bp.admin_coupons'))

    return render_template('admin/coupons/add.html', module='coupons')


@admin_bp.route('/coupons/edit/<int:coupon_id>', methods=['GET', 'POST'], endpoint='admin_edit_coupon')
def admin_edit_coupon(coupon_id: int):
    """
    Edit an existing coupon.
    """
    coupon = Coupon.query.get_or_404(coupon_id)

    if request.method == 'POST':
        code = request.form.get('code', '').strip().upper()
        discount_type = request.form.get('discount_type', coupon.discount_type)
        raw_value = request.form.get('value', '0').strip()
        raw_min_spend = request.form.get('min_spend', '0').strip()
        raw_max_discount = request.form.get('max_discount', '').strip()
        raw_usage_limit = request.form.get('usage_limit', '').strip()
        raw_per_customer_limit = request.form.get('per_customer_limit', '').strip()
        is_active = request.form.get('is_active') in ('1', 'true', 'on')

        if not code:
            flash("Coupon code is required.", "error")
            return redirect(request.url)

        existing = Coupon.query.filter(Coupon.code == code, Coupon.id != coupon.id).first()
        if existing:
            flash(f"Coupon code '{code}' is already used by another coupon.", "error")
            return redirect(request.url)

        try:
            val_float = float(raw_value)
            if discount_type == 'fixed':
                val_float = float(to_cents(val_float))
        except (ValueError, TypeError):
            flash("Invalid discount value.", "error")
            return redirect(request.url)

        coupon.code = code
        coupon.discount_type = discount_type
        coupon.value = val_float
        coupon.min_spend_cents = to_cents(raw_min_spend)
        coupon.max_discount_cents = to_cents(raw_max_discount) if raw_max_discount else None
        coupon.usage_limit = int(raw_usage_limit) if raw_usage_limit.isdigit() else None
        coupon.per_customer_limit = int(raw_per_customer_limit) if raw_per_customer_limit.isdigit() else None
        coupon.is_active = is_active

        db.session.commit()
        flash(f"Coupon '{coupon.code}' updated successfully.", "success")
        return redirect(url_for('admin_bp.admin_coupons'))

    # Prepare readable values for form
    display_value = from_cents(coupon.value) if coupon.discount_type == 'fixed' else coupon.value
    min_spend_display = from_cents(coupon.min_spend_cents)
    max_discount_display = from_cents(coupon.max_discount_cents) if coupon.max_discount_cents else ""

    return render_template(
        'admin/coupons/edit.html',
        coupon=coupon,
        display_value=display_value,
        min_spend_display=min_spend_display,
        max_discount_display=max_discount_display,
        module='coupons'
    )


@admin_bp.post('/coupons/toggle/<int:coupon_id>', endpoint='admin_toggle_coupon')
def admin_toggle_coupon(coupon_id: int):
    """
    Toggle a coupon's active status.
    """
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    status_str = "activated" if coupon.is_active else "deactivated"
    flash(f"Coupon '{coupon.code}' has been {status_str}.", "success")
    return redirect(url_for('admin_bp.admin_coupons'))


@admin_bp.post('/coupons/delete/<int:coupon_id>', endpoint='admin_delete_coupon')
def admin_delete_coupon(coupon_id: int):
    """
    Delete a coupon code.
    """
    coupon = Coupon.query.get_or_404(coupon_id)
    code = coupon.code
    db.session.delete(coupon)
    db.session.commit()
    flash(f"Coupon '{code}' has been deleted.", "success")
    return redirect(url_for('admin_bp.admin_coupons'))
