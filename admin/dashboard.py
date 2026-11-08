from datetime import timedelta
from flask import render_template, session, redirect, url_for
from admin import admin_bp
from extensions import limiter
from helpers.auth import admin_required
from helpers.money import format_money, from_cents
from helpers.time import utc_now, to_local
from models.order import Order
from models.user import User
from models.product import Product
from models.product_variant import ProductVariant
from models.coupon import Coupon
from services.stock_service import get_low_stock_variants


@admin_bp.get('/dashboard', endpoint='dashboard')
@admin_bp.get('/', endpoint='dashboard_root')
@limiter.limit("30 per minute")
@admin_required
def dashboard():
    module = 'dashboard'
    admin_name = session.get('username', 'Admin')

    # 1. Real Order & Financial Metrics
    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    total_orders = len(all_orders)

    completed_orders = [o for o in all_orders if o.status in ('confirmed', 'shipped', 'delivered')]
    pending_orders = [o for o in all_orders if o.status == 'pending']
    cancelled_orders = [o for o in all_orders if o.status == 'cancelled']

    net_revenue_cents = sum((o.total_cents or 0) for o in completed_orders)
    gross_sales_cents = sum((o.subtotal_cents or 0) for o in all_orders if o.status != 'cancelled')
    total_discounts_cents = sum((o.discount_cents or 0) for o in all_orders if o.status != 'cancelled')

    refund_rate = round((len(cancelled_orders) / total_orders * 100), 1) if total_orders > 0 else 0.0
    aov_cents = round(net_revenue_cents / len(completed_orders)) if completed_orders else 0

    # 2. Real Catalog & User Stats
    users_count = User.query.filter(User.role != 'admin').count()
    products_count = Product.query.count()
    active_products_count = Product.query.filter_by(is_active=True).count()
    variants_count = ProductVariant.query.count()
    active_variants = ProductVariant.query.filter_by(is_active=True).all()
    total_inventory_units = sum((v.stock or 0) for v in active_variants)
    low_stock_variants = get_low_stock_variants()
    low_stock_count = len(low_stock_variants)
    out_of_stock_count = sum(1 for v in low_stock_variants if (v.stock or 0) <= 0)
    critical_low_count = sum(1 for v in low_stock_variants if (v.stock or 0) > 0)
    healthy_skus_count = max(0, variants_count - low_stock_count)
    inventory_health_percent = round((healthy_skus_count / variants_count * 100), 1) if variants_count > 0 else 100.0
    active_coupons_count = Coupon.query.filter_by(is_active=True).count()

    # Detailed Low Stock Inventory List
    low_stock_details = []
    for v in low_stock_variants:
        thresh = v.low_stock_threshold if v.low_stock_threshold is not None else 5
        cat_name = 'General'
        if v.product and v.product.category:
            cat_name = v.product.category.name if hasattr(v.product.category, 'name') else str(v.product.category)
        brand_name = v.product.brand.name if (v.product and v.product.brand) else 'TechStore'

        low_stock_details.append({
            'id': v.id,
            'product_id': v.product_id,
            'product_name': v.product.name if v.product else 'Product',
            'product_image': v.product.image if (v.product and v.product.image) else '/static/images/no-image.jpg',
            'spec_name': v.spec_name or 'Standard',
            'sku': v.sku,
            'stock': v.stock,
            'threshold': thresh,
            'price_formatted': format_money(v.price_cents or 0),
            'is_out_of_stock': ((v.stock or 0) <= 0),
            'category_name': cat_name,
            'brand_name': brand_name
        })

    # 3. Real 7-Day Revenue & Orders Graph Data
    now_utc = utc_now()
    now_local = to_local(now_utc) or now_utc

    # Pre-aggregate orders by day key YYYY-MM-DD
    orders_by_day = {}
    for o in all_orders:
        if o.created_at:
            odt = to_local(o.created_at) or o.created_at
            d_key = odt.strftime('%Y-%m-%d')
            if d_key not in orders_by_day:
                orders_by_day[d_key] = {'rev_cents': 0, 'count': 0}
            orders_by_day[d_key]['count'] += 1
            if o.status in ('confirmed', 'shipped', 'delivered'):
                orders_by_day[d_key]['rev_cents'] += (o.total_cents or 0)

    max_day_cents = max([v['rev_cents'] for v in orders_by_day.values()] + [1])

    chart_days = []
    for i in range(6, -1, -1):
        target_dt = now_local - timedelta(days=i)
        d_key = target_dt.strftime('%Y-%m-%d')
        day_stats = orders_by_day.get(d_key, {'rev_cents': 0, 'count': 0})
        day_cents = day_stats['rev_cents']
        if day_cents > 0:
            height_pct = max(18, min(100, round((day_cents / max_day_cents) * 100)))
        else:
            height_pct = 10
        chart_days.append({
            'day_name': target_dt.strftime('%a'),
            'date_str': target_dt.strftime('%b %d'),
            'rev_cents': day_cents,
            'rev_formatted': format_money(day_cents),
            'orders_count': day_stats['count'],
            'height_pct': height_pct,
            'is_today': (i == 0)
        })

    # 4. Real Recent Orders (Top 6)
    recent_orders = all_orders[:6]

    # 5. Real Payment Methods Distribution
    payment_counts = {}
    for o in all_orders:
        m = (o.payment_method or 'COD').upper()
        payment_counts[m] = payment_counts.get(m, 0) + 1

    payment_distribution = []
    for p_name, count in sorted(payment_counts.items(), key=lambda x: x[1], reverse=True):
        pct = round((count / total_orders * 100), 1) if total_orders > 0 else 0
        payment_distribution.append({
            'name': p_name,
            'count': count,
            'percent': pct
        })

    # 6. Real Low Stock Items (Top 5)
    low_stock_preview = low_stock_variants[:5]

    return render_template(
        'admin/dashboard/dashboard.html',
        module=module,
        admin_name=admin_name,
        net_revenue_formatted=format_money(net_revenue_cents),
        gross_sales_formatted=format_money(gross_sales_cents),
        total_discounts_formatted=format_money(total_discounts_cents),
        aov_formatted=format_money(aov_cents),
        total_orders=total_orders,
        completed_orders_count=len(completed_orders),
        pending_orders_count=len(pending_orders),
        cancelled_orders_count=len(cancelled_orders),
        refund_rate=refund_rate,
        users_count=users_count,
        products_count=products_count,
        active_products_count=active_products_count,
        variants_count=variants_count,
        total_inventory_units=total_inventory_units,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        critical_low_count=critical_low_count,
        healthy_skus_count=healthy_skus_count,
        inventory_health_percent=inventory_health_percent,
        active_coupons_count=active_coupons_count,
        chart_days=chart_days,
        recent_orders=recent_orders,
        payment_distribution=payment_distribution,
        low_stock_preview=low_stock_preview,
        low_stock_details=low_stock_details
    )
