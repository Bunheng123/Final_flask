from extensions import db
from helpers.time import utc_now

class CouponRedemption(db.Model):
    __tablename__ = 'coupon_redemptions'

    id = db.Column(db.Integer, primary_key=True)
    coupon_id = db.Column(db.Integer, db.ForeignKey('coupons.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    user = db.relationship('User', backref=db.backref('coupon_redemptions', lazy=True))

    def __repr__(self):
        return f"<CouponRedemption coupon={self.coupon_id} order={self.order_id} user={self.user_id}>"
