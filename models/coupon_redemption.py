from extensions import db
from helpers.time import utc_now

class CouponRedemption(db.Model):
    __tablename__ = 'coupon_redemptions'

    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    def __repr__(self):
        return f"<CouponRedemption coupon={self.coupon_id} order={self.order_id}>"
