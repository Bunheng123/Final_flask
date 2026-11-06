from extensions import db
from helpers.time import utc_now

class WishlistItem(db.Model):
    __tablename__ = 'wishlist_items'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    product = db.relationship('Product', backref='wishlist_items', lazy=True)

    __table_args__ = (
        db.UniqueConstraint('customer_id', 'product_id', name='uq_wishlist_customer_product'),
    )

    def __repr__(self):
        return f"<WishlistItem customer={self.customer_id} product={self.product_id}>"
