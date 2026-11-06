from extensions import db

class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True)
    product_name = db.Column(db.String(255), nullable=False)
    sku = db.Column(db.String(80), nullable=False)
    spec_name = db.Column(db.String(150), nullable=False)
    qty = db.Column(db.Integer, nullable=False, default=1)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    line_total_cents = db.Column(db.Integer, nullable=False)

    variant = db.relationship('ProductVariant', backref='order_items', lazy=True)

    def __repr__(self):
        return f"<OrderItem {self.id}: {self.sku} x{self.qty}>"
