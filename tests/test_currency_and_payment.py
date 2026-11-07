import json
import pytest
from extensions import db
from helpers.currency import (
    khr_format,
    usd_format,
    khr_from_usd,
    usd_from_khr,
    normalize_khr,
)
from services.khqr_service import (
    generate_khqr,
    get_payment_status,
    mark_payment_paid,
    validate_khr_tag54,
    build_khqr_payload,
    qr_image_base64_uri,
)
from services.wallet_service import (
    compute_split_payment,
    reserve_wallet_balance,
)


def test_currency_helpers():
    assert khr_format(42000) == '42,000 ៛'
    assert usd_format(42000) == '≈ $10.24'
    assert khr_from_usd(10.5) == 43050
    assert khr_from_usd(0) == 0
    assert usd_from_khr(4100) == 1.00
    assert normalize_khr(None) == 0
    assert normalize_khr("5000.4") == 5000


def test_wallet_split_logic():
    # Split payment
    split = compute_split_payment(5000, 1500)
    assert split['payment_mode'] == 'split'
    assert split['wallet_used_khr'] == 1500
    assert split['khqr_remaining_khr'] == 3500

    # Full wallet payment
    full_wallet = compute_split_payment(5000, 10000)
    assert full_wallet['payment_mode'] == 'wallet'
    assert full_wallet['wallet_used_khr'] == 5000
    assert full_wallet['khqr_remaining_khr'] == 0

    # Zero wallet -> khqr
    full_khqr = compute_split_payment(5000, 0)
    assert full_khqr['payment_mode'] == 'khqr'
    assert full_khqr['wallet_used_khr'] == 0
    assert full_khqr['khqr_remaining_khr'] == 5000


def test_wallet_reserve_balance():
    res = reserve_wallet_balance(10000, 4000)
    assert res['remaining_balance_khr'] == 6000
    assert res['amount_khr'] == 4000

    with pytest.raises(ValueError, match=r'(?i)insufficient'):
        reserve_wallet_balance(2000, 5000)

    with pytest.raises(ValueError, match=r'(?i)negative'):
        reserve_wallet_balance(2000, -500)


def test_khqr_tag54_validation():
    assert validate_khr_tag54(50000) == 50000
    with pytest.raises(ValueError, match=r'(?i)negative'):
        validate_khr_tag54(-100)


def test_khqr_payload_builder():
    payload = build_khqr_payload('REF-123', 82000, merchant_name='Store A')
    assert payload['merchant_name'] == 'Store A'
    assert payload['currency'] == 'KHR'
    assert payload['tag_54_khr_amount'] == 82000
    assert payload['is_emvco_like'] is True


def test_khqr_reference_generation_and_polling(monkeypatch):
    payment = generate_khqr(reference='demo-order', amount_khr=42000)
    assert payment['status'] == 'pending'
    assert payment['tag_54_khr_amount'] == 42000
    assert 'data:image/png;base64,' in payment['qr_image_base64']
    assert 'data:image/png;base64,' in payment['base64_uri']

    class PendingPaymentClient:
        def check_payment(self, payment_hash):
            assert payment_hash == payment['reference_md5']
            return 'UNPAID'

    monkeypatch.setattr('services.khqr_service.get_khqr_client', lambda: PendingPaymentClient())
    monkeypatch.setattr('services.khqr_service.get_khqr_config', lambda: {'token': 'test-token'})
    status = get_payment_status(payment['reference_md5'])
    assert status['success'] is True
    assert status['data']['reference'] == 'demo-order'
    assert status['data']['status'] == 'pending'
    assert status['data']['bakong_status'] == 'UNPAID'

    # Mark paid
    paid = mark_payment_paid(payment['reference_md5'])
    assert paid['success'] is True
    assert paid['data']['status'] == 'paid'
    assert 'paid_at' in paid['data']

    # Non-existent reference
    missing = get_payment_status('non-existent-hash')
    assert missing['success'] is False
    assert missing['status'] == 'not_found'


def test_qr_image_base64_uri_helper():
    payment = generate_khqr(reference='test-helper', amount_khr=25000)
    if payment.get('qr_string'):
        uri = qr_image_base64_uri(payment['qr_string'])
        assert uri.startswith('data:image/png;base64,')


def test_generate_khqr_uses_bakong_base64_uri_renderer(monkeypatch):
    class FakeKhqrClient:
        def __init__(self):
            self.image_format = None

        def create_qr(self, **kwargs):
            return {'data': {'qr': 'real-khqr-payload', 'md5': 'payment-md5'}}

        def qr_image(self, qr_string, format):
            assert qr_string == 'real-khqr-payload'
            self.image_format = format
            return 'data:image/png;base64,bakong-rendered-image'

    client = FakeKhqrClient()
    monkeypatch.setattr('services.khqr_service.get_khqr_client', lambda: client)

    payment = generate_khqr(reference='sdk-render-check', amount_khr=25000)

    assert client.image_format == 'base64_uri'
    assert payment['base64_uri'] == 'data:image/png;base64,bakong-rendered-image'


def test_api_payment_check_endpoint(client, monkeypatch):
    # 1. Non-existent payment hash -> 404
    resp = client.get('/api/payment/check/invalid_hash_12345')
    assert resp.status_code == 404
    data = resp.get_json()
    assert data['success'] is False
    assert data['status'] == 'not_found'

    # 2. Existing payment hash -> 200
    payment = generate_khqr(reference='api-test-order', amount_khr=20500)
    class PaidPaymentClient:
        def check_payment(self, payment_hash):
            assert payment_hash == payment['reference_md5']
            return 'PAID'

    monkeypatch.setattr('services.khqr_service.get_khqr_client', lambda: PaidPaymentClient())
    monkeypatch.setattr('services.khqr_service.get_khqr_config', lambda: {'token': 'test-token'})
    resp2 = client.get(f"/api/payment/check/{payment['reference_md5']}")
    assert resp2.status_code == 200
    data2 = resp2.get_json()
    assert data2['success'] is True
    assert data2['data']['reference'] == 'api-test-order'
    assert data2['data']['amount_khr'] == 20500
    assert data2['data']['status'] == 'paid'
    assert 'paid_at' in data2['data']


def test_checkout_payment_integration(client, app, monkeypatch):
    # Mock telegram sending to avoid background thread network calls
    monkeypatch.setattr('helpers.telegram.send_telegram', lambda *args, **kwargs: None)

    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'

    # Set cart cookie with a mock item
    cart_data = [
        {'id': 1, 'name': 'Test Laptop', 'price': 10.0, 'qty': 2, 'image': 'laptop.png'}
    ]
    client.set_cookie('cart_list', json.dumps(cart_data))

    # 1. GET /checkout should display KHR and USD amounts, and include base64_uri image
    res_get = client.get('/checkout')
    assert res_get.status_code == 200
    assert b"TechStore" in res_get.data
    assert b'data:image/png;base64,' not in res_get.data

    # 2. POST /checkout with payment='khqr'
    res_post_khqr = client.post('/checkout', data={
        'first_name': 'John',
        'last_name': 'Doe',
        'email': 'john@example.com',
        'phone': '012345678',
        'address': '123 Street, Phnom Penh',
        'payment': 'khqr',
        'wallet_balance_khr': '0',
    })
    assert res_post_khqr.status_code == 200
    assert b"Order awaiting payment" in res_post_khqr.data
    assert b"Order placed successfully!</h2>" not in res_post_khqr.data
    assert b'role="dialog" aria-modal="true"' in res_post_khqr.data
    assert b"Scan to pay with KHQR" in res_post_khqr.data
    assert b"data:image/png;base64," in res_post_khqr.data
    assert b'data-checkout-url="/checkout"' in res_post_khqr.data
    assert b'window.location.assign(checkoutUrl)' in res_post_khqr.data
    assert not any(
        cookie.startswith('cart_list=') and 'Max-Age=0' in cookie
        for cookie in res_post_khqr.headers.getlist('Set-Cookie')
    )
    checkout_again = client.get('/checkout')
    assert checkout_again.status_code == 200
    assert b'MSI Katana 15' in checkout_again.data
    assert b"successMessage.classList.remove('hidden')" in res_post_khqr.data
    assert b"modal.classList.add('hidden')" in res_post_khqr.data

    # 3. POST /checkout with payment='split'
    client.set_cookie('cart_list', json.dumps(cart_data))
    with app.app_context():
        from models.user import User
        user = db.session.get(User, 2)
        user.wallet_balance_khr = 100
        db.session.commit()
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'
    res_post_split = client.post('/checkout', data={
        'first_name': 'Jane',
        'last_name': 'Doe',
        'email': 'jane@example.com',
        'phone': '098765432',
        'address': '456 Boulevard, Phnom Penh',
        'payment': 'split',
        'wallet_balance_khr': '1',
    })
    assert res_post_split.status_code == 200
    assert b"Order awaiting payment" in res_post_split.data
    assert b"Order placed successfully!</h2>" not in res_post_split.data
    assert b"khqr-payment-panel" in res_post_split.data
    assert b"data:image/png;base64," in res_post_split.data
    with app.app_context():
        from models.wallet_transaction import WalletTransaction
        debit = WalletTransaction.query.filter_by(transaction_type='debit').one()
        assert debit.amount_khr == -100
        assert debit.status == 'pending'
        assert db.session.get(User, 2).wallet_balance_khr == 0
