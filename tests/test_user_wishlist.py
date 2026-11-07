import pytest
from extensions import db
from models.user import User
from models.product import Product
from models.wishlist_item import WishlistItem


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
    assert b"Account Overview" in response.data
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
    assert b"Order History" in response.data


def test_wishlist_requires_login(client):
    """GET /wishlist redirects to /login when unauthenticated."""
    response = client.get('/wishlist', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/login' in response.headers.get('Location', '')


def test_wishlist_empty_view(client):
    """GET /wishlist renders 200 OK without raising NotImplementedError."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    response = client.get('/wishlist')
    assert response.status_code == 200
    assert b"My Wishlist" in response.data


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
    assert b"MSI Katana 15" in res_view.data or b"View Product" in res_view.data

    # 3. Remove product 1 via JSON
    res_rem = client.post('/wishlist/remove', json={'product_id': 1})
    assert res_rem.status_code == 200
    data_rem = res_rem.get_json()
    assert data_rem['success'] is True
    assert data_rem['in_wishlist'] is False

    # 4. View wishlist again - should be empty
    res_empty = client.get('/wishlist')
    assert res_empty.status_code == 200
    assert b"Your wishlist is currently empty" in res_empty.data

