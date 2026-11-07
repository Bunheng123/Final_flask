"""
Unit & Integration Tests for Catalog, Product Variants, Atomic Stock & Low-Stock Alerts.
Workstream: Workstream A / Member 2
"""
import pytest
from extensions import db
from models.category import Category
from models.product import Product
from models.product_variant import ProductVariant
from services import stock_service
from helpers.money import to_cents, from_cents, format_money


@pytest.fixture
def sample_catalog(app):
    """
    Seed a category, products, and variants for testing.
    """
    with app.app_context():
        # Create Category
        cat_laptops = Category(name="Laptops", slug="laptops")
        cat_phones = Category(name="Phones", slug="phones")
        db.session.add(cat_laptops)
        db.session.add(cat_phones)
        db.session.commit()

        # Create Product 1 (Active)
        prod1 = stock_service.create_product(
            name="ThinkPad X1 Carbon",
            category_id=cat_laptops.id,
            description="Ultra-lightweight premium laptop",
            price_cents=149900,
            stock=10,
            sku="TP-X1-DEF",
            spec_name="Default (16GB / 512GB)",
            low_stock_threshold=3
        )

        # Add a secondary variant to Product 1
        var1_pro = stock_service.create_variant(
            product_id=prod1.id,
            sku="TP-X1-PRO",
            spec_name="Pro (32GB / 1TB)",
            price_cents=189900,
            stock=4,
            low_stock_threshold=2
        )

        # Create Product 2 (Active, default threshold fallback)
        prod2 = stock_service.create_product(
            name="iPhone 15 Pro",
            category_id=cat_phones.id,
            description="Titanium powerhouse smartphone",
            price_cents=99900,
            stock=8,
            sku="IP15P-128",
            spec_name="128GB Black Titanium",
            low_stock_threshold=None  # Should fallback to config (5)
        )

        # Create Product 3 (Inactive)
        prod3 = stock_service.create_product(
            name="Legacy Phone",
            category_id=cat_phones.id,
            description="Discontinued model",
            price_cents=29900,
            stock=0,
            sku="LEGACY-01",
            spec_name="Default",
            is_active=False
        )

        return {
            "cat_laptops_id": cat_laptops.id,
            "cat_phones_id": cat_phones.id,
            "prod1_id": prod1.id,
            "prod2_id": prod2.id,
            "prod3_id": prod3.id,
            "var1_pro_id": var1_pro.id
        }


# ==========================================
# 1. Product & Variant Fetching Tests
# ==========================================

def test_get_active_products(app, sample_catalog):
    """Test fetching active products excludes inactive ones and includes variants."""
    with app.app_context():
        active_products = stock_service.get_active_products()
        names = [p.name for p in active_products]
        assert "ThinkPad X1 Carbon" in names
        assert "iPhone 15 Pro" in names
        assert "Legacy Phone" not in names  # Inactive must be excluded

        # Check linked variants
        tp_product = next(p for p in active_products if p.name == "ThinkPad X1 Carbon")
        assert len(tp_product.variants) == 2
        skus = {v.sku for v in tp_product.variants}
        assert "TP-X1-DEF" in skus
        assert "TP-X1-PRO" in skus


def test_get_active_products_with_filters(app, sample_catalog):
    """Test filtering active products by category and search keyword."""
    with app.app_context():
        # Category filter
        laptop_products = stock_service.get_active_products(category_id=sample_catalog["cat_laptops_id"])
        assert len(laptop_products) == 1
        assert laptop_products[0].name == "ThinkPad X1 Carbon"

        # Search filter (name match)
        search_phone = stock_service.get_active_products(search="iPhone")
        assert len(search_phone) == 1
        assert search_phone[0].name == "iPhone 15 Pro"

        # Search filter (description match)
        search_desc = stock_service.get_active_products(search="Ultra-lightweight")
        assert len(search_desc) == 1
        assert search_desc[0].name == "ThinkPad X1 Carbon"


def test_get_product_by_id(app, sample_catalog):
    """Test retrieving product by ID with active flag options."""
    with app.app_context():
        prod = stock_service.get_product_by_id(sample_catalog["prod1_id"])
        assert prod is not None
        assert prod.name == "ThinkPad X1 Carbon"

        # Inactive product
        inactive = stock_service.get_product_by_id(sample_catalog["prod3_id"], only_active=True)
        assert inactive is None

        inactive_all = stock_service.get_product_by_id(sample_catalog["prod3_id"], only_active=False)
        assert inactive_all is not None


# ==========================================
# 2. Variant CRUD & Guarantee Tests
# ==========================================

def test_variant_guarantee_on_create_product(app, sample_catalog):
    """Every created product must automatically have at least one variant."""
    with app.app_context():
        prod = stock_service.get_product_by_id(sample_catalog["prod2_id"])
        assert len(prod.variants) >= 1
        default_var = prod.variants[0]
        assert default_var.price_cents == 99900
        assert default_var.stock == 8


def test_create_and_update_variant(app, sample_catalog):
    """Test creating a new variant and updating its attributes."""
    with app.app_context():
        new_var = stock_service.create_variant(
            product_id=sample_catalog["prod2_id"],
            sku="IP15P-256",
            spec_name="256GB Natural Titanium",
            price_cents=109900,
            stock=15,
            low_stock_threshold=4
        )
        assert new_var.id is not None
        assert new_var.sku == "IP15P-256"
        assert new_var.stock == 15

        # Update variant
        updated = stock_service.update_variant(
            variant_id=new_var.id,
            spec_name="256GB Natural Titanium (Unlocked)",
            price_cents=114900,
            stock=12
        )
        assert updated.spec_name == "256GB Natural Titanium (Unlocked)"
        assert updated.price_cents == 114900
        assert updated.stock == 12


def test_variant_duplicate_sku_rejected(app, sample_catalog):
    """Attempting to create or update to an existing SKU must fail."""
    with app.app_context():
        with pytest.raises(ValueError, match="already exists"):
            stock_service.create_variant(
                product_id=sample_catalog["prod1_id"],
                sku="TP-X1-DEF",  # Already used
                spec_name="Another Variant",
                price_cents=99999
            )


def test_cannot_delete_only_variant(app, sample_catalog):
    """Architecture Rule: Cannot delete the only variant of a product."""
    with app.app_context():
        prod2 = stock_service.get_product_by_id(sample_catalog["prod2_id"])
        assert len(prod2.variants) == 1
        only_var = prod2.variants[0]

        with pytest.raises(ValueError, match="Cannot delete the only variant"):
            stock_service.delete_variant(only_var.id)


def test_can_delete_secondary_variant(app, sample_catalog):
    """Deleting a variant when multiple exist succeeds."""
    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]
        success = stock_service.delete_variant(var_id)
        assert success is True
        assert stock_service.get_variant_by_id(var_id) is None


# ==========================================
# 3. Atomic Stock Decrement & Concurrency Tests
# ==========================================

def test_decrement_stock_atomic_success(app, sample_catalog):
    """Atomic decrement decreases stock count when stock is sufficient."""
    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # Stock: 4
        success = stock_service.decrement_stock_atomic(variant_id=var_id, quantity=2)
        assert success is True

        variant = stock_service.get_variant_by_id(var_id)
        assert variant.stock == 2


def test_decrement_stock_atomic_insufficient(app, sample_catalog):
    """Atomic decrement returns False and does not alter stock when quantity > stock."""
    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # Stock: 4
        success = stock_service.decrement_stock_atomic(variant_id=var_id, quantity=5)
        assert success is False

        # Verify stock remained untouched
        variant = stock_service.get_variant_by_id(var_id)
        assert variant.stock == 4


def test_decrement_stock_atomic_invalid_inputs(app, sample_catalog):
    """Decrement with quantity <= 0 or non-existent variant returns False."""
    with app.app_context():
        assert stock_service.decrement_stock_atomic(variant_id=sample_catalog["var1_pro_id"], quantity=0) is False
        assert stock_service.decrement_stock_atomic(variant_id=sample_catalog["var1_pro_id"], quantity=-3) is False
        assert stock_service.decrement_stock_atomic(variant_id=999999, quantity=1) is False


def test_restore_stock(app, sample_catalog):
    """Restoring stock increments inventory count accurately."""
    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # Stock: 4
        assert stock_service.restore_stock(variant_id=var_id, quantity=3) is True

        variant = stock_service.get_variant_by_id(var_id)
        assert variant.stock == 7


# ==========================================
# 4. Low-Stock Alert Telegram Trigger Tests
# ==========================================

def test_low_stock_alert_triggered_explicit_threshold(app, sample_catalog, monkeypatch):
    """
    When stock drops to or below the variant's low_stock_threshold (2),
    an alert must be dispatched via send_telegram.
    """
    dispatched_alerts = []

    def mock_send(msg):
        dispatched_alerts.append(msg)

    monkeypatch.setattr('services.stock_service.send_telegram', mock_send)
    monkeypatch.setattr('helpers.telegram.send_telegram', mock_send)

    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # Stock: 4, Threshold: 2

        # Decrement by 1 -> Stock is 3 (> 2) -> No alert
        stock_service.decrement_stock_atomic(variant_id=var_id, quantity=1)
        assert len(dispatched_alerts) == 0

        # Decrement by 1 -> Stock is 2 (<= 2) -> Low stock alert triggered!
        stock_service.decrement_stock_atomic(variant_id=var_id, quantity=1)
        assert len(dispatched_alerts) == 1
        alert = dispatched_alerts[0]
        assert "LOW STOCK ALERT" in alert
        assert "TP-X1-PRO" in alert
        assert "Current Stock: <b>2</b>" in alert
        assert "Threshold: 2" in alert


def test_low_stock_alert_triggered_fallback_threshold(app, sample_catalog, monkeypatch):
    """
    When low_stock_threshold is None, it should use config LOW_STOCK_THRESHOLD (default 5).
    """
    dispatched_alerts = []

    def mock_send(msg):
        dispatched_alerts.append(msg)

    monkeypatch.setattr('services.stock_service.send_telegram', mock_send)
    monkeypatch.setattr('helpers.telegram.send_telegram', mock_send)

    with app.app_context():
        prod2 = stock_service.get_product_by_id(sample_catalog["prod2_id"])
        var = prod2.variants[0]  # Stock: 8, Threshold: None (fallback 5)

        # Decrement by 2 -> Stock: 6 (> 5) -> No alert
        stock_service.decrement_stock_atomic(variant_id=var.id, quantity=2)
        assert len(dispatched_alerts) == 0

        # Decrement by 2 -> Stock: 4 (<= 5) -> Alert triggered!
        stock_service.decrement_stock_atomic(variant_id=var.id, quantity=2)
        assert len(dispatched_alerts) == 1
        assert "IP15P-128" in dispatched_alerts[0]
        assert "Current Stock: <b>4</b>" in dispatched_alerts[0]
        assert "Threshold: 5" in dispatched_alerts[0]


# ==========================================
# 5. Monetary Cents & Currency Standards Tests
# ==========================================

def test_price_stored_in_integer_cents(app, sample_catalog):
    """All variant prices must strictly be integer cents."""
    with app.app_context():
        var = stock_service.get_variant_by_id(sample_catalog["var1_pro_id"])
        assert isinstance(var.price_cents, int)
        assert var.price_cents == 189900
        # Format money helper
        assert format_money(var.price_cents) == "$1899.00"
        assert from_cents(var.price_cents) == 1899.00


# ==========================================
# 6. Storefront Views & API Integration Tests
# ==========================================

def test_storefront_products_list_view(client, sample_catalog):
    """Storefront GET /products loads active database products with formatted prices."""
    res = client.get('/products')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "ThinkPad X1 Carbon" in html
    assert "iPhone 15 Pro" in html
    assert "Legacy Phone" not in html  # Inactive excluded
    assert "$1499.00" in html
    assert "$999.00" in html


def test_storefront_products_filter_by_category(client, sample_catalog):
    """Storefront GET /products?category_id=X filters by category."""
    cat_id = sample_catalog["cat_laptops_id"]
    res = client.get(f'/products?category_id={cat_id}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "ThinkPad X1 Carbon" in html
    assert "iPhone 15 Pro" not in html


def test_storefront_products_search(client, sample_catalog):
    """Storefront GET /products?q=query searches product names."""
    res = client.get('/products?q=ThinkPad')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "ThinkPad X1 Carbon" in html
    assert "iPhone 15 Pro" not in html


def test_storefront_product_detail_view_with_variants(client, sample_catalog):
    """
    Storefront GET /product/<id> renders product details, active variants,
    variant selector form with CSRF token, product_id, and variant_id.
    """
    prod_id = sample_catalog["prod1_id"]
    res = client.get(f'/product/{prod_id}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')

    # Base product information
    assert "ThinkPad X1 Carbon" in html
    assert "Laptops" in html
    assert "TP-X1-DEF" in html

    # Variants rendered in selector
    assert "Default (16GB / 512GB)" in html
    assert "Pro (32GB / 1TB)" in html
    assert "$1499.00" in html
    assert "$1899.00" in html

    # Form attributes
    assert 'name="csrf_token"' in html
    assert f'value="{prod_id}"' in html
    assert 'name="variant_id"' in html
    assert 'name="qty"' in html


def test_storefront_product_detail_out_of_stock_state(client, sample_catalog):
    """When a variant has 0 stock, the page displays Out of Stock indicator."""
    with client.application.app_context():
        # Set stock of default variant to 0
        prod1 = stock_service.get_product_by_id(sample_catalog["prod1_id"])
        def_var = prod1.variants[0]
        stock_service.update_stock(def_var.id, 0)

    res = client.get(f'/product/{sample_catalog["prod1_id"]}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Out of Stock" in html


def test_storefront_product_not_found_returns_404(client, sample_catalog):
    """Requesting an unknown product ID returns 404."""
    res = client.get('/product/999999')
    assert res.status_code == 404


def test_api_products_with_db_catalog(client, sample_catalog):
    """GET /api/products returns database-backed active products with variant lists."""
    res = client.get('/api/products')
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data['success'] is True
    assert json_data['count'] == 2  # 2 active products

    # Verify ThinkPad product data
    tp = next(p for p in json_data['data'] if p['name'] == "ThinkPad X1 Carbon")
    assert tp['category'] == "Laptops"
    assert len(tp['variants']) == 2
    var_skus = {v['sku'] for v in tp['variants']}
    assert "TP-X1-DEF" in var_skus
    assert "TP-X1-PRO" in var_skus
    assert isinstance(tp['variants'][0]['price'], float)


def test_api_product_detail_with_db_catalog(client, sample_catalog):
    """GET /api/products/<id> returns single database-backed product details."""
    prod_id = sample_catalog["prod1_id"]
    res = client.get(f'/api/products/{prod_id}')
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data['success'] is True
    assert json_data['data']['name'] == "ThinkPad X1 Carbon"
    assert len(json_data['data']['variants']) == 2


# ==========================================
# 7. Admin Controllers & Variant Management Tests
# ==========================================

def test_admin_products_access_guards(client, sample_catalog):
    """
    Admin products route requires admin authentication:
    - Logged-out -> redirect to /login
    - Logged-in customer (role='user') -> 403 Forbidden
    - Logged-in admin (role='admin') -> 200 OK
    """
    # 1. Unauthenticated request
    res_anon = client.get('/admin/products', follow_redirects=False)
    assert res_anon.status_code in (301, 302)
    assert '/login' in res_anon.headers.get('Location', '')

    # 2. Customer user request
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['role'] = 'user'
        sess['user_role'] = 'user'

    res_user = client.get('/admin/products', follow_redirects=False)
    assert res_user.status_code == 403

    # 3. Admin user request
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['user_role'] = 'admin'

    res_admin = client.get('/admin/products')
    assert res_admin.status_code == 200
    html = res_admin.data.decode('utf-8')
    assert "Product &amp; Inventory Management" in html or "Product & Inventory Management" in html
    assert "ThinkPad X1 Carbon" in html


def test_admin_add_product_with_default_variant(client, sample_catalog):
    """
    POST /admin/products/add creates a product and guarantees the initial Default variant
    with price converted to integer cents and stock saved.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # GET form
    res_get = client.get('/admin/products/add')
    assert res_get.status_code == 200
    assert 'name="name"' in res_get.data.decode('utf-8')

    # POST new product
    res_post = client.post('/admin/products/add', data={
        'name': 'Dell XPS 15',
        'category_id': str(sample_catalog["cat_laptops_id"]),
        'description': 'InfinityEdge powerhouse laptop',
        'image': 'https://example.com/xps15.jpg',
        'sku': 'DELL-XPS15-DEF',
        'spec_name': 'Default (16GB / 512GB)',
        'price': '1599.99',  # $ USD float -> 159999 cents
        'stock': '14',
        'cost_price': '1200.00',
        'low_stock_threshold': '3'
    }, follow_redirects=True)

    assert res_post.status_code == 200
    assert "Dell XPS 15" in res_post.data.decode('utf-8')

    # Verify database state
    with client.application.app_context():
        created_prod = Product.query.filter_by(name='Dell XPS 15').first()
        assert created_prod is not None
        assert len(created_prod.variants) == 1

        var = created_prod.variants[0]
        assert var.sku == 'DELL-XPS15-DEF'
        assert var.spec_name == 'Default (16GB / 512GB)'
        assert var.price_cents == 159999
        assert var.stock == 14
        assert var.low_stock_threshold == 3


def test_admin_product_variants_view(client, sample_catalog):
    """GET /admin/products/<id>/variants displays variant table and add form."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    prod_id = sample_catalog["prod1_id"]
    res = client.get(f'/admin/products/{prod_id}/variants')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "Manage Variants: ThinkPad X1 Carbon" in html
    assert "TP-X1-DEF" in html
    assert "TP-X1-PRO" in html


def test_admin_variant_add_post(client, sample_catalog):
    """POST /admin/product/<id>/variant/add creates a new variant with integer cents conversion."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    prod_id = sample_catalog["prod1_id"]
    res = client.post(f'/admin/product/{prod_id}/variant/add', data={
        'sku': 'TP-X1-ULTRA',
        'spec_name': 'Ultra (64GB / 2TB SSD)',
        'price': '2399.50',  # $ USD float -> 239950 cents
        'stock': '6',
        'low_stock_threshold': '2',
        'is_active': '1'
    }, follow_redirects=True)

    assert res.status_code == 200

    # Verify DB
    with client.application.app_context():
        var = stock_service.get_variant_by_sku('TP-X1-ULTRA')
        assert var is not None
        assert var.price_cents == 239950
        assert var.stock == 6
        assert var.low_stock_threshold == 2


def test_admin_variant_edit_post(client, sample_catalog):
    """POST /admin/variant/<id>/edit updates attributes and converts price to integer cents."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    var_id = sample_catalog["var1_pro_id"]
    res = client.post(f'/admin/variant/{var_id}/edit', data={
        'sku': 'TP-X1-PRO-V2',
        'spec_name': 'Pro Max (32GB / 1TB OLED)',
        'price': '1999.00',
        'stock': '9',
        'low_stock_threshold': '4',
        'is_active': '1'
    }, follow_redirects=True)

    assert res.status_code == 200

    with client.application.app_context():
        var = stock_service.get_variant_by_id(var_id)
        assert var.sku == 'TP-X1-PRO-V2'
        assert var.spec_name == 'Pro Max (32GB / 1TB OLED)'
        assert var.price_cents == 199900
        assert var.stock == 9
        assert var.low_stock_threshold == 4


def test_admin_variant_stock_update_post(client, sample_catalog):
    """POST /admin/variant/<id>/stock allows quick stock adjustment."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    var_id = sample_catalog["var1_pro_id"]
    res = client.post(f'/admin/variant/{var_id}/stock', data={
        'stock': '35'
    }, follow_redirects=True)

    assert res.status_code == 200

    with client.application.app_context():
        var = stock_service.get_variant_by_id(var_id)
        assert var.stock == 35


def test_admin_variant_delete_protection_and_success(client, sample_catalog):
    """
    POST /admin/variant/<id>/delete enforces that the sole variant cannot be deleted.
    When multiple variants exist, secondary variant can be deleted.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # Product 2 has only 1 variant -> deletion rejected
    with client.application.app_context():
        prod2 = stock_service.get_product_by_id(sample_catalog["prod2_id"])
        only_var_id = prod2.variants[0].id

    res_fail = client.post(f'/admin/variant/{only_var_id}/delete', data={'confirm': '1'}, follow_redirects=True)
    assert res_fail.status_code == 200
    assert "Cannot delete the only variant" in res_fail.data.decode('utf-8')

    with client.application.app_context():
        assert stock_service.get_variant_by_id(only_var_id) is not None

    # Product 1 has 2 variants -> deleting secondary variant succeeds
    var1_pro_id = sample_catalog["var1_pro_id"]
    res_ok = client.post(f'/admin/variant/{var1_pro_id}/delete', data={'confirm': '1'}, follow_redirects=True)
    assert res_ok.status_code == 200
    assert "Variant deleted successfully." in res_ok.data.decode('utf-8')

    with client.application.app_context():
        assert stock_service.get_variant_by_id(var1_pro_id) is None


def test_admin_toggle_product_status(client, sample_catalog):
    """POST /admin/products/<id>/toggle-status toggles is_active."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    prod_id = sample_catalog["prod1_id"]
    # Toggle off
    res1 = client.post(f'/admin/products/{prod_id}/toggle-status', follow_redirects=True)
    assert res1.status_code == 200

    with client.application.app_context():
        prod = stock_service.get_product_by_id(prod_id)
        assert prod.is_active is False

    # Toggle on
    res2 = client.post(f'/admin/products/{prod_id}/toggle-status', follow_redirects=True)
    assert res2.status_code == 200

    with client.application.app_context():
        prod = stock_service.get_product_by_id(prod_id)
        assert prod.is_active is True


def test_admin_delete_product(client, sample_catalog):
    """POST /admin/products/<id>/delete deletes product and all its variants."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    prod_id = sample_catalog["prod2_id"]
    res = client.post(f'/admin/products/{prod_id}/delete', follow_redirects=True)
    assert res.status_code == 200

    with client.application.app_context():
        assert stock_service.get_product_by_id(prod_id) is None


# ==========================================
# 8. Product Edit CRUD & Test Pricing Tests
# ==========================================

def test_storefront_stepper_quantity_controls(client, sample_catalog):
    """Storefront product detail page renders - and + stepper controls."""
    prod_id = sample_catalog["prod1_id"]
    res = client.get(f'/product/{prod_id}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert 'id="qtyMinusBtn"' in html
    assert 'id="qtyPlusBtn"' in html
    assert 'id="productQtyInput"' in html
    assert 'stepQty(-1)' in html
    assert 'stepQty(1)' in html


def test_admin_edit_product_crud(client, sample_catalog):
    """
    GET and POST /admin/products/<id>/edit provides full CRUD editing
    over product identity, category, description, and status.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    prod_id = sample_catalog["prod1_id"]

    # 1. GET edit form
    res_get = client.get(f'/admin/products/{prod_id}/edit')
    assert res_get.status_code == 200
    html_get = res_get.data.decode('utf-8')
    assert f'value="ThinkPad X1 Carbon"' in html_get
    assert 'name="csrf_token"' in html_get
    assert 'name="name"' in html_get
    assert 'name="category_id"' in html_get

    # 2. POST update product
    new_cat_id = sample_catalog["cat_phones_id"]
    res_post = client.post(f'/admin/products/{prod_id}/edit', data={
        'name': 'ThinkPad X1 Carbon Gen 12',
        'category_id': str(new_cat_id),
        'description': 'Updated flagship ultrabook specifications',
        'image': 'https://example.com/x1gen12.png',
        'is_active': '1'
    }, follow_redirects=True)

    assert res_post.status_code == 200
    html_post = res_post.data.decode('utf-8')
    assert "ThinkPad X1 Carbon Gen 12" in html_post

    # Verify DB
    with client.application.app_context():
        updated = stock_service.get_product_by_id(prod_id)
        assert updated.name == 'ThinkPad X1 Carbon Gen 12'
        assert updated.category_id == new_cat_id
        assert updated.description == 'Updated flagship ultrabook specifications'
        assert updated.image == 'https://example.com/x1gen12.png'


def test_set_test_prices_cents_service_and_admin_route(client, sample_catalog):
    """
    Tests set_test_prices_cents() domain service and POST /admin/products/set-test-prices
    setting all variants to 1¢ / 2¢ ($0.01 / $0.02) test prices.
    """
    with client.application.app_context():
        # Service function alternating 1 and 2 cents
        count = stock_service.set_test_prices_cents()
        assert count > 0

        variants = ProductVariant.query.order_by(ProductVariant.id.asc()).all()
        assert variants[0].price_cents in (1, 2)
        assert variants[1].price_cents in (1, 2)

        # Service function explicit 1 cent for all
        stock_service.set_test_prices_cents(cents=1)
        variants = ProductVariant.query.all()
        for v in variants:
            assert v.price_cents == 1

    # Admin route trigger
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    res_route = client.post('/admin/products/set-test-prices', follow_redirects=True)
    assert res_route.status_code == 200
    html = res_route.data.decode('utf-8')
    assert "Successfully updated" in html
    assert "test prices" in html

    # Verify DB after route call
    with client.application.app_context():
        variants = ProductVariant.query.order_by(ProductVariant.id.asc()).all()
        for idx, v in enumerate(variants):
            expected = 1 if (idx % 2 == 0) else 2
            assert v.price_cents == expected




