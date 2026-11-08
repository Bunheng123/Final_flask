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
    an alert must be dispatched via send_telegram targeting the 429 security alert chat (@pp_shop_alert).
    """
    dispatched_alerts = []

    def mock_send(msg, chat_id=None, token=None, **kwargs):
        dispatched_alerts.append({
            "msg": msg,
            "chat_id": chat_id,
            "token": token
        })

    monkeypatch.setattr('services.stock_service.send_telegram', mock_send)
    monkeypatch.setattr('helpers.telegram.send_telegram', mock_send)

    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # Stock: 4, Threshold: 2
        var = stock_service.get_variant_by_id(var_id)
        prod_id = var.product_id

        # Decrement by 1 -> Stock is 3 (> 2) -> No alert
        stock_service.decrement_stock_atomic(variant_id=var_id, quantity=1)
        assert len(dispatched_alerts) == 0

        # Decrement by 1 -> Stock is 2 (<= 2) -> Low stock alert triggered!
        stock_service.decrement_stock_atomic(variant_id=var_id, quantity=1)
        assert len(dispatched_alerts) == 1
        alert = dispatched_alerts[0]
        msg = alert["msg"]
        chat_id = alert["chat_id"]

        # Alert must target the 429 rate limit security alert channel
        expected_chat = app.config.get("TELEGRAM_ALERT_CHAT_ID") or "@pp_shop_alert"
        assert chat_id == expected_chat
        assert "LOW STOCK ALERT" in msg
        assert "ThinkPad X1 Carbon" in msg
        assert "Pro (32GB / 1TB)" in msg
        assert "TP-X1-PRO" in msg
        assert "Remaining Stock: <b>2</b>" in msg
        assert "Threshold Trigger: <b>2</b>" in msg
        assert f"/admin/products/{prod_id}/variants" in msg


def test_low_stock_alert_triggered_fallback_threshold(app, sample_catalog, monkeypatch):
    """
    When low_stock_threshold is None, it should use config LOW_STOCK_THRESHOLD (default 5)
    and target the 429 security alert chat (@pp_shop_alert).
    """
    dispatched_alerts = []

    def mock_send(msg, chat_id=None, token=None, **kwargs):
        dispatched_alerts.append({
            "msg": msg,
            "chat_id": chat_id,
            "token": token
        })

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
        alert = dispatched_alerts[0]
        msg = alert["msg"]
        chat_id = alert["chat_id"]

        expected_chat = app.config.get("TELEGRAM_ALERT_CHAT_ID") or "@pp_shop_alert"
        assert chat_id == expected_chat
        assert "LOW STOCK ALERT" in msg
        assert "iPhone 15 Pro" in msg
        assert "IP15P-128" in msg
        assert "Remaining Stock: <b>4</b>" in msg
        assert "Threshold Trigger: <b>5</b>" in msg
        assert f"/admin/products/{prod2.id}/variants" in msg

        # Subsequent purchase on already-low product -> Stock: 3 -> No redundant alert!
        stock_service.decrement_stock_atomic(variant_id=var.id, quantity=1)
        assert len(dispatched_alerts) == 1


def test_low_stock_alert_uses_custom_security_alert_channel(app, sample_catalog, monkeypatch):
    """
    Verifies that TELEGRAM_ALERT_CHAT_ID and TELEGRAM_ALERT_BOT_TOKEN
    from app.config are respected when dispatching low stock alerts.
    """
    dispatched_alerts = []

    def mock_send(msg, chat_id=None, token=None, **kwargs):
        dispatched_alerts.append({
            "msg": msg,
            "chat_id": chat_id,
            "token": token
        })

    monkeypatch.setattr('services.stock_service.send_telegram', mock_send)
    monkeypatch.setattr('helpers.telegram.send_telegram', mock_send)

    with app.app_context():
        monkeypatch.setitem(app.config, "TELEGRAM_ALERT_CHAT_ID", "@custom_sec_alert")
        monkeypatch.setitem(app.config, "TELEGRAM_ALERT_BOT_TOKEN", "custom_alert_bot_token")

        var_id = sample_catalog["var1_pro_id"]  # Stock: 4, Threshold: 2
        stock_service.decrement_stock_atomic(variant_id=var_id, quantity=2)

        assert len(dispatched_alerts) == 1
        alert = dispatched_alerts[0]
        assert alert["chat_id"] == "@custom_sec_alert"
        assert alert["token"] == "custom_alert_bot_token"
        assert "Remaining Stock: <b>2</b>" in alert["msg"]
        assert f"/admin/products/{sample_catalog['prod1_id']}/variants" in alert["msg"]


def test_low_stock_alert_triggered_on_manual_stock_update(app, sample_catalog, monkeypatch):
    """
    Verifies that updating stock via update_stock() also dispatches
    a low stock alert if the new stock is <= threshold.
    """
    dispatched_alerts = []

    def mock_send(msg, chat_id=None, token=None, **kwargs):
        dispatched_alerts.append({
            "msg": msg,
            "chat_id": chat_id,
            "token": token
        })

    monkeypatch.setattr('services.stock_service.send_telegram', mock_send)
    monkeypatch.setattr('helpers.telegram.send_telegram', mock_send)

    with app.app_context():
        var_id = sample_catalog["var1_pro_id"]  # threshold is 2
        stock_service.update_stock(variant_id=var_id, new_stock=1)

        assert len(dispatched_alerts) == 1
        alert = dispatched_alerts[0]
        expected_chat = app.config.get("TELEGRAM_ALERT_CHAT_ID") or "@pp_shop_alert"
        assert alert["chat_id"] == expected_chat
        assert "Remaining Stock: <b>1</b>" in alert["msg"]
        assert f"/admin/products/{sample_catalog['prod1_id']}/variants" in alert["msg"]


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


def test_zero_stock_product_hidden_from_storefront_and_api(client, sample_catalog):
    """
    A product where all active variants have stock <= 0 must be hidden from customers:
    - Excluded from stock_service.get_active_products()
    - Excluded from storefront GET /products, GET /, and GET /api/products
    - GET /product/<id> and GET /api/products/<id> return 404
    - Admin GET /admin/products and stock_service.get_all_products() still show it for restocking
    """
    with client.application.app_context():
        prod_id = sample_catalog["prod1_id"]
        prod1 = stock_service.get_product_by_id(prod_id)
        for v in prod1.variants:
            stock_service.update_stock(v.id, 0)

        # 1. Service layer check
        active_prods = stock_service.get_active_products()
        assert prod_id not in [p.id for p in active_prods]

        # Admin service helper still includes it
        all_prods = stock_service.get_all_products()
        assert prod_id in [p.id for p in all_prods]
        assert stock_service.get_product_by_id(prod_id) is not None

    # 2. Storefront listing (/products)
    res_list = client.get('/products')
    assert res_list.status_code == 200
    html_list = res_list.data.decode('utf-8')
    assert f'data-product-id="{prod_id}"' not in html_list

    # 3. Storefront homepage (/)
    res_home = client.get('/')
    assert res_home.status_code == 200
    html_home = res_home.data.decode('utf-8')
    assert f'/product/{prod_id}' not in html_home

    # 4. Storefront API (/api/products)
    res_api = client.get('/api/products')
    assert res_api.status_code == 200
    api_data = res_api.get_json()['data']
    assert prod_id not in [p['id'] for p in api_data]

    # 5. Detail page returns 404
    res_detail = client.get(f'/product/{prod_id}')
    assert res_detail.status_code == 404

    # 6. Detail API returns 404
    res_api_detail = client.get(f'/api/products/{prod_id}')
    assert res_api_detail.status_code == 404

    # 7. Admin dashboard still lists it for restock
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['user_role'] = 'admin'

    res_admin = client.get('/admin/products')
    assert res_admin.status_code == 200
    admin_html = res_admin.data.decode('utf-8')
    assert "ThinkPad X1 Carbon" in admin_html


def test_inactive_variants_product_hidden_from_storefront(client, sample_catalog):
    """
    A product where all variants have is_active = False must be hidden from storefront
    and return 404 on detail views, but remain accessible in admin.
    """
    with client.application.app_context():
        prod_id = sample_catalog["prod2_id"]
        prod2 = stock_service.get_product_by_id(prod_id)
        for v in prod2.variants:
            stock_service.update_variant(v.id, is_active=False)

        active_prods = stock_service.get_active_products()
        assert prod_id not in [p.id for p in active_prods]

    res_list = client.get('/products')
    assert res_list.status_code == 200
    assert f'data-product-id="{prod_id}"' not in res_list.data.decode('utf-8')

    res_detail = client.get(f'/product/{prod_id}')
    assert res_detail.status_code == 404

    res_api_detail = client.get(f'/api/products/{prod_id}')
    assert res_api_detail.status_code == 404

    # Admin dashboard still shows it
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'
        sess['user_role'] = 'admin'

    res_admin = client.get('/admin/products')
    assert res_admin.status_code == 200
    assert "iPhone 15 Pro" in res_admin.data.decode('utf-8')


def test_product_detail_exposes_only_active_variants(client, sample_catalog):
    """
    On the product detail page and API, only active variants (is_active == True)
    are shown to shoppers in the variant selector, and the in-stock variant is selected by default.
    """
    with client.application.app_context():
        prod1 = stock_service.get_product_by_id(sample_catalog["prod1_id"])
        # Deactivate default variant, leave pro variant active
        def_var = next(v for v in prod1.variants if v.sku == "TP-X1-DEF")
        pro_var = next(v for v in prod1.variants if v.sku == "TP-X1-PRO")
        pro_var_id = pro_var.id
        stock_service.update_variant(def_var.id, is_active=False)

    # 1. Product detail page
    res = client.get(f'/product/{sample_catalog["prod1_id"]}')
    assert res.status_code == 200
    html = res.data.decode('utf-8')
    assert "TP-X1-DEF" not in html
    assert "TP-X1-PRO" in html
    # Pro variant must be present and selected
    assert f'value="{pro_var_id}"' in html

    # 2. Product API detail
    res_api = client.get(f'/api/products/{sample_catalog["prod1_id"]}')
    assert res_api.status_code == 200
    data = res_api.get_json()['data']
    variant_skus = [v['sku'] for v in data['variants']]
    assert "TP-X1-DEF" not in variant_skus
    assert "TP-X1-PRO" in variant_skus


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


# ==========================================
# 11. Brand Management & Safe Disassociation Tests
# ==========================================

def test_brand_service_crud_and_slug(app):
    """
    Test Brand CRUD service operations and unique slug auto-generation.
    """
    with app.app_context():
        # 1. Create with auto-generated slug
        b1 = stock_service.create_brand(
            name="Apple",
            description="Consumer electronics & software",
            website="https://www.apple.com"
        )
        assert b1.id is not None
        assert b1.name == "Apple"
        assert b1.slug == "apple"
        assert b1.website == "https://www.apple.com"

        # 2. Duplicate name validation
        with pytest.raises(ValueError, match="already exists"):
            stock_service.create_brand(name="Apple")

        # 3. Slug collision resolution for similar name
        b2 = stock_service.create_brand(name="Apple US")
        assert b2.slug == "apple-us"

        # 4. Fetch by ID and Slug
        fetched_by_id = stock_service.get_brand_by_id(b1.id)
        assert fetched_by_id.name == "Apple"
        fetched_by_slug = stock_service.get_brand_by_slug("apple")
        assert fetched_by_slug.id == b1.id

        # 5. Update brand
        updated = stock_service.update_brand(
            brand_id=b1.id,
            name="Apple Inc.",
            slug="apple-inc",
            website="https://apple.com"
        )
        assert updated.name == "Apple Inc."
        assert updated.slug == "apple-inc"
        assert updated.website == "https://apple.com"

        # 6. List all brands
        all_brands = stock_service.get_all_brands()
        assert len(all_brands) >= 2


def test_brand_deletion_disassociates_products_without_deleting_them(app, sample_catalog):
    """
    CRITICAL ACCEPTANCE TEST:
    Deleting a brand MUST safely disassociate linked products by setting
    product.brand_id = None (NULL) BEFORE deleting the brand row,
    without cascading deletion of any products.
    """
    with app.app_context():
        from models.brand import Brand

        # 1. Create a brand
        sony = stock_service.create_brand(
            name="Sony Electronics",
            website="https://www.sony.com"
        )
        sony_id = sony.id

        # 2. Create a product linked to this brand
        headphones = stock_service.create_product(
            name="WH-1000XM5 Noise Canceling Headphones",
            category_id=sample_catalog["cat_phones_id"],
            description="Industry-leading noise cancellation",
            price_cents=39900,
            stock=15,
            sku="SONY-WH5-BLK",
            spec_name="Black",
            brand_id=sony_id
        )
        prod_id = headphones.id

        # Verify initial brand linkage
        assert headphones.brand_id == sony_id
        assert headphones.brand.name == "Sony Electronics"

        # 3. Delete the brand
        success = stock_service.delete_brand(sony_id)
        assert success is True

        # 4. CRITICAL VERIFICATION:
        # A) The brand row is deleted
        assert db.session.get(Brand, sony_id) is None

        # B) The product STILL EXISTS in the database (NO cascade deletion!)
        persisted_prod = db.session.get(Product, prod_id)
        assert persisted_prod is not None
        assert persisted_prod.name == "WH-1000XM5 Noise Canceling Headphones"

        # C) The product's brand_id is now safely set to None (NULL)
        assert persisted_prod.brand_id is None
        assert persisted_prod.brand is None


# ==========================================
# 12. Category Management CRUD & Reassignment Tests
# ==========================================

def test_category_service_crud_and_reassignment(app):
    """
    Test Category CRUD, slug generation, and safe deletion with product reassignment.
    """
    with app.app_context():
        # 1. Create Category
        cat_audio = stock_service.create_category(name="Audio & Headphones")
        assert cat_audio.id is not None
        assert cat_audio.slug == "audio-headphones"

        # 2. Duplicate category validation
        with pytest.raises(ValueError, match="already exists"):
            stock_service.create_category(name="Audio & Headphones")

        # 3. Update Category
        updated_cat = stock_service.update_category(cat_audio.id, name="Audio Equipment", slug="audio-equipment")
        assert updated_cat.name == "Audio Equipment"
        assert updated_cat.slug == "audio-equipment"

        # 4. Link a product to this category
        prod = stock_service.create_product(
            name="Wireless Earbuds",
            category_id=cat_audio.id,
            price_cents=4900,
            stock=20,
            sku="AUDIO-001"
        )
        prod_id = prod.id

        # 5. Attempting to delete category with linked products without reassign target must fail
        with pytest.raises(ValueError, match=r"linked to it"):
            stock_service.delete_category(cat_audio.id)

        # 6. Create fallback category and reassign
        cat_accessories = stock_service.create_category(name="Accessories")
        success = stock_service.delete_category(cat_audio.id, reassign_to_id=cat_accessories.id)
        assert success is True

        # Verify old category is deleted
        assert stock_service.get_category_by_id(cat_audio.id) is None

        # Verify product was safely reassigned
        reassigned_prod = db.session.get(Product, prod_id)
        assert reassigned_prod is not None
        assert reassigned_prod.category_id == cat_accessories.id


# ==========================================
# 13. Admin Brand & Category Route Tests
# ==========================================

def test_admin_brand_routes_full_flow(client):
    """
    Test full admin workflow for Brands:
    - Auth guard
    - GET /admin/brands (listing)
    - POST /admin/brands/add (create brand)
    - GET & POST /admin/brands/<id>/edit (update brand)
    - POST /admin/brands/<id>/delete (safe deletion)
    """
    # 1. Unauthenticated access blocked
    res_unauth = client.get('/admin/brands')
    assert res_unauth.status_code == 302

    # 2. Authenticate as admin
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # 3. GET /admin/brands
    res_list = client.get('/admin/brands')
    assert res_list.status_code == 200
    html_list = res_list.data.decode('utf-8')
    assert "Brand Management" in html_list

    # 4. GET /admin/brands/add
    res_add_get = client.get('/admin/brands/add')
    assert res_add_get.status_code == 200

    # 5. POST /admin/brands/add
    res_add_post = client.post('/admin/brands/add', data={
        'name': 'Razer Gaming',
        'slug': 'razer-gaming',
        'website': 'https://www.razer.com',
        'description': 'For Gamers. By Gamers.'
    }, follow_redirects=True)
    assert res_add_post.status_code == 200
    html_added = res_add_post.data.decode('utf-8')
    assert "Razer Gaming" in html_added

    # Fetch created brand ID
    with client.application.app_context():
        razer = stock_service.get_brand_by_slug('razer-gaming')
        assert razer is not None
        razer_id = razer.id

    # 6. GET /admin/brands/<id>/edit
    res_edit_get = client.get(f'/admin/brands/{razer_id}/edit')
    assert res_edit_get.status_code == 200

    # 7. POST /admin/brands/<id>/edit
    res_edit_post = client.post(f'/admin/brands/{razer_id}/edit', data={
        'name': 'Razer Inc.',
        'slug': 'razer-inc',
        'website': 'https://razer.com',
        'description': 'Updated description'
    }, follow_redirects=True)
    assert res_edit_post.status_code == 200
    html_edited = res_edit_post.data.decode('utf-8')
    assert "Razer Inc." in html_edited

    # 8. POST /admin/brands/<id>/delete
    res_del = client.post(f'/admin/brands/{razer_id}/delete', follow_redirects=True)
    assert res_del.status_code == 200

    with client.application.app_context():
        from models.brand import Brand
        assert db.session.get(Brand, razer_id) is None


def test_admin_category_routes_full_flow(client, sample_catalog):
    """
    Test full admin workflow for Categories:
    - GET /admin/categories
    - POST /admin/categories/add
    - GET & POST /admin/categories/<id>/edit
    - POST /admin/categories/<id>/delete
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # 1. GET /admin/categories
    res_list = client.get('/admin/categories')
    assert res_list.status_code == 200
    html = res_list.data.decode('utf-8')
    assert "Category Management" in html

    # 2. GET /admin/categories/add
    res_add_get = client.get('/admin/categories/add')
    assert res_add_get.status_code == 200

    # 3. POST /admin/categories/add
    res_add_post = client.post('/admin/categories/add', data={
        'name': 'Smart Watches',
        'slug': 'smart-watches'
    }, follow_redirects=True)
    assert res_add_post.status_code == 200
    assert "Smart Watches" in res_add_post.data.decode('utf-8')

    with client.application.app_context():
        sw_cat = stock_service.get_category_by_slug('smart-watches')
        assert sw_cat is not None
        sw_cat_id = sw_cat.id

    # 4. GET & POST /admin/categories/<id>/edit
    res_edit_get = client.get(f'/admin/categories/{sw_cat_id}/edit')
    assert res_edit_get.status_code == 200

    res_edit_post = client.post(f'/admin/categories/{sw_cat_id}/edit', data={
        'name': 'Wearables & Smart Watches',
        'slug': 'wearables'
    }, follow_redirects=True)
    assert res_edit_post.status_code == 200
    assert "Wearables" in res_edit_post.data.decode('utf-8')
    assert "wearables" in res_edit_post.data.decode('utf-8')

    # 5. POST /admin/categories/<id>/delete (no products linked)
    res_del = client.post(f'/admin/categories/{sw_cat_id}/delete', follow_redirects=True)
    assert res_del.status_code == 200

    with client.application.app_context():
        assert stock_service.get_category_by_id(sw_cat_id) is None


def test_admin_product_brand_assignment_flow(client, sample_catalog):
    """
    Test creating and editing a product with brand assignment in admin controllers.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # Create a brand first
    with client.application.app_context():
        dell = stock_service.create_brand(name="Dell Technologies")
        dell_id = dell.id

    # 1. Create product with brand_id
    cat_id = sample_catalog["cat_laptops_id"]
    res_add = client.post('/admin/products/add', data={
        'name': 'Dell XPS 15',
        'category_id': str(cat_id),
        'brand_id': str(dell_id),
        'sku': 'DELL-XPS-15',
        'spec_name': '32GB RAM / 1TB SSD',
        'price': '1999.00',
        'stock': '7'
    }, follow_redirects=True)
    assert res_add.status_code == 200

    # Verify DB
    with client.application.app_context():
        prod = Product.query.filter_by(name='Dell XPS 15').first()
        assert prod is not None
        assert prod.brand_id == dell_id
        assert prod.brand.name == "Dell Technologies"
        prod_id = prod.id

    # 2. Edit product to unassign brand
    res_edit = client.post(f'/admin/products/{prod_id}/edit', data={
        'name': 'Dell XPS 15 (Refurbished)',
        'category_id': str(cat_id),
        'brand_id': '',  # clear brand
        'is_active': '1'
    }, follow_redirects=True)
    assert res_edit.status_code == 200

    # Verify DB brand cleared
    with client.application.app_context():
        updated_prod = db.session.get(Product, prod_id)
        assert updated_prod.name == 'Dell XPS 15 (Refurbished)'
        assert updated_prod.brand_id is None


# ==========================================
# 14. XSS-Safe Keyword Highlighting & Storefront Filtering Tests
# ==========================================

def test_highlight_query_xss_safety_and_matching():
    """
    Test XSS-Safe Keyword Highlighting helper.
    Contract:
      - Neutralizes script tags into &lt;script&gt;
      - Wraps matched query into <mark class="search-highlight">
      - Case-insensitive matching
    """
    from helpers.highlight import highlight_query

    # 1. Standard match & case preservation
    res1 = highlight_query("Lenovo ThinkPad X1 Carbon", "thinkpad")
    assert '<mark class="search-highlight">ThinkPad</mark>' in str(res1)

    # 2. Empty query returns clean escaped string
    res2 = highlight_query("Regular Product Name", "")
    assert str(res2) == "Regular Product Name"
    assert "<mark" not in str(res2)

    # 3. None handling
    assert str(highlight_query(None, "test")) == ""

    # 4. CRITICAL ACCEPTANCE TEST: Neutralize <script>alert(1)</script>
    xss_val = "<script>alert(1)</script>"
    res_xss = highlight_query(xss_val, "alert")
    res_str = str(res_xss)

    # MUST NOT contain unescaped raw <script> tags
    assert "<script>" not in res_str
    assert "</script>" not in res_str

    # MUST contain properly escaped HTML entities with highlight
    assert "&lt;script&gt;<mark class=\"search-highlight\">alert</mark>(1)&lt;/script&gt;" == res_str

    # 5. Query containing raw script tags
    res_xss_query = highlight_query(xss_val, "<script>")
    res_query_str = str(res_xss_query)
    assert "<script>" not in res_query_str
    assert '<mark class="search-highlight">&lt;script&gt;</mark>' in res_query_str


def test_storefront_category_brand_and_search_filtering(client, sample_catalog):
    """
    Test storefront /products filtering by Category, Brand, and search query (q).
    Also tests searching with XSS payload to ensure safe response rendering.
    """
    with client.application.app_context():
        # Create brand & products
        asus = stock_service.create_brand(name="ASUS ROG", slug="asus-rog")
        cat_id = sample_catalog["cat_laptops_id"]
        prod = stock_service.create_product(
            name="ASUS ROG Zephyrus G16",
            category_id=cat_id,
            description="Ultra-slim high performance gaming laptop",
            price_cents=219900,
            stock=12,
            sku="ROG-G16-01",
            brand_id=asus.id
        )

    # 1. Filter by category slug
    res_cat = client.get('/products?category=laptops')
    assert res_cat.status_code == 200
    html_cat = res_cat.data.decode('utf-8')
    assert "ThinkPad X1 Carbon" in html_cat
    assert "ASUS ROG Zephyrus G16" in html_cat
    assert "iPhone 15 Pro" not in html_cat

    # 2. Filter by brand name
    res_brand = client.get('/products?brand=ASUS+ROG')
    assert res_brand.status_code == 200
    html_brand = res_brand.data.decode('utf-8')
    assert "ASUS ROG Zephyrus G16" in html_brand
    assert "ThinkPad X1 Carbon" not in html_brand

    # 3. Filter by search query (q)
    res_search = client.get('/products?q=Zephyrus')
    assert res_search.status_code == 200
    html_search = res_search.data.decode('utf-8')
    assert "ASUS ROG" in html_search
    assert '<mark class="search-highlight">Zephyrus</mark>' in html_search

    # 4. CRITICAL ACCEPTANCE TEST: Searching with XSS payload
    res_xss = client.get('/products?q=<script>alert(1)</script>')
    assert res_xss.status_code == 200
    html_xss = res_xss.data.decode('utf-8')

    # MUST NOT output raw executable <script>alert(1)</script>
    assert "<script>alert(1)</script>" not in html_xss
    # Properly escaped in value attributes or text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_xss or 'value="&lt;script&gt;alert(1)&lt;/script&gt;"' in html_xss or '&#039;' in html_xss or '&quot;' in html_xss


def test_api_products_with_category_brand_and_search(client, sample_catalog):
    """
    Test GET /api/products filtering by category, brand, and q.
    """
    with client.application.app_context():
        lenovo = stock_service.create_brand(name="Lenovo", slug="lenovo")
        tp = stock_service.get_product_by_id(sample_catalog["prod1_id"])
        stock_service.update_product(tp.id, brand_id=lenovo.id)

    # 1. Filter by category
    res_cat = client.get('/api/products?category=laptops')
    assert res_cat.status_code == 200
    data_cat = res_cat.get_json()
    assert data_cat["success"] is True
    assert any(p["name"] == "ThinkPad X1 Carbon" for p in data_cat["data"])
    assert not any(p["name"] == "iPhone 15 Pro" for p in data_cat["data"])

    # 2. Filter by brand
    res_brand = client.get('/api/products?brand=lenovo')
    assert res_brand.status_code == 200
    data_brand = res_brand.get_json()
    assert data_brand["success"] is True
    assert all("ThinkPad" in p["name"] for p in data_brand["data"])

    # 3. Filter by search
    res_search = client.get('/api/products?q=iPhone')
    assert res_search.status_code == 200
    data_search = res_search.get_json()
    assert data_search["success"] is True
    assert any("iPhone 15 Pro" in p["name"] for p in data_search["data"])


def test_admin_products_live_search_and_filtering(client, sample_catalog):
    """
    Test Admin /admin/products search by name, SKU, brand, and XSS safety.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['role'] = 'admin'

    # 1. Search by product name
    res_name = client.get('/admin/products?q=ThinkPad')
    assert res_name.status_code == 200
    html_name = res_name.data.decode('utf-8')
    assert "ThinkPad" in html_name
    assert '<mark class="search-highlight">ThinkPad</mark>' in html_name

    # 2. Search by variant SKU
    res_sku = client.get('/admin/products?q=TP-X1-DEF')
    assert res_sku.status_code == 200
    html_sku = res_sku.data.decode('utf-8')
    assert "ThinkPad" in html_sku
    assert "TP-X1-DEF" in html_sku

    # 3. Search with XSS input
    res_xss = client.get('/admin/products?q=<script>alert(1)</script>')
    assert res_xss.status_code == 200
    html_xss = res_xss.data.decode('utf-8')
    # Must not contain raw unescaped script tag
    assert "<script>alert(1)</script>" not in html_xss
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_xss or 'value="&lt;script&gt;alert(1)&lt;/script&gt;"' in html_xss or '&#039;' in html_xss or '&quot;' in html_xss







