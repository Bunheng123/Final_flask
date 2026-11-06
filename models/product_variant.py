from extensions import db

class ProductVariant(db.Model):
    __tablename__ = 'product_variants'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    sku = db.Column(db.String(80), unique=True, nullable=False)
    spec_name = db.Column(db.String(150), nullable=False, default="Default")
    price_cents = db.Column(db.Integer, nullable=False)
    cost_price_cents = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<ProductVariant {self.sku}: {self.spec_name}>"
