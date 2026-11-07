import hashlib
import os
from datetime import datetime, timedelta, timezone
from flask import has_app_context

# Ensure environment variables from .env file are loaded
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from helpers.currency import normalize_khr

try:
    from bakong_khqr import KHQR
except ImportError:
    KHQR = None


def get_khqr_config():
    """Read and return current Bakong KHQR configuration from environment / .env file."""
    return {
        'token': os.environ.get('BAKONG_TOKEN', '').strip(),
        'account_id': os.environ.get('BAKONG_ACCOUNT_ID', 'bunheng_lim@bkrt').strip(),
        'merchant_name': os.environ.get('BAKONG_MERCHANT_NAME', 'SETEC').strip(),
        'merchant_city': os.environ.get('BAKONG_MERCHANT_CITY', 'Phnom Penh').strip(),
        'phone_number': os.environ.get('BAKONG_PHONE_NUMBER', '099774967').strip(),
        'store_label': os.environ.get('BAKONG_STORE_LABEL', 'Cashier-01').strip(),
        'terminal_label': os.environ.get('BAKONG_TERMINAL_LABEL', 'POS-01').strip(),
    }


def get_khqr_client():
    """Instantiate a KHQR client using the token from the .env file."""
    if KHQR is None:
        return None
    config = get_khqr_config()
    return KHQR(config['token'] or None)


_PAYMENT_CACHE = {}


def _make_reference(order_number=None):
    raw = order_number or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def validate_khr_tag54(amount_khr):
    """KHQR Tag 54 requires a whole number in KHR."""
    amount = normalize_khr(amount_khr)
    if amount < 0:
        raise ValueError('Tag 54 amount cannot be negative.')
    return amount


def build_khqr_payload(reference, amount_khr, merchant_name=None, merchant_id=None):
    """Build a compact EMVCo-like payload with Tag 54 integer KHR amount."""
    config = get_khqr_config()
    tag54 = validate_khr_tag54(amount_khr)
    expires_in_minutes = 30
    payload = {
        'merchant_name': merchant_name or config['merchant_name'],
        'merchant_id': merchant_id or config['account_id'],
        'currency': 'KHR',
        'tag_54_khr_amount': tag54,
        'reference': reference,
        'expires_in_minutes': expires_in_minutes,
        'is_emvco_like': True,
    }
    return payload


def qr_image_base64_uri(qr_string):
    """Render a KHQR payload using the Bakong SDK's Base64 Data URI renderer."""
    if not qr_string:
        raise ValueError('A KHQR payload is required to render a payment code.')
    client = get_khqr_client()
    if client is None:
        raise RuntimeError('The bakong-khqr package is required to render payment codes.')
    return client.qr_image(qr_string, format='base64_uri')


def generate_khqr(
    reference=None,
    amount_khr=0,
    merchant_name=None,
    merchant_id=None,
    merchant_city=None,
    phone_number=None,
    store_label=None,
    terminal_label=None,
):
    """Create a 30-minute KHQR payment payload using credentials from the .env file."""
    config = get_khqr_config()
    exact_reference = reference or _make_reference()
    amount = validate_khr_tag54(amount_khr)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    raw_md5 = hashlib.md5(exact_reference.encode('utf-8')).hexdigest()
    reference_md5 = raw_md5

    name = merchant_name or config['merchant_name']
    acc_id = merchant_id or config['account_id']
    city = merchant_city or config['merchant_city']
    phone = phone_number or config['phone_number']
    store = store_label or config['store_label']
    term = terminal_label or config['terminal_label']

    qr_string = None

    client = get_khqr_client()
    if client is None:
        raise RuntimeError('The bakong-khqr package is required to generate payment codes.')

    try:
        khqr_resp = client.create_qr(
            amount=float(amount),
            account_id=acc_id,
            merchant_name=name,
            merchant_city=city,
            currency='KHR',
            store_label=store,
            phone_number=phone,
            bill_number=exact_reference,
            terminal_label=term,
            static=False,
            expiration=1,
            return_dict=True,
        )
    except Exception as exc:
        raise RuntimeError('Bakong KHQR payload generation failed.') from exc

    if isinstance(khqr_resp, dict):
        response_data = khqr_resp.get('data') or {}
        qr_string = response_data.get('qr')
        reference_md5 = response_data.get('md5') or reference_md5
    elif hasattr(khqr_resp, 'data'):
        response_data = khqr_resp.data
        qr_string = getattr(response_data, 'qr', None)
        reference_md5 = getattr(response_data, 'md5', None) or reference_md5

    if not qr_string:
        raise RuntimeError('Bakong KHQR did not return a payment payload.')

    try:
        qr_image_base64 = client.qr_image(qr_string, format='base64_uri')
    except Exception as exc:
        raise RuntimeError('Bakong KHQR image generation failed.') from exc

    payload = build_khqr_payload(
        reference=exact_reference,
        amount_khr=amount,
        merchant_name=name,
        merchant_id=acc_id,
    )
    if qr_string:
        payload['qr_string'] = qr_string

    result = {
        'reference': exact_reference,
        'reference_md5': reference_md5,
        'amount_khr': amount,
        'currency': 'KHR',
        'merchant_name': name,
        'merchant_id': acc_id,
        'expires_at': expires_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'expires_in_seconds': 1800,
        'tag_54_khr_amount': amount,
        'qr_string': qr_string,
        'qr_payload': payload,
        'qr_image_base64': qr_image_base64,
        'base64_uri': qr_image_base64,
        'status': 'pending',
    }
    _PAYMENT_CACHE[reference_md5] = result
    _PAYMENT_CACHE[raw_md5] = result
    return result


def get_payment_status(reference_md5):
    payment = _PAYMENT_CACHE.get(reference_md5)
    if not payment:
        if not has_app_context():
            return {'success': False, 'status': 'not_found'}

        from models.order import Order
        from models.wallet_transaction import WalletTransaction

        transaction = WalletTransaction.query.filter_by(reference=reference_md5).first()
        order = Order.query.filter_by(payment_reference=reference_md5).first()
        if transaction is None and order is None:
            return {'success': False, 'status': 'not_found'}

        if transaction and transaction.transaction_type == 'top_up':
            amount_khr = transaction.amount_khr
            known_status = (
                'paid' if transaction.status == 'completed'
                else 'expired' if transaction.status == 'expired'
                else 'pending'
            )
        elif order is not None:
            amount_khr = order.total_khr - order.wallet_used_khr
            known_status = (
                'paid' if order.payment_status in {'paid', 'refunded'}
                else 'expired' if order.payment_status == 'expired'
                else 'pending'
            )
        else:
            return {'success': False, 'status': 'not_found'}

        payment = {
            'reference': reference_md5,
            'reference_md5': reference_md5,
            'amount_khr': amount_khr,
            'status': known_status,
        }
        _PAYMENT_CACHE[reference_md5] = payment

    if payment['status'] == 'pending':
        if not get_khqr_config()['token']:
            raise RuntimeError('BAKONG_TOKEN is required to check payment status.')
        try:
            client = get_khqr_client()
            if client is None:
                raise RuntimeError('The bakong-khqr package is required to check payment status.')
            bakong_status = client.check_payment(reference_md5)
        except Exception as exc:
            raise RuntimeError('Bakong payment status check failed.') from exc

        payment['bakong_status'] = str(bakong_status).upper()
        if payment['bakong_status'] == 'PAID':
            payment['status'] = 'paid'
            payment['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        elif payment['bakong_status'] == 'EXPIRED':
            payment['status'] = 'expired'

    return {'success': True, 'data': payment}


def mark_payment_paid(reference_md5):
    payment = _PAYMENT_CACHE.get(reference_md5)
    if not payment:
        return {'success': False, 'status': 'not_found'}
    payment['status'] = 'paid'
    payment['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'success': True, 'data': payment}
