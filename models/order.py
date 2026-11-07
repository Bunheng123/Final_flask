from extensions import db
from helpers.time import utc_now

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(50), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    customer_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=False)
    address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(20), nullable=False, default='unpaid', server_default='unpaid')
    payment_reference = db.Column(db.String(128), nullable=True, unique=True)
    total_khr = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    wallet_used_khr = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    status = db.Column(db.String(30), default='pending', nullable=False)  # pending, confirmed, shipped, delivered, cancelled
    subtotal_cents = db.Column(db.Integer, nullable=False, default=0)
    discount_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False, default=0)
    coupon_code = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    shipped_at = db.Column(db.DateTime, nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)
    cancelled_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.Index('idx_order_status_created_at', 'status', 'created_at'),
    )

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    coupon_redemptions = db.relationship('CouponRedemption', backref='order', lazy=True)

    def __repr__(self):
        return f"<Order {self.order_number} ({self.status})>"
