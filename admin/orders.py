"""
Admin Order Management.
Owner: Workstream C (Orders & Grace Period)
"""
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify, abort, session
from admin import admin_bp
from extensions import db
from models.order import Order
from helpers.auth import admin_required
from helpers.time import to_local, utc_now
from helpers.money import format_money, from_cents
from services.order_service import (
    VALID_TRANSITIONS,
    transition_order,
    get_order_payment_hash,
)

@admin_bp.get('/orders', endpoint='admin_orders')
@admin_required
def admin_orders():
    """
    List customer orders with status tabs, search, and date filters.
    """
    status_filter = request.args.get('status', '').strip().lower()
    search_query = request.args.get('q', '').strip()
    start_date = request.args.get('start_date', '').strip()
    end_date = request.args.get('end_date', '').strip()

    query = Order.query

    # Status filter
    if status_filter and status_filter in VALID_TRANSITIONS:
        query = query.filter(Order.status == status_filter)

    # Search filter
    if search_query:
        search_like = f"%{search_query}%"
        query = query.filter(
            (Order.order_number.ilike(search_like)) |
            (Order.customer_name.ilike(search_like)) |
            (Order.email.ilike(search_like)) |
            (Order.phone.ilike(search_like))
        )

    # Date filters
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Order.created_at >= start_dt)
        except ValueError:
            pass

    if end_date:
        try:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
            query = query.filter(Order.created_at <= end_dt)
        except ValueError:
            pass

    orders = query.order_by(Order.created_at.desc()).all()

    # Precalculate status counts for badges
    counts = {
        'all': Order.query.count(),
        'pending': Order.query.filter_by(status='pending').count(),
        'confirmed': Order.query.filter_by(status='confirmed').count(),
        'shipped': Order.query.filter_by(status='shipped').count(),
        'delivered': Order.query.filter_by(status='delivered').count(),
        'cancelled': Order.query.filter_by(status='cancelled').count(),
    }

    return render_template(
        'admin/orders/index.html',
        orders=orders,
        status_counts=counts,
        current_status=status_filter or 'all',
        search_query=search_query,
        start_date=start_date,
        end_date=end_date,
        to_local=to_local,
        format_money=format_money,
        valid_transitions=VALID_TRANSITIONS,
    )


@admin_bp.get('/orders/<int:order_id>', endpoint='admin_order_detail')
@admin_required
def admin_order_detail(order_id: int):
    """
    View order details, line items, timestamps, and payment hash.
    Supports both JSON response for the luxury detail modal and full HTML page.
    """
    order = Order.query.get_or_404(order_id)

    # Return JSON for AJAX modal request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
        items_data = []
        for item in order.items:
            items_data.append({
                'id': item.id,
                'product_name': item.product_name,
                'sku': item.sku,
                'spec_name': item.spec_name,
                'qty': item.qty,
                'unit_price_cents': item.unit_price_cents,
                'unit_price_formatted': format_money(item.unit_price_cents),
                'line_total_cents': item.line_total_cents,
                'line_total_formatted': format_money(item.line_total_cents),
            })

        local_created = to_local(order.created_at)
        local_confirmed = to_local(order.confirmed_at)
        local_shipped = to_local(order.shipped_at)
        local_delivered = to_local(order.delivered_at)
        local_cancelled = to_local(order.cancelled_at)

        return jsonify({
            'success': True,
            'order': {
                'id': order.id,
                'order_number': order.order_number,
                'customer_name': order.customer_name,
                'email': order.email,
                'phone': order.phone,
                'address': order.address,
                'payment_method': order.payment_method,
                'status': order.status,
                'subtotal_cents': order.subtotal_cents,
                'subtotal_formatted': format_money(order.subtotal_cents),
                'discount_cents': order.discount_cents,
                'discount_formatted': format_money(order.discount_cents),
                'total_cents': order.total_cents,
                'total_formatted': format_money(order.total_cents),
                'coupon_code': order.coupon_code,
                'bakong_hash': get_order_payment_hash(order),
                'created_at': local_created.strftime('%Y-%m-%d %I:%M %p') if local_created else None,
                'confirmed_at': local_confirmed.strftime('%Y-%m-%d %I:%M %p') if local_confirmed else None,
                'shipped_at': local_shipped.strftime('%Y-%m-%d %I:%M %p') if local_shipped else None,
                'delivered_at': local_delivered.strftime('%Y-%m-%d %I:%M %p') if local_delivered else None,
                'cancelled_at': local_cancelled.strftime('%Y-%m-%d %I:%M %p') if local_cancelled else None,
                'items': items_data,
                'allowed_transitions': VALID_TRANSITIONS.get(order.status, []),
            }
        })

    return render_template(
        'admin/orders/detail.html',
        order=order,
        to_local=to_local,
        format_money=format_money,
        get_order_payment_hash=get_order_payment_hash,
        valid_transitions=VALID_TRANSITIONS,
    )


@admin_bp.post('/orders/<int:order_id>/status', endpoint='admin_update_order_status')
@admin_required
def admin_update_order_status(order_id: int):
    """
    Transition order status (e.g. pending -> confirmed -> shipped -> delivered).
    Enforces forward-only progression via order_service.
    """
    target_status = request.form.get('status', '').strip().lower()
    if not target_status:
        flash("Target status is required.", "danger")
        return redirect(request.referrer or url_for('admin_bp.admin_orders'))

    try:
        order = transition_order(
            order_id=order_id,
            target_status=target_status,
            admin_id=session.get('user_id')
        )
        flash(f"Order #{order.order_number} successfully transitioned to '{target_status.upper()}'.", "success")
    except ValueError as e:
        flash(str(e), "danger")
    except Exception as e:
        flash(f"Failed to update status: {e}", "danger")

    return redirect(request.referrer or url_for('admin_bp.admin_orders'))
