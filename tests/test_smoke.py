import pytest
from models.user import User

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

def test_admin_login_and_register_redirects(client):
    """GET /admin/login and /admin/register redirect (302) to /login and /register with query string preserved."""
    res_login = client.get('/admin/login?next=/admin/dashboard&src=bookmark', follow_redirects=False)
    assert res_login.status_code in (301, 302)
    loc = res_login.headers.get('Location', '')
    assert '/login' in loc
    assert 'next=%2Fadmin%2Fdashboard' in loc or 'next=/admin/dashboard' in loc
    assert 'src=bookmark' in loc

    res_reg = client.get('/admin/register?promo=true', follow_redirects=False)
    assert res_reg.status_code in (301, 302)
    loc_reg = res_reg.headers.get('Location', '')
    assert '/register' in loc_reg
    assert 'promo=true' in loc_reg

def test_admin_logs_in_and_lands_on_dashboard(client):
    """Admin logs in at /login and lands on dashboard."""
    response = client.post('/login', data={
        'email': 'admin@techstore.test',
        'password': 'password123'
    }, follow_redirects=False)
    assert response.status_code in (301, 302)
    assert response.headers.get('Location', '').endswith('/admin/dashboard')

def test_user_logs_in_and_lands_on_home(client):
    """User with role 'user' logs in at /login and lands on home page."""
    response = client.post('/login', data={
        'email': 'user@techstore.test',
        'password': 'password123'
    }, follow_redirects=False)
    assert response.status_code in (301, 302)
    loc = response.headers.get('Location', '')
    assert loc == '/' or loc.endswith('/')

def test_logged_out_admin_redirect_and_return(client):
    """
    Logged-out request to /admin redirects to /login?next=/admin/...
    After login, the admin returns to that target page.
    """
    target = '/admin/user'
    res_guard = client.get(target, follow_redirects=False)
    assert res_guard.status_code in (301, 302)
    loc = res_guard.headers.get('Location', '')
    assert '/login' in loc
    assert 'next=' in loc

    # Login as admin with next=target
    res_login = client.post(f'/login?next={target}', data={
        'email': 'admin@techstore.test',
        'password': 'password123'
    }, follow_redirects=False)
    assert res_login.status_code in (301, 302)
    assert res_login.headers.get('Location', '').endswith(target)

def test_user_with_admin_next_redirected_to_home(client):
    """A user with role 'user' who has next=/admin/dashboard is sent to home, not /admin."""
    response = client.post('/login?next=/admin/dashboard', data={
        'email': 'user@techstore.test',
        'password': 'password123'
    }, follow_redirects=False)
    assert response.status_code in (301, 302)
    loc = response.headers.get('Location', '')
    assert '/admin' not in loc
    assert loc == '/' or loc.endswith('/')

def test_user_cannot_access_admin_route(client):
    """A logged-in user with role 'user' requesting any /admin route is blocked with 403."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'
        sess['user_role'] = 'user'

    response = client.get('/admin/dashboard', follow_redirects=False)
    assert response.status_code == 403

def test_register_always_creates_role_user(client):
    """Register at /register always creates role 'user', even when client submits role='admin'."""
    response = client.post('/register', data={
        'username': 'attempted_hacker',
        'email': 'hacker@techstore.test',
        'password': 'safePassword123',
        'confirm_password': 'safePassword123',
        'role': 'admin'  # Should be ignored!
    }, follow_redirects=False)
    assert response.status_code in (301, 302)

    from extensions import db
    created = User.query.filter_by(email='hacker@techstore.test').first()
    assert created is not None
    assert created.role == 'user'

def test_admin_logout_get_vs_post(client):
    """
    GET /admin/logout does not log the user out.
    POST /logout logs out the user with CSRF.
    """
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 1
        sess['username'] = 'test_admin'
        sess['email'] = 'admin@techstore.test'
        sess['role'] = 'admin'

    # GET /admin/logout should NOT log out
    get_res = client.get('/admin/logout', follow_redirects=False)
    assert get_res.status_code in (301, 302)
    with client.session_transaction() as sess:
        assert sess.get('is_login') is True

    # POST /logout SHOULD log out
    post_res = client.post('/logout', follow_redirects=False)
    assert post_res.status_code in (301, 302)
    with client.session_transaction() as sess:
        assert sess.get('is_login') is None or sess.get('is_login') is False

def test_api_users_requires_admin_session(client):
    """/api/users and /api/user/<id> require an admin session (401 otherwise)."""
    # 1. Unauthenticated request
    res_unauth = client.get('/api/users')
    assert res_unauth.status_code == 401

    # 2. Authenticated as role 'user'
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'user'
    res_user = client.get('/api/users')
    assert res_user.status_code == 401

    # 3. Authenticated as role 'admin'
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'admin'
    res_admin = client.get('/api/users')
    assert res_admin.status_code == 200

def test_stubs_501_on_post(client):
    """Unimplemented stubs must return 501 on POST."""
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['role'] = 'user'

    assert client.post('/account').status_code == 501
    assert client.post('/account/orders').status_code == 501
    assert client.post('/account/orders/ORD-001').status_code == 501
    assert client.post('/forgot-password').status_code == 501
    assert client.post('/reset-password/sample-token').status_code == 501

def test_rate_limit_login(client, monkeypatch):
    """The 6th POST in a minute to /login returns 429."""
    from extensions import limiter
    limiter.reset()

    # Mock Telegram alert to avoid external calls
    monkeypatch.setattr('helpers.telegram.send_rate_limit_alert', lambda *args, **kwargs: None)
    monkeypatch.setattr('helpers.telegram.send_telegram', lambda *args, **kwargs: None)

    # 5 attempts: fail credentials -> 400
    for _ in range(5):
        res = client.post('/login', data={'email': 'wrong@test.com', 'password': 'wrong'})
        assert res.status_code == 400

    # 6th attempt -> 429 Too Many Requests
    res_6th = client.post('/login', data={'email': 'wrong@test.com', 'password': 'wrong'})
    assert res_6th.status_code == 429

    limiter.reset()

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
