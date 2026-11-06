def test_home_page_status_200(client):
    """Storefront home page should return 200 OK."""
    response = client.get('/')
    assert response.status_code == 200
    assert b"TechStore" in response.data

def test_api_products_status_200(client):
    """API products endpoint should return 200 OK with JSON array."""
    response = client.get('/api/products')
    assert response.status_code == 200
    json_data = response.get_json()
    assert json_data['success'] is True
    assert json_data['count'] > 0
    assert isinstance(json_data['data'], list)

def test_admin_redirects_when_logged_out(client):
    """Unauthenticated access to /admin/dashboard must redirect to /admin/login."""
    response = client.get('/admin/dashboard', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/admin/login' in response.headers.get('Location', '')

def test_non_admin_cannot_access_admin(client):
    """A logged-in user with role != 'admin' must be blocked from admin routes."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'
        sess['user_role'] = 'user'

    response = client.get('/admin/dashboard', follow_redirects=False)
    assert response.status_code in (301, 302)
    assert '/admin/login' in response.headers.get('Location', '')

def test_admin_can_access_admin(client):
    """A logged-in user with role == 'admin' can access admin dashboard."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['username'] = 'test_admin'
        sess['email'] = 'admin@techstore.test'
        sess['role'] = 'admin'
        sess['user_role'] = 'admin'

    response = client.get('/admin/dashboard')
    assert response.status_code == 200

def test_money_helpers():
    """Verify cents conversion and formatting."""
    from helpers.money import to_cents, from_cents, format_money
    assert to_cents(12.99) == 1299
    assert to_cents("12.99") == 1299
    assert to_cents(10) == 1000
    assert to_cents(None) == 0
    assert from_cents(1299) == 12.99
    assert from_cents(0) == 0.0
    assert format_money(1299) == "$12.99"

def test_time_helpers():
    """Verify timezone-naive UTC now and local conversion."""
    from helpers.time import utc_now, to_local
    now = utc_now()
    assert now.tzinfo is None
    local_time = to_local(now)
    assert local_time.tzinfo is not None
