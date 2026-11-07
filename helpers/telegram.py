import os
import time
import threading
from datetime import datetime, timezone, timedelta
import requests
from config import (
    TELEGRAM_ALERT_BOT_TOKEN,
    TELEGRAM_ALERT_CHAT_ID,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)

# In-memory alert cache to prevent Telegram spam if an attacker hits hundreds of times
_recent_alerts = {}
_lock = threading.Lock()
ALERT_COOLDOWN_SECONDS = 60

def _escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _get_active_credentials(token=None, chat_id=None):
    """
    Dynamically retrieve Telegram credentials, reloading .env if needed.
    Ensures newly added tokens in .env are picked up without requiring server restart.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        pass

    active_token = token or os.environ.get("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
    active_chat = chat_id or os.environ.get("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
    return active_token, active_chat


def _send_telegram_worker(text, chat_id, token, parse_mode):
    bot_token, target_chat = _get_active_credentials(token, chat_id)
    if not bot_token or not target_chat or not text:
        print(f"[Telegram Notice] Message not sent - Missing config: Token={'SET' if bot_token else 'EMPTY'}, ChatID={target_chat}")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': target_chat,
        'text': text,
        'parse_mode': parse_mode,
        'disable_web_page_preview': True
    }
    headers = {'Content-Type': 'application/json'}
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if not res.ok:
            print(f"[Telegram Bot Error] HTTP {res.status_code}: {res.text}")
        else:
            print(f"[Telegram Bot Success] Message delivered to {target_chat}")
    except Exception as e:
        print(f"[Telegram Error] Network failure: {e}")


def send_telegram(text: str, chat_id: str = None, token: str = None, parse_mode: str = "HTML"):
    """
    Generic non-blocking function to send a Telegram message in a background thread.
    Never raises an exception into the calling request.
    """
    t = threading.Thread(
        target=_send_telegram_worker,
        args=(text, chat_id, token, parse_mode),
        daemon=True
    )
    t.start()


def send_order_receipt(order):
    """
    Builds and dispatches a comprehensive, luxury HTML order receipt to Telegram.
    Includes customer snapshot, payment method, itemized line items table, and totals.
    Dispatched ONLY if order is confirmed and paid.
    """
    if not order:
        return

    # Never alert Telegram for unpaid or pending orders
    payment_status = getattr(order, 'payment_status', None)
    if payment_status != 'paid':
        return

    from helpers.money import format_money
    from helpers.currency import khr_format

    items_text = ""
    for item in order.items:
        price_fmt = format_money(item.unit_price_cents)
        line_fmt = format_money(item.line_total_cents)
        items_text += (
            f"• <b>{_escape_html(item.product_name)}</b> ({_escape_html(item.spec_name)})\n"
            f"   └ <code>{item.qty} × {price_fmt}</code> = <b>{line_fmt}</b>\n"
        )

    discount_line = ""
    if order.discount_cents and order.discount_cents > 0:
        discount_line = f"🎟️ <b>Discount:</b> -{format_money(order.discount_cents)}\n"

    total_khr_val = getattr(order, 'total_khr', None) or int(order.total_cents / 100 * 4100)
    khr_amount = khr_format(total_khr_val)

    wallet_line = ""
    wallet_used = getattr(order, 'wallet_used_khr', 0) or 0
    if wallet_used > 0:
        wallet_line = f"👛 <b>Wallet Used:</b> {khr_format(wallet_used)}\n"

    payment_method = getattr(order, 'payment_method', 'KHQR') or 'KHQR'

    receipt = (
        f"✅ <b>[PAID ORDER RECEIPT #{_escape_html(order.order_number)}]</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Customer:</b> {_escape_html(order.customer_name)}\n"
        f"📞 <b>Phone:</b> {_escape_html(order.phone)}\n"
        f"✉️ <b>Email:</b> {_escape_html(order.email)}\n"
        f"📍 <b>Address:</b> {_escape_html(order.address)}\n"
        f"💳 <b>Payment:</b> <code>{_escape_html(payment_method.upper())}</code> (PAID)\n"
        f"{wallet_line}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛒 <b>Ordered Items:</b>\n{items_text}"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Subtotal:</b> {format_money(order.subtotal_cents)}\n"
        f"{discount_line}"
        f"🚚 <b>Shipping:</b> Free\n"
        f"💰 <b>Total Paid:</b> <b>{format_money(order.total_cents)}</b> ({khr_amount})\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>Status:</b> <b>PAID & CONFIRMED</b>"
    )

    send_telegram(receipt)


def send_low_stock_alert(variant_name: str, current_stock: int, threshold: int = None):
    """
    Wrapper stub for low stock threshold alerts.
    """
    thresh_info = f" (Threshold: {threshold})" if threshold is not None else ""
    msg = (
        f"⚠️ <b>[LOW STOCK ALERT]</b>\n"
        f"Product/Variant: <b>{_escape_html(variant_name)}</b>\n"
        f"Current Stock: <b>{current_stock}</b>{thresh_info}\n"
        f"Please reorder inventory soon."
    )
    send_telegram(msg)


def send_order_alert(order_number: str, total_str: str, customer_name: str, status: str = "pending"):
    """
    Wrapper stub for order status / lifecycle transition alerts.
    """
    msg = (
        f"📦 <b>[ORDER UPDATE #{_escape_html(order_number)}]</b>\n"
        f"Customer: <b>{_escape_html(customer_name)}</b>\n"
        f"Total: <b>{_escape_html(total_str)}</b>\n"
        f"Status: <b>{_escape_html(status.upper())}</b>"
    )
    send_telegram(msg)


def _send_alert_worker(ip, method, path, limit_desc, retry_after, user_agent):
    now = time.time()
    
    with _lock:
        last_info = _recent_alerts.get(ip)
        if last_info and (now - last_info['timestamp']) < ALERT_COOLDOWN_SECONDS:
            # Increase blocked attempt count during cooldown, don't spam Telegram
            last_info['count'] += 1
            return
        # First alert or cooldown expired
        _recent_alerts[ip] = {'timestamp': now, 'count': 1}

    bot_token = os.environ.get("TELEGRAM_ALERT_BOT_TOKEN") or TELEGRAM_ALERT_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    chat_id = os.environ.get("TELEGRAM_ALERT_CHAT_ID") or TELEGRAM_ALERT_CHAT_ID or TELEGRAM_CHAT_ID

    if not bot_token or not chat_id:
        return

    cambodia_tz = timezone(timedelta(hours=7))
    cambodia_time = datetime.now(cambodia_tz).strftime('%Y-%m-%d %I:%M:%S %p (GMT+7)')
    ua_display = _escape_html(user_agent or "Unknown")
    if len(ua_display) > 80:
        ua_display = ua_display[:77] + "..."

    message = (
        "🚨 <b>[429] RATE LIMIT TRIGGERED</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<pre><code>"
        f"Target Endpoint  : {_escape_html(method)} {_escape_html(path)}\n"
        f"Attacker IP      : {_escape_html(ip)}\n"
        f"Attempts         : {_escape_html(limit_desc)}\n"
        f"Cooldown Period  : {retry_after}s remaining\n"
        "</code></pre>"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Device Info:</b> <code>{ua_display}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ <code>{cambodia_time}</code>"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=8)
        if not res.ok:
            print(f"[Telegram Alert Error] HTTP {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[Telegram Alert Error] Failed to send alert: {e}")


def send_rate_limit_alert(ip, method, path, limit_desc="Rate limit exceeded", retry_after=60, user_agent=None):
    """
    Non-blocking function to send security rate-limit alerts to Telegram.
    Runs asynchronously in a background thread so client requests are never delayed.
    """
    t = threading.Thread(
        target=_send_alert_worker,
        args=(ip, method, path, limit_desc, retry_after, user_agent),
        daemon=True
    )
    t.start()
