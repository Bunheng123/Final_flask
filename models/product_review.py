from extensions import db
from helpers.time import utc_now

class ProductReview(db.Model):
    __tablename__ = 'product_reviews'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    comment = db.Column(db.Text, nullable=True)
    is_visible = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_review_rating_range'),
        db.UniqueConstraint('customer_id', 'product_id', name='uq_review_customer_product'),
    )

    def __repr__(self):
        return f"<ProductReview product={self.product_id} rating={self.rating}>"
