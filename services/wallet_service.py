"""Wallet business logic for store-credit and split-payment flows.

The project keeps global pricing in KHR as the canonical ledger currency,
while the storefront can still display USD approximations via helpers.currency.
"""


def compute_split_payment(order_total_khr, wallet_balance_khr):
    """Return the wallet and KHQR split for a checkout total.

    A wallet balance that exceeds the order total is fully consumed by credit.
    """
    total = int(order_total_khr or 0)
    balance = int(wallet_balance_khr or 0)

    wallet_used = min(balance, total)
    khqr_remaining = max(total - wallet_used, 0)

    if khqr_remaining == 0:
        payment_mode = 'wallet'
    elif wallet_used == 0:
        payment_mode = 'khqr'
    else:
        payment_mode = 'split'

    return {
        'wallet_used_khr': wallet_used,
        'khqr_remaining_khr': khqr_remaining,
        'payment_mode': payment_mode,
        'total_khr': total,
    }


def reserve_wallet_balance(wallet_balance_khr, amount_khr):
    """Reduce the wallet balance by amount_khr after validation."""
    wallet_balance = int(wallet_balance_khr or 0)
    amount = int(amount_khr or 0)

    if amount < 0:
        raise ValueError('Wallet amount cannot be negative.')
    if wallet_balance < amount:
        raise ValueError('Insufficient wallet balance for this order.')

    remaining = wallet_balance - amount
    return {
        'amount_khr': amount,
        'remaining_balance_khr': remaining,
    }
