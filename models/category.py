from extensions import db

class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False)

    products = db.relationship('Product', backref='category', lazy=True)

    def __repr__(self):
        return f"<Category {self.name}>"
