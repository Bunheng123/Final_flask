"""
Coupon Service - Promotional discount calculations, validation, and redemptions.
Owner: Workstream D / Developer 4 (Coupons, Invoicing & Reports)
"""
from typing import Optional, Tuple
from sqlalchemy import func
from extensions import db
from models.coupon import Coupon
from models.coupon_redemption import CouponRedemption
from helpers.time import utc_now


def validate_coupon(code: str, subtotal_cents: int, user_id: Optional[int] = None) -> Tuple[bool, str, int]:
    """
    Validates a coupon code against the current cart subtotal and user redemption limits.

    Args:
        code: The coupon code string (case-insensitive).
        subtotal_cents: The cart subtotal in integer cents.
        user_id: Optional user ID for per-customer usage check.

    Returns:
        tuple: (is_valid: bool, message: str, discount_cents: int)
    """
    if not code or not code.strip():
        return False, "Please enter a coupon code.", 0

    clean_code = code.strip().upper()
    coupon = Coupon.query.filter(func.upper(Coupon.code) == clean_code).first()

    if not coupon:
        return False, f"Coupon '{clean_code}' does not exist.", 0

    if not coupon.is_active:
        return False, f"Coupon '{clean_code}' is currently inactive.", 0

    now = utc_now()

    # Check start and expiration dates
    if coupon.starts_at and now < coupon.starts_at:
        return False, f"Coupon '{clean_code}' is not active yet.", 0

    if coupon.expires_at and now > coupon.expires_at:
        return False, f"Coupon '{clean_code}' has expired.", 0

    # Check minimum spend requirement
    if subtotal_cents < coupon.min_spend_cents:
        min_dollars = coupon.min_spend_cents / 100.0
        return False, f"Minimum spend of ${min_dollars:.2f} required for coupon '{clean_code}'.", 0

    # Check global usage limit
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        return False, f"Coupon '{clean_code}' has reached its maximum redemption limit.", 0

    # Check per-customer usage limit
    if user_id and coupon.per_customer_limit is not None:
        user_redemptions = CouponRedemption.query.filter_by(coupon_id=coupon.id, user_id=user_id).count()
        if user_redemptions >= coupon.per_customer_limit:
            return False, f"You have already redeemed coupon '{clean_code}' the maximum allowed number of times.", 0

    # Calculate discount in cents
    if coupon.discount_type == 'percent':
        calculated_discount = int(round(subtotal_cents * (coupon.value / 100.0)))
    elif coupon.discount_type == 'fixed':
        # value in cents (e.g. 2000.0 = $20.00)
        calculated_discount = int(round(coupon.value))
    else:
        return False, f"Unsupported discount type '{coupon.discount_type}'.", 0

    # Apply max discount cap if configured
    if coupon.max_discount_cents and calculated_discount > coupon.max_discount_cents:
        calculated_discount = coupon.max_discount_cents

    # Ensure discount does not exceed subtotal
    calculated_discount = max(0, min(calculated_discount, subtotal_cents))

    return True, f"Coupon '{clean_code}' applied successfully!", calculated_discount


def apply_coupon(code: str, subtotal_cents: int) -> int:
    """
    Calculates the discount amount in cents without committing a redemption.
    Returns 0 if the coupon is invalid.
    """
    is_valid, _, discount_cents = validate_coupon(code, subtotal_cents)
    return discount_cents if is_valid else 0


def redeem(code: str, order_id: int, user_id: Optional[int] = None) -> Optional[CouponRedemption]:
    """
    Records a coupon redemption in coupon_redemptions, increments the coupon's used_count,
    and commits the transaction.

    Args:
        code: Coupon code string.
        order_id: The ID of the order using this coupon.
        user_id: Optional ID of the user placing the order.

    Returns:
        The created CouponRedemption object or None if invalid.
    """
    if not code:
        return None

    clean_code = code.strip().upper()
    coupon = Coupon.query.filter(func.upper(Coupon.code) == clean_code).first()

    if not coupon:
        return None

    coupon.used_count = (coupon.used_count or 0) + 1

    redemption = CouponRedemption(
        coupon_id=coupon.id,
        order_id=order_id,
        user_id=user_id,
        created_at=utc_now()
    )
    db.session.add(redemption)
    db.session.commit()
    return redemption


def release(redemption_id: int) -> bool:
    """
    Releases a redeemed coupon when an order is cancelled or rolled back.
    Decrements coupon used_count and deletes the redemption record.
    """
    redemption = db.session.get(CouponRedemption, redemption_id)
    if not redemption:
        return False

    coupon = db.session.get(Coupon, redemption.coupon_id)
    if coupon and coupon.used_count > 0:
        coupon.used_count -= 1

    db.session.delete(redemption)
    db.session.commit()
    return True
