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
    """Read and return current Bakong KHQR configuration strictly from .env file / environment."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    account_id = os.environ.get('BAKONG_ACCOUNT_ID', '').strip()
    token = os.environ.get('BAKONG_TOKEN', '').strip()
    merchant_name = os.environ.get('BAKONG_MERCHANT_NAME', '').strip()
    merchant_city = os.environ.get('BAKONG_MERCHANT_CITY', '').strip()
    currency = os.environ.get('BAKONG_CURRENCY', '').strip()
    phone_number = os.environ.get('BAKONG_PHONE_NUMBER', '').strip()
    store_label = os.environ.get('BAKONG_STORE_LABEL', '').strip()
    terminal_label = os.environ.get('BAKONG_TERMINAL_LABEL', '').strip()

    if has_app_context():
        from flask import current_app
        if account_id:
            current_app.config['BAKONG_ACCOUNT_ID'] = account_id
        if token:
            current_app.config['BAKONG_TOKEN'] = token
        if currency:
            current_app.config['BAKONG_CURRENCY'] = currency

    return {
        'token': token or (current_app.config.get('BAKONG_TOKEN', '') if has_app_context() else ''),
        'account_id': account_id or (current_app.config.get('BAKONG_ACCOUNT_ID', '') if has_app_context() else ''),
        'merchant_name': merchant_name or (current_app.config.get('BAKONG_MERCHANT_NAME', 'TechStore') if has_app_context() else 'TechStore'),
        'merchant_city': merchant_city or (current_app.config.get('BAKONG_MERCHANT_CITY', 'Phnom Penh') if has_app_context() else 'Phnom Penh'),
        'currency': currency or (current_app.config.get('BAKONG_CURRENCY', 'KHR') if has_app_context() else 'KHR'),
        'phone_number': phone_number or (current_app.config.get('BAKONG_PHONE_NUMBER', '') if has_app_context() else ''),
        'store_label': store_label or (current_app.config.get('BAKONG_STORE_LABEL', 'Cashier-01') if has_app_context() else 'Cashier-01'),
        'terminal_label': terminal_label or (current_app.config.get('BAKONG_TERMINAL_LABEL', 'POS-01') if has_app_context() else 'POS-01'),
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
    """KHQR Tag 54 requires a whole number in KHR without artificial modification."""
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

    currency = config.get('currency', 'KHR')
    if currency == 'USD':
        from helpers.currency import usd_from_khr
        send_amount = float(usd_from_khr(amount))
    else:
        send_amount = float(amount)

    try:
        khqr_resp = client.create_qr(
            amount=send_amount,
            account_id=acc_id,
            merchant_name=name,
            merchant_city=city,
            currency=currency,
            store_label=store,
            phone_number=phone,
            bill_number=exact_reference[:25],
            terminal_label=term,
            static=False,
            expiration=30,
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
        'currency': currency,
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
        # Protect Bakong API daily quota (100 req/day): enforce a 4-second cooldown per reference
        last_checked = payment.get('_last_checked_at')
        now_ts = datetime.now(timezone.utc).timestamp()
        if last_checked and (now_ts - last_checked) < 4:
            return {'success': True, 'data': payment}

        if not get_khqr_config()['token']:
            raise RuntimeError('BAKONG_TOKEN is required to check payment status.')
        try:
            client = get_khqr_client()
            if client is None:
                raise RuntimeError('The bakong-khqr package is required to check payment status.')
            payment['_last_checked_at'] = now_ts

            raw_resp = None
            try:
                raw_resp = client._KHQR__post_request("/check_transaction_by_md5", {"md5": reference_md5})
            except Exception:
                raw_resp = None

            if isinstance(raw_resp, dict):
                resp_code = raw_resp.get("responseCode")
                err_code = raw_resp.get("errorCode")
                resp_msg = raw_resp.get("responseMessage", "")

                if err_code == 17 or "limit of 100 exceeded" in str(resp_msg).lower():
                    payment['bakong_status'] = 'QUOTA_EXCEEDED'
                    payment['gateway_error'] = 'Daily limit of 100 requests exceeded on NBC Bakong Developer token.'
                    return {
                        'success': False,
                        'status': 'quota_exceeded',
                        'message': 'Daily request limit of 100 exceeded on Bakong Developer API. If you have already paid in your app, your funds are safe! Please contact admin to confirm your order.',
                        'data': payment
                    }
                elif resp_code == 0:
                    payment['bakong_status'] = 'PAID'
                    payment['status'] = 'paid'
                    payment['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                else:
                    payment['bakong_status'] = 'UNPAID'
            else:
                bakong_status = client.check_payment(reference_md5)
                payment['bakong_status'] = str(bakong_status).upper()
                if payment['bakong_status'] == 'PAID':
                    payment['status'] = 'paid'
                    payment['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
                elif payment['bakong_status'] == 'EXPIRED':
                    payment['status'] = 'expired'
        except Exception as exc:
            raise RuntimeError('Bakong payment status check failed.') from exc

    return {'success': True, 'data': payment}


def mark_payment_paid(reference_md5):
    payment = _PAYMENT_CACHE.get(reference_md5)
    if not payment:
        return {'success': False, 'status': 'not_found'}
    payment['status'] = 'paid'
    payment['paid_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'success': True, 'data': payment}
