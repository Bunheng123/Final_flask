import pytest
from datetime import timedelta
from extensions import db, limiter
from models.user import User
from models.category import Category
from models.product import Product
from models.product_variant import ProductVariant
from models.order import Order
from models.order_item import OrderItem
from helpers.time import utc_now
from helpers.money import to_cents, format_money
from services.order_service import (
    transition_order,
    cancel_order_by_customer,
    confirm_pending_orders,
    is_order_cancellable_by_customer,
    get_order_payment_hash,
    create_order
)
from jobs.grace_period import check_grace_period_orders, auto_confirm_pending_orders_job

@pytest.fixture(autouse=True)
def mock_telegram_and_limiter(monkeypatch):
    """Disable external telegram network calls and reset limiter for isolated testing."""
    monkeypatch.setattr('helpers.telegram.send_telegram', lambda *args, **kwargs: None)
    monkeypatch.setattr('helpers.telegram.send_order_alert', lambda *args, **kwargs: None)
    monkeypatch.setattr('helpers.telegram.send_rate_limit_alert', lambda *args, **kwargs: None)
    limiter.reset()

@pytest.fixture
def test_setup(app):
    """Setup test category, product, and variant."""
    with app.app_context():
        cat = Category(name="Electronics", slug="electronics")
        db.session.add(cat)
        db.session.flush()

        prod = Product(name="Gaming Mouse", category_id=cat.id, description="High DPI", image="mouse.jpg", is_active=True)
        db.session.add(prod)
        db.session.flush()

        variant = ProductVariant(
            product_id=prod.id,
            sku="SKU-MOUSE-001",
            spec_name="RGB Edition",
            price_cents=5000,
            stock=20,
            is_active=True
        )
        db.session.add(variant)
        db.session.commit()

        yield {
            'cat_id': cat.id,
            'prod_id': prod.id,
            'variant_id': variant.id
        }


def test_order_creation_and_stock_decrement(app, test_setup):
    """Test order creation decrements variant stock and sets pending status."""
    with app.app_context():
        customer_data = {
            'first_name': 'John',
            'last_name': 'Doe',
            'email': 'john@example.com',
            'phone': '012345678',
            'address': 'Street 2004, Phnom Penh',
            'payment_method': 'bakong'
        }
        cart_items = [{
            'id': test_setup['variant_id'],
            'variant_id': test_setup['variant_id'],
            'name': 'Gaming Mouse',
            'price': 50.0,
            'qty': 2
        }]

        initial_stock = db.session.get(ProductVariant, test_setup['variant_id']).stock
        order = create_order(customer_data, cart_items)

        assert order.id is not None
        assert order.status == 'pending'
        assert order.subtotal_cents == 10000
        assert order.total_cents == 10000
        assert len(order.items) == 1
        assert order.items[0].qty == 2

        # Stock decremented by 2
        updated_variant = db.session.get(ProductVariant, test_setup['variant_id'])
        assert updated_variant.stock == initial_stock - 2


def test_forward_only_progression(app, test_setup):
    """Test strict forward lifecycle: pending -> confirmed -> shipped -> delivered."""
    with app.app_context():
        order = Order(
            order_number="ORD-TEST-001",
            customer_name="Alice",
            email="alice@example.com",
            phone="01111111",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=5000,
            total_cents=5000,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()

        # Direct jump from pending to delivered must FAIL
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_order(order.id, 'delivered')

        # Direct jump from pending to shipped must FAIL
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_order(order.id, 'shipped')

        # pending -> confirmed is valid
        order = transition_order(order.id, 'confirmed')
        assert order.status == 'confirmed'
        assert order.confirmed_at is not None

        # confirmed -> shipped is valid
        order = transition_order(order.id, 'shipped')
        assert order.status == 'shipped'
        assert order.shipped_at is not None

        # shipped -> delivered is valid
        order = transition_order(order.id, 'delivered')
        assert order.status == 'delivered'
        assert order.delivered_at is not None

        # Modifying a delivered order must FAIL
        with pytest.raises(ValueError, match="Invalid status transition"):
            transition_order(order.id, 'cancelled')


def test_customer_cancellation_within_4_hours(app, test_setup):
    """Customer can cancel order within 4 hours, restoring stock and crediting store credit."""
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        variant = db.session.get(ProductVariant, test_setup['variant_id'])
        initial_stock = variant.stock

        # Create order 1 hour ago
        order = Order(
            order_number="ORD-CANC-001",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012222222",
            address="Street 101, Phnom Penh",
            payment_method="bakong",
            status="pending",
            subtotal_cents=5000,
            total_cents=5000,
            created_at=utc_now() - timedelta(hours=1)
        )
        db.session.add(order)
        db.session.flush()

        item = OrderItem(
            order_id=order.id,
            variant_id=variant.id,
            product_name="Gaming Mouse",
            sku=variant.sku,
            spec_name=variant.spec_name,
            qty=3,
            unit_price_cents=5000,
            line_total_cents=15000
        )
        db.session.add(item)
        variant.stock -= 3
        db.session.commit()

        assert is_order_cancellable_by_customer(order, max_hours=4) is True

        # Customer cancels
        cancelled_order = cancel_order_by_customer(order.id, user_id=user.id)
        assert cancelled_order.status == 'cancelled'
        assert cancelled_order.cancelled_at is not None

        # Verify stock restored
        reloaded_variant = db.session.get(ProductVariant, variant.id)
        assert reloaded_variant.stock == initial_stock


def test_customer_cancellation_after_4_hours_rejected(app, test_setup):
    """Customer cancellation after 4 hours must be rejected."""
    with app.app_context():
        user = User.query.filter_by(role='user').first()

        # Create order 5 hours ago
        order = Order(
            order_number="ORD-EXPIRED-001",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012333333",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=5000,
            total_cents=5000,
            created_at=utc_now() - timedelta(hours=5)
        )
        db.session.add(order)
        db.session.commit()

        assert is_order_cancellable_by_customer(order, max_hours=4) is False

        with pytest.raises(ValueError, match="4-hour cancellation window"):
            cancel_order_by_customer(order.id, user_id=user.id)

        # Status must remain pending
        reloaded = db.session.get(Order, order.id)
        assert reloaded.status == 'pending'


def test_cannot_cancel_other_users_order(app):
    """Customer cannot cancel an order belonging to another user."""
    with app.app_context():
        order = Order(
            order_number="ORD-OTHER-001",
            user_id=999,  # Different user
            customer_name="Bob",
            email="bob@example.com",
            phone="012444444",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=2000,
            total_cents=2000,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()

        with pytest.raises(PermissionError, match="do not have permission"):
            cancel_order_by_customer(order.id, user_id=1)


def test_bakong_md5_hash_generation(app):
    """Test deterministic 32-character hexadecimal Bakong MD5 hash."""
    with app.app_context():
        order = Order(
            order_number="ORD-BAKONG-TEST",
            customer_name="Charlie",
            email="charlie@example.com",
            phone="012555555",
            address="Phnom Penh",
            payment_method="bakong",
            status="pending",
            subtotal_cents=10000,
            total_cents=10000,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()

        hash_str = get_order_payment_hash(order)
        assert len(hash_str) == 32
        assert all(c in "0123456789abcdef" for c in hash_str)
        # Property access
        assert order.bakong_hash == hash_str


def test_auto_confirm_pending_orders_job(app):
    """Scheduler job auto-confirms orders pending > 4 hours."""
    with app.app_context():
        old_order = Order(
            order_number="ORD-OLD-001",
            customer_name="David",
            email="david@example.com",
            phone="012666666",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=3000,
            total_cents=3000,
            created_at=utc_now() - timedelta(hours=5)
        )
        recent_order = Order(
            order_number="ORD-RECENT-001",
            customer_name="Eve",
            email="eve@example.com",
            phone="012777777",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=4000,
            total_cents=4000,
            created_at=utc_now() - timedelta(hours=1)
        )
        db.session.add(old_order)
        db.session.add(recent_order)
        db.session.commit()

        confirmed = confirm_pending_orders(grace_hours=4)
        assert old_order in confirmed
        assert recent_order not in confirmed

        reloaded_old = db.session.get(Order, old_order.id)
        assert reloaded_old.status == 'confirmed'
        assert reloaded_old.confirmed_at is not None

        reloaded_recent = db.session.get(Order, recent_order.id)
        assert reloaded_recent.status == 'pending'


def test_check_grace_period_orders_boundary_and_telegram_alert(app, monkeypatch):
    """
    Session 2: Verify check_grace_period_orders boundary logic:
    - 3h 59m old: NOT auto-confirmed.
    - 4h 01m old: Auto-confirmed.
    - Non-pending orders (e.g. cancelled): NOT modified.
    - Dispatches Telegram alert with Order ID, total amount via format_money(), and note of 4h expiration.
    """
    telegram_messages = []
    monkeypatch.setattr('jobs.grace_period.send_telegram', lambda msg: telegram_messages.append(msg))

    with app.app_context():
        now = utc_now()
        # Order 1: 3 hours 59 minutes old (Within grace window -> should NOT confirm)
        order_within = Order(
            order_number="ORD-WITHIN-GRACE",
            customer_name="Grace Within",
            email="within@example.com",
            phone="012999111",
            address="Phnom Penh",
            payment_method="bakong",
            status="pending",
            subtotal_cents=4500,
            total_cents=4500,
            created_at=now - timedelta(hours=3, minutes=59)
        )

        # Order 2: 4 hours 1 minute old (Expired grace window -> MUST auto-confirm)
        order_expired = Order(
            order_number="ORD-EXPIRED-GRACE",
            customer_name="Grace Expired",
            email="expired@example.com",
            phone="012999222",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=8500,
            total_cents=8500,
            created_at=now - timedelta(hours=4, minutes=1)
        )

        # Order 3: Cancelled order from 10 hours ago -> MUST NOT be confirmed
        order_cancelled = Order(
            order_number="ORD-CANCELLED-OLD",
            customer_name="Cancelled Old",
            email="cancelled@example.com",
            phone="012999333",
            address="Phnom Penh",
            payment_method="cod",
            status="cancelled",
            subtotal_cents=6000,
            total_cents=6000,
            created_at=now - timedelta(hours=10)
        )

        db.session.add(order_within)
        db.session.add(order_expired)
        db.session.add(order_cancelled)
        db.session.commit()

        # Run the periodic grace period job
        confirmed = check_grace_period_orders(grace_hours=4)

        # Assertions
        assert order_expired in confirmed
        assert order_within not in confirmed
        assert order_cancelled not in confirmed

        reloaded_expired = db.session.get(Order, order_expired.id)
        assert reloaded_expired.status == 'confirmed'
        assert reloaded_expired.confirmed_at is not None

        reloaded_within = db.session.get(Order, order_within.id)
        assert reloaded_within.status == 'pending'

        reloaded_cancelled = db.session.get(Order, order_cancelled.id)
        assert reloaded_cancelled.status == 'cancelled'

        # Telegram notification checks
        assert len(telegram_messages) == 1
        msg = telegram_messages[0]
        assert "ORD-EXPIRED-GRACE" in msg
        assert "Grace Expired" in msg
        assert format_money(8500) in msg  # $85.00
        assert "4-hour grace window expired" in msg
        assert "CONFIRMED" in msg


def test_scheduler_registration_and_configuration(app):
    """
    Session 2: Verify APScheduler job registration when SCHEDULER_ENABLED is True.
    """
    from jobs import init_scheduler, scheduler

    # Temporarily set SCHEDULER_ENABLED = True and TESTING = False to verify init_scheduler behavior
    test_app = app
    test_app.config['SCHEDULER_ENABLED'] = True
    test_app.config['TESTING'] = False

    try:
        s = init_scheduler(test_app)
        if s is not None:
            job = s.get_job('grace_period_auto_confirm')
            assert job is not None
            assert job.id == 'grace_period_auto_confirm'
            assert job.max_instances == 1
    finally:
        test_app.config['TESTING'] = True


def test_admin_orders_views(client, app):
    """Admin can view orders list and access JSON order details."""
    with app.app_context():
        admin = User.query.filter_by(role='admin').first()
        admin_id = admin.id

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = admin_id
        sess['username'] = 'admin'
        sess['role'] = 'admin'

    # View orders list
    res = client.get('/admin/orders')
    assert res.status_code == 200
    assert b"Order Management" in res.data


def test_customer_order_cancellation_endpoint(client, app):
    """Customer can cancel pending order via POST /account/orders/<id>/cancel."""
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        order = Order(
            order_number="ORD-CUST-POST-01",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012888888",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=2500,
            total_cents=2500,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id
        user_id = user.id

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = user_id
        sess['username'] = 'user'
        sess['role'] = 'user'

    # Cancel order
    cancel_res = client.post(f'/account/orders/{order_id}/cancel', follow_redirects=True)
    assert cancel_res.status_code == 200

    with app.app_context():
        cancelled = db.session.get(Order, order_id)
        assert cancelled.status == 'cancelled'


# ==============================================================================
# SESSION 3: NOTIFICATION ENGINE & NAVBAR ALERTS TESTS
# ==============================================================================
from models.notification import Notification
from services.notification_service import (
    notify_user,
    get_unread_count,
    mark_as_read,
    mark_all_as_read,
    get_user_notifications
)

def test_notification_model_and_service_crud(app):
    """
    Session 3: Test notify_user, get_unread_count, mark_as_read, mark_all_as_read.
    """
    with app.app_context():
        user = User.query.filter_by(role='user').first()

        # Initial unread count should be 0
        assert get_unread_count(user.id) == 0

        # Dispatch notification
        n1 = notify_user(user.id, "Welcome!", "Thank you for joining TechStore.", type="system")
        assert n1 is not None
        assert n1.user_id == user.id
        assert n1.title == "Welcome!"
        assert n1.is_read is False
        assert n1.created_at is not None

        # Dispatch second notification
        n2 = notify_user(user.id, "Order Confirmed", "Your order has been confirmed.", type="order")
        assert n2 is not None

        # Count should now be 2
        assert get_unread_count(user.id) == 2

        # Mark single notification as read
        assert mark_as_read(n1.id, user.id) is True
        assert get_unread_count(user.id) == 1

        # Mark all as read
        updated_count = mark_all_as_read(user.id)
        assert updated_count == 1
        assert get_unread_count(user.id) == 0


def test_notification_triggered_on_customer_cancellation(app, test_setup):
    """
    Session 3: Customer cancellation emits 'credit' in-app notification.
    """
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        order = Order(
            order_number="ORD-NOTIF-CANC",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012333444",
            address="Phnom Penh",
            payment_method="bakong",
            status="pending",
            subtotal_cents=7500,
            total_cents=7500,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()

        cancel_order_by_customer(order.id, user_id=user.id)

        # Check notification
        notifs = get_user_notifications(user.id)
        assert len(notifs) >= 1
        refund_notif = next((n for n in notifs if "Cancelled" in n.title), None)
        assert refund_notif is not None
        assert refund_notif.type == "credit"
        assert "$75.00" in refund_notif.message
        assert refund_notif.is_read is False


def test_notification_triggered_on_grace_period_auto_confirm(app):
    """
    Session 3: Grace period auto-confirmation emits in-app notification.
    """
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        order = Order(
            order_number="ORD-NOTIF-AUTO",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012333555",
            address="Phnom Penh",
            payment_method="cod",
            status="pending",
            subtotal_cents=3200,
            total_cents=3200,
            created_at=utc_now() - timedelta(hours=5)
        )
        db.session.add(order)
        db.session.commit()

        check_grace_period_orders(grace_hours=4)

        notifs = get_user_notifications(user.id)
        auto_notif = next((n for n in notifs if "Auto-Confirmed" in n.title), None)
        assert auto_notif is not None
        assert auto_notif.type == "order"
        assert "4-hour grace period" in auto_notif.message


def test_notification_triggered_on_admin_status_transitions(app):
    """
    Session 3: Admin status transitions (shipped, delivered) trigger customer notifications.
    """
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        order = Order(
            order_number="ORD-NOTIF-TRANS",
            user_id=user.id,
            customer_name=user.username,
            email=user.email,
            phone="012333666",
            address="Phnom Penh",
            payment_method="cod",
            status="confirmed",
            subtotal_cents=5000,
            total_cents=5000,
            created_at=utc_now()
        )
        db.session.add(order)
        db.session.commit()

        # Transition to shipped
        transition_order(order.id, 'shipped')
        notifs = get_user_notifications(user.id)
        shipped_notif = next((n for n in notifs if "Shipped" in n.title), None)
        assert shipped_notif is not None
        assert "on the way" in shipped_notif.message

        # Transition to delivered
        transition_order(order.id, 'delivered')
        notifs2 = get_user_notifications(user.id)
        delivered_notif = next((n for n in notifs2 if "Delivered" in n.title), None)
        assert delivered_notif is not None
        assert "arrived safely" in delivered_notif.message


def test_notification_routes_and_navbar_bell(client, app):
    """
    Session 3: Storefront /notifications inbox and mark read endpoints.
    """
    with app.app_context():
        user = User.query.filter_by(role='user').first()
        user_id = user.id
        n = notify_user(user_id, "Special Promotion", "Get 10% off your next purchase!", type="system")
        notif_id = n.id

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = user_id
        sess['username'] = 'user'
        sess['role'] = 'user'

    # 1. Customer views inbox
    res_inbox = client.get('/notifications')
    assert res_inbox.status_code == 200
    assert b"Notifications" in res_inbox.data
    assert b"Special Promotion" in res_inbox.data

    # 2. Navbar bell count endpoint
    res_api = client.get('/api/notifications/unread-count')
    assert res_api.status_code == 200
    assert res_api.get_json()['unread_count'] >= 1

    # 3. Mark single notification as read via AJAX
    res_read = client.post(
        f'/notifications/{notif_id}/read',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res_read.status_code == 200
    assert res_read.get_json()['success'] is True

    # 4. Mark all as read via AJAX
    res_read_all = client.post(
        '/notifications/read-all',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res_read_all.status_code == 200
    assert res_read_all.get_json()['unread_count'] == 0
