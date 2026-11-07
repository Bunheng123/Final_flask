from extensions import db
from helpers.time import utc_now

class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    variants = db.relationship('ProductVariant', backref='product', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('ProductReview', backref='product', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Product {self.id}: {self.name}>"
