"""
Tests for Workstream D / Developer 4: Coupons, Invoicing & Financial Reports.
"""
import io
import datetime
import pytest
from extensions import db
from models.user import User
from models.coupon import Coupon
from models.coupon_redemption import CouponRedemption
from models.order import Order
from models.order_item import OrderItem
from models.category import Category
from models.product import Product
from models.product_variant import ProductVariant
from services.coupon_service import validate_coupon, apply_coupon, redeem, release
from services.invoice_service import generate_invoice_pdf
from services.report_service import (
    generate_sales_report,
    generate_inventory_valuation,
    export_sales_csv,
    export_sales_excel
)
from helpers.time import utc_now


@pytest.fixture
def seed_data(app):
    """Seed test data for coupons, products, variants, and orders."""
    with app.app_context():
        # Clean any old test records
        CouponRedemption.query.delete()
        OrderItem.query.delete()
        Order.query.delete()
        Coupon.query.delete()
        ProductVariant.query.delete()
        Product.query.delete()
        Category.query.delete()

        # Seed Coupons
        c_percent = Coupon(
            code="SAVE10",
            discount_type="percent",
            value=10.0,
            min_spend_cents=5000,       # $50 min spend
            max_discount_cents=2000,    # $20 max cap
            usage_limit=10,
            per_customer_limit=1,
            is_active=True,
            used_count=0
        )
        c_fixed = Coupon(
            code="FIXED15",
            discount_type="fixed",
            value=1500.0,              # $15.00 in cents
            min_spend_cents=3000,      # $30 min spend
            usage_limit=5,
            per_customer_limit=2,
            is_active=True,
            used_count=0
        )
        c_inactive = Coupon(
            code="INACTIVE",
            discount_type="percent",
            value=20.0,
            is_active=False
        )
        c_expired = Coupon(
            code="EXPIRED",
            discount_type="percent",
            value=15.0,
            is_active=True,
            expires_at=utc_now() - datetime.timedelta(days=2)
        )
        c_future = Coupon(
            code="FUTURE",
            discount_type="percent",
            value=15.0,
            is_active=True,
            starts_at=utc_now() + datetime.timedelta(days=2)
        )
        c_exhausted = Coupon(
            code="EXHAUSTED",
            discount_type="percent",
            value=10.0,
            usage_limit=3,
            used_count=3,
            is_active=True
        )

        db.session.add_all([c_percent, c_fixed, c_inactive, c_expired, c_future, c_exhausted])

        # Seed Catalog
        cat = Category(name="Laptops", slug="laptops")
        db.session.add(cat)
        db.session.commit()

        prod = Product(
            category_id=cat.id,
            name="Test Laptop Pro",
            description="High performance laptop",
            image="test.jpg",
            is_active=True
        )
        db.session.add(prod)
        db.session.commit()

        v1 = ProductVariant(
            product_id=prod.id,
            sku="LAPTOP-PRO-16",
            spec_name="16GB / 512GB",
            price_cents=100000,  # $1,000.00
            cost_price_cents=70000,
            stock=15,
            low_stock_threshold=5,
            is_active=True
        )
        v2 = ProductVariant(
            product_id=prod.id,
            sku="LAPTOP-PRO-32",
            spec_name="32GB / 1TB",
            price_cents=150000,  # $1,500.00
            cost_price_cents=105000,
            stock=3,  # Low stock
            low_stock_threshold=5,
            is_active=True
        )
        db.session.add_all([v1, v2])
        db.session.commit()

        # Seed Orders
        order1 = Order(
            order_number="ORD-20261101-001",
            user_id=1,
            customer_name="John Doe",
            email="john@example.com",
            phone="012345678",
            address="123 Street, Phnom Penh",
            payment_method="cod",
            status="confirmed",
            subtotal_cents=100000,
            discount_cents=10000,
            total_cents=90000,
            coupon_code="SAVE10",
            created_at=utc_now() - datetime.timedelta(days=1)
        )
        db.session.add(order1)
        db.session.commit()

        item1 = OrderItem(
            order_id=order1.id,
            variant_id=v1.id,
            product_name="Test Laptop Pro",
            sku="LAPTOP-PRO-16",
            spec_name="16GB / 512GB",
            qty=1,
            unit_price_cents=100000,
            line_total_cents=100000
        )
        db.session.add(item1)
        db.session.commit()

        order2 = Order(
            order_number="ORD-20261102-002",
            user_id=None,
            customer_name="Jane Smith",
            email="jane@example.com",
            phone="098765432",
            address="456 Boulevard, Phnom Penh",
            payment_method="qr",
            status="pending",
            subtotal_cents=150000,
            discount_cents=0,
            total_cents=150000,
            created_at=utc_now()
        )
        db.session.add(order2)
        db.session.commit()

        item2 = OrderItem(
            order_id=order2.id,
            variant_id=v2.id,
            product_name="Test Laptop Pro",
            sku="LAPTOP-PRO-32",
            spec_name="32GB / 1TB",
            qty=1,
            unit_price_cents=150000,
            line_total_cents=150000
        )
        db.session.add(item2)
        db.session.commit()


# ==============================================================================
# 1. Coupon Service Unit Tests
# ==============================================================================

def test_validate_coupon_percent(seed_data):
    """Test percentage discount calculation and min spend."""
    valid, msg, discount = validate_coupon("save10", 10000)  # $100 subtotal
    assert valid is True
    assert discount == 1000  # 10% of 10000 = 1000 cents ($10.00)


def test_validate_coupon_fixed(seed_data):
    """Test fixed dollar discount calculation."""
    valid, msg, discount = validate_coupon("FIXED15", 5000)  # $50 subtotal
    assert valid is True
    assert discount == 1500  # $15.00 fixed


def test_validate_coupon_min_spend_rejected(seed_data):
    """Test rejection when subtotal does not meet min_spend."""
    valid, msg, discount = validate_coupon("SAVE10", 3000)  # $30 < $50 min spend
    assert valid is False
    assert "Minimum spend" in msg
    assert discount == 0


def test_validate_coupon_max_cap_applied(seed_data):
    """Test percentage discount capped by max_discount_cents."""
    # 10% of $300 (30000 cents) = $30 (3000 cents), but cap is $20 (2000 cents)
    valid, msg, discount = validate_coupon("SAVE10", 30000)
    assert valid is True
    assert discount == 2000


def test_validate_coupon_invalid_and_inactive(seed_data):
    """Test invalid and inactive coupon codes."""
    v1, _, _ = validate_coupon("NONEXISTENT", 10000)
    assert v1 is False

    v2, msg2, _ = validate_coupon("INACTIVE", 10000)
    assert v2 is False
    assert "inactive" in msg2.lower()

    v3, msg3, _ = validate_coupon("EXPIRED", 10000)
    assert v3 is False
    assert "expired" in msg3.lower()

    v4, msg4, _ = validate_coupon("FUTURE", 10000)
    assert v4 is False
    assert "not active" in msg4.lower()

    v5, msg5, _ = validate_coupon("EXHAUSTED", 10000)
    assert v5 is False
    assert "maximum" in msg5.lower()


def test_validate_coupon_per_customer_limit(seed_data):
    """Test per-customer limit enforcement."""
    # Redeem SAVE10 for user_id=1
    redemption = redeem("SAVE10", order_id=1, user_id=1)
    assert redemption is not None

    # Now user 1 tries again -> should fail
    valid, msg, _ = validate_coupon("SAVE10", 10000, user_id=1)
    assert valid is False
    assert "maximum allowed number" in msg

    # But user 2 can still use it
    valid2, _, _ = validate_coupon("SAVE10", 10000, user_id=2)
    assert valid2 is True


def test_apply_and_release_coupon(seed_data):
    """Test apply_coupon calculation and release function."""
    discount = apply_coupon("SAVE10", 10000)
    assert discount == 1000

    discount_invalid = apply_coupon("FAKE", 10000)
    assert discount_invalid == 0

    c = Coupon.query.filter_by(code="FIXED15").first()
    init_count = c.used_count
    redemption = redeem("FIXED15", order_id=1, user_id=5)
    assert c.used_count == init_count + 1

    released = release(redemption.id)
    assert released is True
    assert c.used_count == init_count


# ==============================================================================
# 2. Storefront Coupon & Invoice Route Tests
# ==============================================================================

def test_coupon_preview_endpoint(client, seed_data):
    """Test /coupon/preview AJAX endpoint."""
    res = client.post('/coupon/preview', json={
        'code': 'SAVE10',
        'subtotal': 100.00
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert data['discount_cents'] == 1000
    assert data['discount_formatted'] == "$10.00"
    assert data['new_total_formatted'] == "$90.00"

    # Test invalid code
    res_bad = client.post('/coupon/preview', json={
        'code': 'BOGUS',
        'subtotal': 100.00
    })
    assert res_bad.status_code == 400
    data_bad = res_bad.get_json()
    assert data_bad['success'] is False


def test_invoice_pdf_generation(seed_data):
    """Test ReportLab PDF generation service directly."""
    order = Order.query.first()
    buf = generate_invoice_pdf(order.id)
    assert isinstance(buf, io.BytesIO)
    content = buf.getvalue()
    assert content.startswith(b'%PDF')
    assert len(content) > 1000


def test_invoice_pdf_download_endpoint(client, seed_data):
    """Test GET /order/<id>/invoice.pdf endpoint."""
    order = Order.query.first()

    # Log in as admin
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'admin'
        sess['user_id'] = 1

    res = client.get(f'/order/{order.id}/invoice.pdf')
    assert res.status_code == 200
    assert res.content_type == 'application/pdf'
    assert f"Invoice-{order.order_number}.pdf" in res.headers['Content-Disposition']
    assert res.data.startswith(b'%PDF')


# ==============================================================================
# 3. Report Service & Accounting Export Tests
# ==============================================================================

def test_generate_sales_and_inventory_reports(seed_data):
    """Test sales metrics aggregation and inventory stock valuation."""
    sales = generate_sales_report()
    assert sales['total_orders'] == 2
    assert sales['completed_orders_count'] == 1  # 1 confirmed, 1 pending
    assert sales['net_revenue_cents'] == 90000

    inv = generate_inventory_valuation()
    assert inv['total_skus'] == 2
    assert inv['total_units'] == 18  # 15 + 3
    assert inv['low_stock_count'] == 1  # v2 has 3 <= 5
    assert inv['total_retail_valuation_cents'] == (15 * 100000) + (3 * 150000)


def test_export_sales_csv(seed_data):
    """Test CSV generation."""
    csv_str = export_sales_csv()
    assert "Order Number,Date (Local),Customer Name" in csv_str
    assert "ORD-20261101-001" in csv_str
    assert "John Doe" in csv_str


def test_export_sales_excel(seed_data):
    """Test multi-tab Excel workbook generation via openpyxl."""
    buf = export_sales_excel()
    assert isinstance(buf, io.BytesIO)
    content = buf.getvalue()
    # Excel files are zip archives starting with PK
    assert content.startswith(b'PK')


def test_admin_reports_dashboard_and_export_routes(client, seed_data):
    """Test admin reports view and export downloads."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'admin'
        sess['user_id'] = 1

    # Dashboard view
    res = client.get('/admin/reports')
    assert res.status_code == 200
    assert b"Accounting &amp; Valuation Reports" in res.data or b"Accounting & Valuation Reports" in res.data

    # CSV export
    res_csv = client.get('/admin/reports/export-csv')
    assert res_csv.status_code == 200
    assert res_csv.content_type.startswith('text/csv')

    # Excel export
    res_excel = client.get('/admin/reports/export-excel')
    assert res_excel.status_code == 200
    assert 'spreadsheet' in res_excel.content_type or 'octet-stream' in res_excel.content_type


# ==============================================================================
# 4. Admin Coupon CRUD Tests
# ==============================================================================

def test_admin_coupons_crud(client, seed_data):
    """Test admin list, add, edit, toggle, and delete coupon routes."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'admin'
        sess['user_id'] = 1

    # 1. List
    res_list = client.get('/admin/coupons')
    assert res_list.status_code == 200
    assert b"SAVE10" in res_list.data

    # 2. Add
    res_add = client.post('/admin/coupons/add', data={
        'code': 'SUMMER30',
        'discount_type': 'percent',
        'value': '30',
        'min_spend': '100.00',
        'max_discount': '50.00',
        'usage_limit': '50',
        'per_customer_limit': '1',
        'is_active': '1'
    }, follow_redirects=True)
    assert res_add.status_code == 200
    created = Coupon.query.filter_by(code='SUMMER30').first()
    assert created is not None
    assert created.value == 30.0
    assert created.min_spend_cents == 10000
    assert created.max_discount_cents == 5000

    # 3. Edit
    res_edit = client.post(f'/admin/coupons/edit/{created.id}', data={
        'code': 'SUMMER35',
        'discount_type': 'percent',
        'value': '35',
        'min_spend': '150.00',
        'max_discount': '60.00',
        'usage_limit': '75',
        'per_customer_limit': '2',
        'is_active': '1'
    }, follow_redirects=True)
    assert res_edit.status_code == 200
    updated = Coupon.query.get(created.id)
    assert updated.code == 'SUMMER35'
    assert updated.value == 35.0
    assert updated.min_spend_cents == 15000

    # 4. Toggle
    res_toggle = client.post(f'/admin/coupons/toggle/{updated.id}', follow_redirects=True)
    assert res_toggle.status_code == 200
    assert updated.is_active is False

    # 5. Delete
    res_delete = client.post(f'/admin/coupons/delete/{updated.id}', follow_redirects=True)
    assert res_delete.status_code == 200
    assert Coupon.query.get(updated.id) is None
