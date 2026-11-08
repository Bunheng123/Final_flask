import pytest
from extensions import db
from models.user import User
from models.product import Product
from models.category import Category
from models.wishlist_item import WishlistItem


@pytest.fixture
def sample_product_id(app):
    with app.app_context():
        cat = Category.query.first()
        if not cat:
            cat = Category(name='Laptops', slug='laptops')
            db.session.add(cat)
            db.session.commit()

        prod = Product.query.first()
        if not prod:
            prod = Product(
                name='MacBook Pro 16',
                category_id=cat.id,
                description='Apple Silicon M3 Max',
                image='https://images.unsplash.com/photo-1517336714731-489689fd1ca8',
                is_active=True
            )
            db.session.add(prod)
            db.session.commit()
        return prod.id


def test_account_overview_requires_login(client):
    """GET /account redirects to /login when unauthenticated."""
    response = client.get('/account', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/login' in response.headers.get('Location', '')


def test_account_overview_renders_for_logged_in_user(client):
    """GET /account renders 200 OK without raising NotImplementedError."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    response = client.get('/account')
    assert response.status_code == 200
    assert b"Account Overview" in response.data or b"Account Dashboard" in response.data
    assert b"test_user" in response.data


def test_account_orders_renders_cleanly(client):
    """GET /account/orders renders 200 OK."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    response = client.get('/account/orders')
    assert response.status_code == 200
    assert b"Order History" in response.data or b"Orders" in response.data


def test_wishlist_unauthenticated_redirect(client):
    """Anonymous user accessing /wishlist is redirected to login."""
    res = client.get('/wishlist', follow_redirects=False)
    assert res.status_code in (301, 302)
    assert '/login' in res.headers.get('Location', '')


def test_wishlist_requires_login(client):
    """GET /wishlist redirects to /login when unauthenticated."""
    response = client.get('/wishlist', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/login' in response.headers.get('Location', '')


def test_wishlist_empty_view(client):
    """GET /wishlist renders 200 OK when empty."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    response = client.get('/wishlist')
    assert response.status_code == 200
    assert b"My Wishlist" in response.data


def test_wishlist_ajax_toggle_unauthenticated(client, sample_product_id):
    """Anonymous user toggling wishlist via AJAX receives 401 JSON."""
    res = client.post(
        f'/wishlist/toggle/{sample_product_id}',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res.status_code == 401
    data = res.get_json()
    assert data['success'] is False
    assert 'login_url' in data


def test_wishlist_toggle_add_and_remove(client, sample_product_id):
    """Authenticated user can toggle product in/out of wishlist."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # 1. Toggle Add
    res_add = client.post(
        f'/wishlist/toggle/{sample_product_id}',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res_add.status_code == 200
    data_add = res_add.get_json()
    assert data_add['success'] is True
    assert data_add['in_wishlist'] is True

    item = WishlistItem.query.filter_by(user_id=2, product_id=sample_product_id).first()
    assert item is not None

    # 2. View in Wishlist
    res_view = client.get('/wishlist')
    assert res_view.status_code == 200
    assert b"MacBook Pro 16" in res_view.data

    # 3. Toggle Remove
    res_rem = client.post(
        f'/wishlist/toggle/{sample_product_id}',
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )
    assert res_rem.status_code == 200
    data_rem = res_rem.get_json()
    assert data_rem['success'] is True
    assert data_rem['in_wishlist'] is False

    item_after = WishlistItem.query.filter_by(user_id=2, product_id=sample_product_id).first()
    assert item_after is None


def test_wishlist_add_and_remove(client):
    """POST /wishlist/add and /wishlist/remove add and delete items."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # 1. Add product 1 via JSON
    res_add = client.post('/wishlist/add', json={'product_id': 1})
    assert res_add.status_code == 200
    data = res_add.get_json()
    assert data['success'] is True
    assert data['in_wishlist'] is True

    # 2. View wishlist - should show product
    res_view = client.get('/wishlist')
    assert res_view.status_code == 200
    assert b"My Wishlist" in res_view.data

    # 3. Remove product 1 via JSON
    res_rem = client.post('/wishlist/remove', json={'product_id': 1})
    assert res_rem.status_code == 200
    data_rem = res_rem.get_json()
    assert data_rem['success'] is True
    assert data_rem['in_wishlist'] is False

    # 4. View wishlist again - should be empty
    res_empty = client.get('/wishlist')
    assert res_empty.status_code == 200
    assert b"Your wishlist is currently empty" in res_empty.data or b"My Wishlist" in res_empty.data


def test_wishlist_add_and_remove_endpoints(client, sample_product_id):
    """Test explicit /wishlist/add and /wishlist/remove routes."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Add endpoint
    res_add = client.post('/wishlist/add', json={'product_id': sample_product_id})
    assert res_add.status_code == 200
    assert res_add.get_json()['in_wishlist'] is True

    # Re-adding does not duplicate
    client.post('/wishlist/add', json={'product_id': sample_product_id})
    count = WishlistItem.query.filter_by(user_id=2, product_id=sample_product_id).count()
    assert count == 1

    # Remove endpoint
    res_rem = client.post('/wishlist/remove', json={'product_id': sample_product_id})
    assert res_rem.status_code == 200
    assert res_rem.get_json()['in_wishlist'] is False
    assert WishlistItem.query.filter_by(user_id=2, product_id=sample_product_id).count() == 0
