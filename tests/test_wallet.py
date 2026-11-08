import json

from flask import g

from extensions import db
from models.order import Order
from models.user import User
from models.wallet_transaction import WalletTransaction


def _login_customer(client):
    with client.session_transaction() as sess:
        sess['is_login'] = True
        sess['user_id'] = 2
        sess['username'] = 'test_user'
        sess['email'] = 'user@techstore.test'
        sess['role'] = 'user'


def test_khqr_topup_and_paid_split_order_refund_to_wallet(client, app, monkeypatch):
    _login_customer(client)

    topup_payment = {
        'reference_md5': 'topup-payment-hash',
        'amount_khr': 5000,
        'base64_uri': 'data:image/png;base64,topup',
    }
    monkeypatch.setattr('front.account.generate_khqr', lambda **kwargs: topup_payment)
    topup_response = client.post('/account/wallet', data={'amount_khr': '5000'})
    assert topup_response.status_code == 200
    assert b'Customer Wallet' in topup_response.data
    with app.app_context():
        assert db.session.get(User, 2).wallet_balance_khr == 0

    payment_status = {'status': 'pending', 'bakong_status': 'SCANNED'}
    monkeypatch.setattr(
        'api.payment.get_payment_status',
        lambda payment_hash: {
            'success': True,
            'data': {**payment_status, 'reference': payment_hash},
        },
    )
    pending_response = client.get('/api/payment/check/topup-payment-hash')
    assert pending_response.status_code == 200
    assert pending_response.get_json()['data']['status'] == 'pending'
    with app.app_context():
        assert db.session.get(User, 2).wallet_balance_khr == 0
        topup = WalletTransaction.query.filter_by(reference='topup-payment-hash').one()
        assert topup.status == 'pending'
    pending_wallet_page = client.get('/account/wallet')
    assert b'KHQR wallet top-up</td>' not in pending_wallet_page.data

    payment_status.update(status='paid', bakong_status='PAID')
    assert client.get('/api/payment/check/topup-payment-hash').status_code == 200
    assert client.get('/api/payment/check/topup-payment-hash').status_code == 200
    with app.app_context():
        user = db.session.get(User, 2)
        assert user.wallet_balance_khr == 5000
        topup = WalletTransaction.query.filter_by(reference='topup-payment-hash').one()
        assert topup.status == 'completed'
    successful_wallet_page = client.get('/account/wallet')
    assert b'Payment success' in successful_wallet_page.data
    assert b'KHQR wallet top-up</td>' in successful_wallet_page.data

    with app.app_context():
        user = db.session.get(User, 2)
        user.wallet_balance_khr = 100
        db.session.commit()
        db.session.expire_all()
        assert db.session.get(User, 2).wallet_balance_khr == 100
    db.session.expire_all()
    g.pop('_current_user', None)

    monkeypatch.setattr(
        'front.checkout.generate_khqr',
        lambda **kwargs: {
            'reference_md5': 'split-payment-hash',
            'amount_khr': kwargs['amount_khr'],
            'base64_uri': 'data:image/png;base64,split',
        },
    )
    client.set_cookie('cart_list', json.dumps([{'id': 1, 'price': 9999, 'qty': 1}]))
    checkout_response = client.post('/checkout', data={
        'first_name': 'Test',
        'last_name': 'Customer',
        'email': 'user@techstore.test',
        'phone': '012345678',
        'address': 'Phnom Penh',
        'payment': 'split',
        'wallet_balance_khr': '999999999',
    })
    assert checkout_response.status_code == 200, checkout_response.data.decode()
    assert b'Order awaiting payment' in checkout_response.data

    with app.app_context():
        order = Order.query.filter_by(payment_reference='split-payment-hash').one()
        order_number = order.order_number
        assert order.payment_method == 'split'
        assert order.payment_status == 'pending'
        assert order.total_khr == 410
        assert order.wallet_used_khr == 100
        assert db.session.get(User, 2).wallet_balance_khr == 0
        debit = WalletTransaction.query.filter_by(reference='split-payment-hash').one()
        assert debit.amount_khr == -100
        assert debit.status == 'pending'

    assert client.get('/api/payment/check/split-payment-hash').status_code == 200
    assert client.get('/api/payment/check/split-payment-hash').status_code == 200
    with app.app_context():
        order = Order.query.filter_by(order_number=order_number).one()
        assert order.status == 'confirmed'
        assert order.payment_status == 'paid'
        debit = WalletTransaction.query.filter_by(reference='split-payment-hash').one()
        assert debit.status == 'completed'

    cancel_response = client.post(f'/account/orders/{order_number}/cancel')
    assert cancel_response.status_code == 302
    with app.app_context():
        order = Order.query.filter_by(order_number=order_number).one()
        assert order.status == 'cancelled'
        assert order.payment_status == 'refunded'
        assert db.session.get(User, 2).wallet_balance_khr == 410
        refund = WalletTransaction.query.filter_by(reference=f'refund:order:{order_number}').one()
        assert refund.amount_khr == 410


def test_expired_split_payment_releases_wallet_reservation(client, app, monkeypatch):
    _login_customer(client)
    with app.app_context():
        db.session.get(User, 2).wallet_balance_khr = 100
        db.session.commit()

    monkeypatch.setattr(
        'front.checkout.generate_khqr',
        lambda **kwargs: {
            'reference_md5': 'expired-split-hash',
            'amount_khr': kwargs['amount_khr'],
            'base64_uri': 'data:image/png;base64,split',
        },
    )
    client.set_cookie('cart_list', json.dumps([{'id': 1, 'price': 9999, 'qty': 1}]))
    response = client.post('/checkout', data={
        'first_name': 'Test',
        'last_name': 'Customer',
        'email': 'user@techstore.test',
        'phone': '012345678',
        'address': 'Phnom Penh',
        'payment': 'split',
    })
    assert response.status_code == 200

    monkeypatch.setattr(
        'api.payment.get_payment_status',
        lambda payment_hash: {
            'success': True,
            'data': {'status': 'expired', 'reference': payment_hash},
        },
    )
    assert client.get('/api/payment/check/expired-split-hash').status_code == 200
    with app.app_context():
        order = Order.query.filter_by(payment_reference='expired-split-hash').one()
        assert order.status == 'cancelled'
        assert order.payment_status == 'expired'
        assert db.session.get(User, 2).wallet_balance_khr == 100
        debit = WalletTransaction.query.filter_by(reference='expired-split-hash').one()
        assert debit.status == 'reversed'
        refund = WalletTransaction.query.filter_by(
            reference='refund:expired:expired-split-hash'
        ).one()
        assert refund.amount_khr == 100
