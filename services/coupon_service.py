"""
Coupon Service - Promotional discount calculations, validation, and redemptions.
Owner: Workstream D (Coupons, Invoicing & Reports)
"""

def validate_coupon(code: str, subtotal_cents: int, customer_id: int = None) -> tuple[bool, str, int]:
    """
    Validates a coupon code against current cart subtotal and usage limits.

    Returns:
      tuple: (is_valid: bool, error_message: str, discount_cents: int)

    TODO: Workstream D - Implement validate_coupon.
    """
    raise NotImplementedError("TODO: Workstream D - Implement validate_coupon")

def apply_coupon(code: str, subtotal_cents: int) -> int:
    """
    Calculates discount amount in cents without committing redemption.

    TODO: Workstream D - Implement apply_coupon.
    """
    raise NotImplementedError("TODO: Workstream D - Implement apply_coupon")

def redeem(code: str, order_id: int, customer_id: int = None):
    """
    Records a coupon redemption in coupon_redemptions and increments coupon used_count.

    TODO: Workstream D - Implement redeem.
    """
    raise NotImplementedError("TODO: Workstream D - Implement redeem")

def release(redemption_id: int):
    """
    Releases a redeemed coupon when an order is cancelled or rolled back.

    TODO: Workstream D - Implement release.
    """
    raise NotImplementedError("TODO: Workstream D - Implement release")
