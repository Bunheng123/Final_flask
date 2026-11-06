from extensions import db
from helpers.time import utc_now

class Customer(db.Model):
    __tablename__ = 'customers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    orders = db.relationship('Order', backref='customer', lazy=True)
    wishlist_items = db.relationship('WishlistItem', backref='customer', lazy=True, cascade='all, delete-orphan')
    reviews = db.relationship('ProductReview', backref='customer', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Customer {self.id}: {self.email}>"
