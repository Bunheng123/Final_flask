"""
Brand Model.
Owner: Developer 2 / Member 2 (Catalog, Inventory & Brand Specialist)
"""
from extensions import db
from helpers.time import utc_now


class Brand(db.Model):
    __tablename__ = 'brands'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    logo = db.Column(db.String(500), nullable=True)
    website = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    products = db.relationship('Product', backref='brand', lazy=True)

    def __repr__(self):
        return f"<Brand {self.id}: {self.name}>"

