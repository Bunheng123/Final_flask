from extensions import db

class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)  # uppercase
    discount_type = db.Column(db.String(20), nullable=False)  # 'percent' | 'fixed'
    value = db.Column(db.Float, nullable=False)  # percent (e.g. 10.0 for 10%) or fixed cents/dollars
    min_spend_cents = db.Column(db.Integer, nullable=False, default=0)
    max_discount_cents = db.Column(db.Integer, nullable=True)
    starts_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    usage_limit = db.Column(db.Integer, nullable=True)
    per_customer_limit = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    redemptions = db.relationship('CouponRedemption', backref='coupon', lazy=True)

    def __repr__(self):
        return f"<Coupon {self.code} ({self.discount_type}:{self.value})>"
