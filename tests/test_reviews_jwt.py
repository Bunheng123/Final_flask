from datetime import timedelta
import pytest
import jwt
from extensions import db
from models.user import User
from models.category import Category
from models.product import Product
from models.product_variant import ProductVariant
from models.product_review import ProductReview
from models.order import Order
from models.order_item import OrderItem
from api.jwt_auth import create_access_token, decode_access_token, jwt_required, jwt_admin_required
from flask import jsonify, g


@pytest.fixture
def catalog_setup_ids(app):
    with app.app_context():
        cat = Category(name='Smartphones', slug='smartphones')
        db.session.add(cat)
        db.session.commit()

        prod = Product(
            name='Pixel 9 Pro',
            category_id=cat.id,
            description='Google Tensor G4 flagship',
            image='https://images.unsplash.com/photo-1598327105666-5b89351aff97',
            is_active=True
        )
        db.session.add(prod)
        db.session.commit()

        variant = ProductVariant(
            product_id=prod.id,
            sku='P9P-128-BLK',
            spec_name='128GB Obsidian',
            price_cents=99900,
            stock=10,
            is_active=True
        )
        db.session.add(variant)
        db.session.commit()

        return prod.id, variant.id


# ==========================================
# 1. JWT TESTS
# ==========================================

def test_jwt_create_and_decode(app):
    """create_access_token generates valid token decodable with correct payload."""
    with app.app_context():
        user = db.session.get(User, 2)
        token = create_access_token(user, expires_in=3600)
        assert isinstance(token, str)

        payload = decode_access_token(token)
        assert payload['user_id'] == 2
        assert payload['username'] == user.username
        assert payload['email'] == user.email
        assert payload['role'] == 'user'
        assert payload['exp'] > payload['iat']


def test_jwt_expired_token_rejected(app):
    """Expired JWT token raises ExpiredSignatureError."""
    with app.app_context():
        user = db.session.get(User, 2)
        # Create expired token (-10 seconds)
        expired_token = create_access_token(user, expires_in=-10)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(expired_token)


def test_api_auth_login_success(client):
    """POST /api/auth/login returns valid 24h Bearer token."""
    res = client.post('/api/auth/login', json={
        'email': 'user@techstore.test',
        'password': 'password123'
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert 'token' in data
    assert data['token_type'] == 'Bearer'
    assert data['expires_in'] == 86400
    assert data['user']['email'] == 'user@techstore.test'


def test_api_auth_login_invalid_credentials(client):
    """POST /api/auth/login rejects wrong password with 401."""
    res = client.post('/api/auth/login', json={
        'email': 'user@techstore.test',
        'password': 'wrongpassword'
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data['success'] is False


def test_api_auth_me_protected(client):
    """GET /api/auth/me requires valid Bearer token."""
    # 1. Request without token -> 401
    res_no_tok = client.get('/api/auth/me')
    assert res_no_tok.status_code == 401

    # 2. Login to get token
    res_login = client.post('/api/auth/login', json={
        'email': 'user@techstore.test',
        'password': 'password123'
    })
    token = res_login.get_json()['token']

    # 3. Request with valid token -> 200
    res_me = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
    assert res_me.status_code == 200
    data = res_me.get_json()
    assert data['success'] is True
    assert data['user']['username'] == 'test_user'


# ==========================================
# 2. REVIEWS & RATINGS TESTS
# ==========================================

def test_review_verified_purchase_enforcement(client, catalog_setup_ids):
    """User who has NOT purchased product is blocked from leaving a review."""
    prod_id, variant_id = catalog_setup_ids

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Attempt to review without purchase
    res = client.post(
        f'/product/{prod_id}/review',
        json={'rating': 5, 'comment': 'Great phone!'},
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res.status_code == 403
    data = res.get_json()
    assert data['success'] is False
    assert "verified" in data['error'].lower()


def test_review_submission_by_verified_purchaser(client, catalog_setup_ids):
    """User who has confirmed order can submit a 1-5 star review."""
    prod_id, variant_id = catalog_setup_ids

    prod = db.session.get(Product, prod_id)
    variant = db.session.get(ProductVariant, variant_id)

    # Create confirmed order for user 2
    order = Order(
        order_number='ORD-CONFIRMED-99',
        user_id=2,
        customer_name='Test User',
        email='user@techstore.test',
        phone='012345678',
        address='Phnom Penh',
        payment_method='khqr',
        status='confirmed',
        subtotal_cents=99900,
        total_cents=99900
    )
    db.session.add(order)
    db.session.flush()

    item = OrderItem(
        order_id=order.id,
        variant_id=variant.id,
        product_name=prod.name,
        sku=variant.sku,
        spec_name=variant.spec_name,
        qty=1,
        unit_price_cents=variant.price_cents,
        line_total_cents=variant.price_cents
    )
    db.session.add(item)
    db.session.commit()

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Submit review
    res = client.post(
        f'/product/{prod_id}/review',
        data={'rating': 5, 'comment': 'Outstanding battery life and display.'},
        follow_redirects=True
    )
    assert res.status_code == 200

    rev = ProductReview.query.filter_by(user_id=2, product_id=prod_id).first()
    assert rev is not None
    assert rev.rating == 5
    assert rev.comment == 'Outstanding battery life and display.'

    # Re-submitting updates the review
    res_update = client.post(
        f'/product/{prod_id}/review',
        data={'rating': 4, 'comment': 'Updated: Good, but gets slightly warm.'},
        follow_redirects=True
    )
    assert res_update.status_code == 200
    rev_up = ProductReview.query.filter_by(user_id=2, product_id=prod_id).first()
    assert rev_up.rating == 4
    assert ProductReview.query.filter_by(user_id=2, product_id=prod_id).count() == 1


def test_admin_review_moderation(client, catalog_setup_ids):
    """Admin can view reviews, toggle visibility, and delete spam."""
    prod_id, variant_id = catalog_setup_ids

    # Seed review
    rev = ProductReview(
        user_id=2,
        product_id=prod_id,
        rating=1,
        comment='Spam review test',
        is_visible=True
    )
    db.session.add(rev)
    db.session.commit()
    rev_id = rev.id

    # Login as admin
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['username'] = 'test_admin'
        sess['email'] = 'admin@techstore.test'
        sess['role'] = 'admin'
        sess['user_role'] = 'admin'

    # 1. Admin reviews dashboard
    res_dash = client.get('/admin/reviews')
    assert res_dash.status_code == 200
    assert b"Spam review test" in res_dash.data

    # 2. Toggle visibility (Hide)
    res_toggle = client.post(f'/admin/reviews/{rev_id}/toggle-visibility', follow_redirects=True)
    assert res_toggle.status_code == 200
    rev_after = db.session.get(ProductReview, rev_id)
    assert rev_after.is_visible is False

    # 3. Delete review
    res_del = client.post(f'/admin/reviews/{rev_id}/delete', follow_redirects=True)
    assert res_del.status_code == 200
    assert db.session.get(ProductReview, rev_id) is None
