"""
Report Service - Accounting exports, revenue metrics, and inventory valuation.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
import csv
import io
from datetime import datetime, date, time
from typing import Optional, Dict, Any
from sqlalchemy import func
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from extensions import db
from models.order import Order
from models.order_item import OrderItem
from models.product import Product
from models.product_variant import ProductVariant
from helpers.money import from_cents, format_money
from helpers.time import to_local
from config import Config


def _parse_date(d_val) -> Optional[datetime]:
    if not d_val:
        return None
    if isinstance(d_val, datetime):
        return d_val
    if isinstance(d_val, date):
        return datetime.combine(d_val, time.min)
    if isinstance(d_val, str):
        d_val = d_val.strip()
        if not d_val:
            return None
        try:
            return datetime.strptime(d_val, "%Y-%m-%d")
        except ValueError:
            try:
                return datetime.fromisoformat(d_val)
            except ValueError:
                return None
    return None


def generate_sales_report(start_date=None, end_date=None) -> Dict[str, Any]:
    """
    Calculates gross sales, net revenue, discount totals, order counts, and daily breakdown.
    """
    query = Order.query

    start_dt = _parse_date(start_date)
    end_dt = _parse_date(end_date)

    if start_dt:
        query = query.filter(Order.created_at >= start_dt)
    if end_dt:
        # Include through end of the target day
        end_dt_inclusive = datetime.combine(end_dt.date(), time.max)
        query = query.filter(Order.created_at <= end_dt_inclusive)

    orders = query.order_by(Order.created_at.desc()).all()

    total_orders = len(orders)
    completed_orders = [o for o in orders if o.status in ('confirmed', 'shipped', 'delivered')]
    pending_orders = [o for o in orders if o.status == 'pending']
    cancelled_orders = [o for o in orders if o.status == 'cancelled']

    # Non-cancelled orders for gross & discount
    active_orders = [o for o in orders if o.status != 'cancelled']
    gross_sales_cents = sum(o.subtotal_cents for o in active_orders)
    discount_cents = sum(o.discount_cents for o in active_orders)
    net_revenue_cents = sum(o.total_cents for o in completed_orders)

    # Group daily
    daily_dict = {}
    for o in orders:
        local_dt = to_local(o.created_at)
        day_key = local_dt.strftime("%Y-%m-%d") if local_dt else o.created_at.strftime("%Y-%m-%d")
        if day_key not in daily_dict:
            daily_dict[day_key] = {
                'date': day_key,
                'orders_count': 0,
                'completed_count': 0,
                'gross_cents': 0,
                'discount_cents': 0,
                'net_cents': 0,
            }
        daily_dict[day_key]['orders_count'] += 1
        if o.status != 'cancelled':
            daily_dict[day_key]['gross_cents'] += o.subtotal_cents
            daily_dict[day_key]['discount_cents'] += o.discount_cents
        if o.status in ('confirmed', 'shipped', 'delivered'):
            daily_dict[day_key]['completed_count'] += 1
            daily_dict[day_key]['net_cents'] += o.total_cents

    daily_breakdown = sorted(daily_dict.values(), key=lambda x: x['date'], reverse=True)

    khr_rate = getattr(Config, 'KHR_RATE', 4000.0)
    aov_cents = (gross_sales_cents // total_orders) if total_orders > 0 else 0
    realization_rate = (len(completed_orders) / total_orders * 100.0) if total_orders > 0 else 0.0
    discount_rate = (discount_cents / gross_sales_cents * 100.0) if gross_sales_cents > 0 else 0.0

    gross_khr = f"{int(round((gross_sales_cents / 100.0) * khr_rate)):,} ៛"
    net_khr = f"{int(round((net_revenue_cents / 100.0) * khr_rate)):,} ៛"

    return {
        'total_orders': total_orders,
        'completed_orders_count': len(completed_orders),
        'pending_orders_count': len(pending_orders),
        'cancelled_orders_count': len(cancelled_orders),
        'gross_sales_cents': gross_sales_cents,
        'gross_sales_formatted': format_money(gross_sales_cents),
        'gross_sales_khr': gross_khr,
        'aov_cents': aov_cents,
        'aov_formatted': format_money(aov_cents),
        'realization_rate': f"{realization_rate:.1f}%",
        'discount_cents': discount_cents,
        'discount_formatted': format_money(discount_cents),
        'discount_rate': f"{discount_rate:.1f}%",
        'net_revenue_cents': net_revenue_cents,
        'net_revenue_formatted': format_money(net_revenue_cents),
        'net_revenue_khr': net_khr,
        'orders': orders,
        'daily_breakdown': daily_breakdown,
        'start_date': start_dt.strftime("%Y-%m-%d") if start_dt else "",
        'end_date': end_dt.strftime("%Y-%m-%d") if end_dt else ""
    }


def generate_inventory_valuation() -> Dict[str, Any]:
    """
    Calculates total inventory retail and cost valuations across product variants.
    """
    variants = db.session.query(ProductVariant, Product)\
        .join(Product, ProductVariant.product_id == Product.id)\
        .filter(ProductVariant.is_active == True)\
        .order_by(Product.name.asc(), ProductVariant.sku.asc())\
        .all()

    total_skus = len(variants)
    total_units = sum(v.stock for v, _ in variants)
    total_retail_cents = sum(v.stock * v.price_cents for v, _ in variants)

    # Cost calculation: use cost_price_cents if set, otherwise assume 70% of retail price
    total_cost_cents = sum(
        v.stock * (v.cost_price_cents if v.cost_price_cents is not None else int(v.price_cents * 0.70))
        for v, _ in variants
    )

    low_stock_threshold_fallback = 5
    low_stock_count = 0
    out_of_stock_count = 0

    items = []
    for v, p in variants:
        threshold = v.low_stock_threshold or low_stock_threshold_fallback
        is_low = v.stock <= threshold
        if v.stock == 0:
            out_of_stock_count += 1
        elif is_low:
            low_stock_count += 1

        cost = v.cost_price_cents if v.cost_price_cents is not None else int(v.price_cents * 0.70)
        items.append({
            'variant_id': v.id,
            'sku': v.sku,
            'product_name': p.name,
            'spec_name': v.spec_name,
            'stock': v.stock,
            'price_cents': v.price_cents,
            'price_formatted': format_money(v.price_cents),
            'cost_price_cents': cost,
            'cost_formatted': format_money(cost),
            'valuation_cents': v.stock * v.price_cents,
            'valuation_formatted': format_money(v.stock * v.price_cents),
            'is_low_stock': is_low,
            'is_out_of_stock': v.stock == 0
        })

    margin_percent = ((total_retail_cents - total_cost_cents) / total_retail_cents * 100.0) if total_retail_cents > 0 else 0.0
    khr_rate = getattr(Config, 'KHR_RATE', 4000.0)
    inventory_khr = f"{int(round((total_retail_cents / 100.0) * khr_rate)):,} ៛"

    return {
        'total_skus': total_skus,
        'total_units': total_units,
        'total_retail_valuation_cents': total_retail_cents,
        'total_retail_valuation_formatted': format_money(total_retail_cents),
        'total_retail_valuation_khr': inventory_khr,
        'total_cost_valuation_cents': total_cost_cents,
        'total_cost_valuation_formatted': format_money(total_cost_cents),
        'potential_profit_cents': total_retail_cents - total_cost_cents,
        'potential_profit_formatted': format_money(total_retail_cents - total_cost_cents),
        'margin_percent': f"{margin_percent:.1f}%",
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'variant_items': items,
        'items': items
    }


def export_sales_csv(start_date=None, end_date=None) -> str:
    """
    Generates a CSV string representation of all matching sales orders.
    """
    report = generate_sales_report(start_date, end_date)
    orders = report['orders']

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow([
        "Order Number",
        "Date (Local)",
        "Customer Name",
        "Email",
        "Phone",
        "Shipping Address",
        "Status",
        "Payment Method",
        "Subtotal ($)",
        "Discount ($)",
        "Total ($)",
        "Coupon Code"
    ])

    for o in orders:
        local_dt = to_local(o.created_at)
        date_str = local_dt.strftime("%Y-%m-%d %H:%M:%S") if local_dt else str(o.created_at)
        writer.writerow([
            o.order_number,
            date_str,
            o.customer_name,
            o.email,
            o.phone,
            o.address.replace("\n", ", ") if o.address else "",
            o.status,
            o.payment_method,
            f"{from_cents(o.subtotal_cents):.2f}",
            f"{from_cents(o.discount_cents):.2f}",
            f"{from_cents(o.total_cents):.2f}",
            o.coupon_code or ""
        ])

    return output.getvalue()


def export_sales_excel(start_date=None, end_date=None) -> io.BytesIO:
    """
    Generates an executive multi-tab Excel workbook (.xlsx) via openpyxl.
    Tabs:
      1. Sales Orders
      2. Daily Summary
      3. Inventory Valuation
    """
    sales_data = generate_sales_report(start_date, end_date)
    inv_data = generate_inventory_valuation()

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Styles
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    total_fill = PatternFill(start_color="EEF2FF", end_color="EEF2FF", fill_type="solid")
    total_font = Font(name="Calibri", size=11, bold=True, color="1E1B4B")
    data_font = Font(name="Calibri", size=10)
    border_thin = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )

    # =========================================================================
    # TAB 1: Sales Orders
    # =========================================================================
    ws_orders = wb.create_sheet(title="Sales Orders")
    orders_headers = [
        "Order #", "Date", "Customer", "Email", "Phone",
        "Status", "Payment", "Subtotal ($)", "Discount ($)", "Total ($)", "Coupon"
    ]
    ws_orders.append(orders_headers)

    for col_idx in range(1, len(orders_headers) + 1):
        cell = ws_orders.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center" if col_idx in (1, 2, 6, 7) else "left", vertical="center")

    row_num = 2
    for o in sales_data['orders']:
        local_dt = to_local(o.created_at)
        date_str = local_dt.strftime("%Y-%m-%d %H:%M") if local_dt else str(o.created_at)
        row_vals = [
            o.order_number,
            date_str,
            o.customer_name,
            o.email,
            o.phone,
            o.status.upper(),
            o.payment_method.upper(),
            from_cents(o.subtotal_cents),
            from_cents(o.discount_cents),
            from_cents(o.total_cents),
            o.coupon_code or ""
        ]
        ws_orders.append(row_vals)

        for col_idx in range(1, len(row_vals) + 1):
            c = ws_orders.cell(row=row_num, column=col_idx)
            c.font = data_font
            c.border = border_thin
            if col_idx in (8, 9, 10):
                c.number_format = '$#,##0.00'
                c.alignment = Alignment(horizontal="right")
        row_num += 1

    # Add Summary Row
    summary_row = [
        "TOTALS", f"{sales_data['total_orders']} orders", "", "", "", "", "",
        from_cents(sales_data['gross_sales_cents']),
        from_cents(sales_data['discount_cents']),
        from_cents(sales_data['net_revenue_cents']),
        ""
    ]
    ws_orders.append(summary_row)
    for col_idx in range(1, len(summary_row) + 1):
        c = ws_orders.cell(row=row_num, column=col_idx)
        c.fill = total_fill
        c.font = total_font
        c.border = border_thin
        if col_idx in (8, 9, 10):
            c.number_format = '$#,##0.00'
            c.alignment = Alignment(horizontal="right")

    # =========================================================================
    # TAB 2: Daily Summary
    # =========================================================================
    ws_daily = wb.create_sheet(title="Daily Summary")
    daily_headers = ["Date", "Orders Count", "Completed Count", "Gross Sales ($)", "Discounts ($)", "Net Revenue ($)"]
    ws_daily.append(daily_headers)

    for col_idx in range(1, len(daily_headers) + 1):
        cell = ws_daily.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    d_row = 2
    for d in sales_data['daily_breakdown']:
        vals = [
            d['date'],
            d['orders_count'],
            d['completed_count'],
            from_cents(d['gross_cents']),
            from_cents(d['discount_cents']),
            from_cents(d['net_cents'])
        ]
        ws_daily.append(vals)
        for col_idx in range(1, len(vals) + 1):
            c = ws_daily.cell(row=d_row, column=col_idx)
            c.font = data_font
            c.border = border_thin
            if col_idx in (4, 5, 6):
                c.number_format = '$#,##0.00'
                c.alignment = Alignment(horizontal="right")
        d_row += 1

    # =========================================================================
    # TAB 3: Inventory Valuation
    # =========================================================================
    ws_inv = wb.create_sheet(title="Inventory Valuation")
    inv_headers = ["SKU", "Product Name", "Specification", "Stock Units", "Unit Price ($)", "Est. Cost ($)", "Total Valuation ($)", "Status"]
    ws_inv.append(inv_headers)

    for col_idx in range(1, len(inv_headers) + 1):
        cell = ws_inv.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    inv_row = 2
    for item in inv_data['items']:
        status_label = "OUT OF STOCK" if item['is_out_of_stock'] else ("LOW STOCK" if item['is_low_stock'] else "IN STOCK")
        vals = [
            item['sku'],
            item['product_name'],
            item['spec_name'],
            item['stock'],
            from_cents(item['price_cents']),
            from_cents(item['cost_price_cents']),
            from_cents(item['valuation_cents']),
            status_label
        ]
        ws_inv.append(vals)
        for col_idx in range(1, len(vals) + 1):
            c = ws_inv.cell(row=inv_row, column=col_idx)
            c.font = data_font
            c.border = border_thin
            if col_idx in (5, 6, 7):
                c.number_format = '$#,##0.00'
                c.alignment = Alignment(horizontal="right")
        inv_row += 1

    # Total Valuation Row
    inv_totals = [
        "TOTAL", "", "", inv_data['total_units'], "", "",
        from_cents(inv_data['total_retail_valuation_cents']),
        f"{inv_data['total_skus']} SKUs"
    ]
    ws_inv.append(inv_totals)
    for col_idx in range(1, len(inv_totals) + 1):
        c = ws_inv.cell(row=inv_row, column=col_idx)
        c.fill = total_fill
        c.font = total_font
        c.border = border_thin
        if col_idx == 7:
            c.number_format = '$#,##0.00'
            c.alignment = Alignment(horizontal="right")

    # Auto-adjust column widths across all sheets
    for ws in [ws_orders, ws_daily, ws_inv]:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or '')
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
