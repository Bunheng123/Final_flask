import io
from datetime import timedelta
import pytest
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from models.user import User
from models.order import Order
from models.order_item import OrderItem
from helpers.time import utc_now


def test_account_requires_login(client):
    """GET /account without session redirects to /login."""
    response = client.get('/account', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/login' in response.headers.get('Location', '')


def test_account_profile_update(client):
    """Customer can update username and email."""
    # Login as regular user
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Valid profile update
    res = client.post('/account', data={
        'action': 'update_profile',
        'username': 'updated_test_user',
        'email': 'updated_user@techstore.test'
    }, follow_redirects=True)
    assert res.status_code == 200

    u = User.query.get(2)
    assert u.username == 'updated_test_user'
    assert u.email == 'updated_user@techstore.test'


def test_account_profile_update_duplicate_rejected(client):
    """Customer cannot change email or username to one already used by another user."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Admin user has email 'admin@techstore.test' and username 'test_admin'
    res = client.post('/account', data={
        'action': 'update_profile',
        'username': 'test_admin',
        'email': 'user@techstore.test'
    }, follow_redirects=True)
    assert b"Username is already taken" in res.data

    res2 = client.post('/account', data={
        'action': 'update_profile',
        'username': 'test_user_ok',
        'email': 'admin@techstore.test'
    }, follow_redirects=True)
    assert b"Email is already in use" in res2.data


def test_account_avatar_upload(client):
    """Customer can upload a profile avatar and generate a thumbnail."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Create dummy in-memory image
    img_byte_arr = io.BytesIO()
    image = Image.new('RGB', (400, 400), color='blue')
    image.save(img_byte_arr, format='JPEG')
    img_byte_arr.seek(0)

    res = client.post('/account', data={
        'action': 'update_profile',
        'username': 'test_user',
        'email': 'user@techstore.test',
        'profile': (img_byte_arr, 'avatar.jpg')
    }, content_type='multipart/form-data', follow_redirects=True)

    assert res.status_code == 200
    u = User.query.get(2)
    assert u.profile is not None
    assert '_org_' in u.profile


def test_account_password_change(client):
    """Customer password change verifies current password and enforces rules."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Wrong current password
    res = client.post('/account', data={
        'action': 'change_password',
        'current_password': 'wrongpassword',
        'new_password': 'newpassword123',
        'confirm_password': 'newpassword123'
    }, follow_redirects=True)
    assert b"Current password is incorrect" in res.data

    # Password too short (<8)
    res_short = client.post('/account', data={
        'action': 'change_password',
        'current_password': 'password123',
        'new_password': 'short',
        'confirm_password': 'short'
    }, follow_redirects=True)
    assert b"at least 8 characters" in res_short.data

    # Password mismatch
    res_mismatch = client.post('/account', data={
        'action': 'change_password',
        'current_password': 'password123',
        'new_password': 'newpassword123',
        'confirm_password': 'mismatchpassword123'
    }, follow_redirects=True)
    assert b"Passwords do not match" in res_mismatch.data

    # Valid change
    res_valid = client.post('/account', data={
        'action': 'change_password',
        'current_password': 'password123',
        'new_password': 'newpassword123',
        'confirm_password': 'newpassword123'
    }, follow_redirects=True)
    assert b"Password updated successfully" in res_valid.data

    u = User.query.get(2)
    assert check_password_hash(u.password, 'newpassword123')


def test_customer_order_history_and_cancel_grace_period(client):
    """Customer can view orders and self-cancel within 4 hours."""
    # Seed order for user 2
    order = Order(
        order_number='ORD-TEST-001',
        user_id=2,
        customer_name='Test User',
        email='user@techstore.test',
        phone='012345678',
        address='Phnom Penh, Cambodia',
        payment_method='khqr',
        status='pending',
        subtotal_cents=5000,
        total_cents=5000,
        created_at=utc_now()
    )
    db.session.add(order)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # View orders list
    res = client.get('/account/orders')
    assert res.status_code == 200
    assert b"ORD-TEST-001" in res.data

    # View order detail
    res_det = client.get('/account/orders/ORD-TEST-001')
    assert res_det.status_code == 200
    assert b"Cancellation Window Active" in res_det.data

    # Cancel order within grace period
    res_cancel = client.post('/account/orders/ORD-TEST-001/cancel', follow_redirects=True)
    assert res_cancel.status_code == 200
    assert b"cancelled successfully" in res_cancel.data

    updated = Order.query.filter_by(order_number='ORD-TEST-001').first()
    assert updated.status == 'cancelled'


def test_customer_order_history_filters_and_search(client):
    """Customer order history filtering by status and searching by order number."""
    # Seed orders with different statuses for user 2
    order_pending = Order(
        order_number='ORD-FILTER-P1',
        user_id=2,
        customer_name='Test User',
        email='user@techstore.test',
        phone='012345678',
        address='Phnom Penh, Cambodia',
        payment_method='cod',
        status='pending',
        subtotal_cents=1000,
        total_cents=1000,
        created_at=utc_now()
    )
    order_delivered = Order(
        order_number='ORD-FILTER-D1',
        user_id=2,
        customer_name='Test User',
        email='user@techstore.test',
        phone='012345678',
        address='Phnom Penh, Cambodia',
        payment_method='khqr',
        status='delivered',
        subtotal_cents=2500,
        total_cents=2500,
        created_at=utc_now()
    )
    db.session.add_all([order_pending, order_delivered])
    db.session.commit()

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Filter status=pending
    res_pending = client.get('/account/orders?status=pending')
    assert res_pending.status_code == 200
    assert b"ORD-FILTER-P1" in res_pending.data
    assert b"ORD-FILTER-D1" not in res_pending.data

    # Filter status=delivered
    res_delivered = client.get('/account/orders?status=delivered')
    assert res_delivered.status_code == 200
    assert b"ORD-FILTER-D1" in res_delivered.data
    assert b"ORD-FILTER-P1" not in res_delivered.data

    # Search by order number query
    res_search = client.get('/account/orders?q=FILTER-P1')
    assert res_search.status_code == 200
    assert b"ORD-FILTER-P1" in res_search.data
    assert b"ORD-FILTER-D1" not in res_search.data


def test_customer_order_cancel_expired_rejected(client):
    """Customer cannot cancel an order older than 4 hours."""
    # Seed an old order
    old_order = Order(
        order_number='ORD-OLD-002',
        user_id=2,
        customer_name='Test User',
        email='user@techstore.test',
        phone='012345678',
        address='Phnom Penh, Cambodia',
        payment_method='khqr',
        status='pending',
        subtotal_cents=5000,
        total_cents=5000,
        created_at=utc_now() - timedelta(hours=5)
    )
    db.session.add(old_order)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    res_cancel = client.post('/account/orders/ORD-OLD-002/cancel', follow_redirects=True)
    assert b"4-hour cancellation window for this order has expired" in res_cancel.data

    unchanged = Order.query.filter_by(order_number='ORD-OLD-002').first()
    assert unchanged.status == 'pending'

