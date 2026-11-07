from extensions import db
from helpers.time import utc_now
from sqlalchemy.sql import func

class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    profile = db.Column(db.String(80), nullable=True)
    username = db.Column(db.String(80), nullable=False)
    first_name = db.Column(db.String(80), nullable=True)
    last_name = db.Column(db.String(80), nullable=True)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.Text, nullable=True)
    role = db.Column(db.String(120), nullable=False, default="user")
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now, server_default=func.now())

    orders = db.relationship('Order', backref='user', lazy='dynamic', order_by='desc(Order.created_at)')

    def __repr__(self):
        return f"<User {self.id}: {self.username}>"
