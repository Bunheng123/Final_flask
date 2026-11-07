from extensions import db
from helpers.time import utc_now


class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transactions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='SET NULL'), nullable=True)
    transaction_type = db.Column(db.String(24), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='completed', server_default='completed')
    amount_khr = db.Column(db.Integer, nullable=False)
    balance_after_khr = db.Column(db.Integer, nullable=False)
    reference = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)

    __table_args__ = (
        db.CheckConstraint('amount_khr != 0', name='ck_wallet_transaction_nonzero_amount'),
        db.CheckConstraint(
            "transaction_type IN ('top_up', 'debit', 'refund')",
            name='ck_wallet_transaction_type',
        ),
        db.Index('idx_wallet_transactions_user_created', 'user_id', 'created_at'),
    )

    order = db.relationship('Order', backref=db.backref('wallet_transactions', lazy=True))

    def __repr__(self):
        return f"<WalletTransaction {self.transaction_type} {self.amount_khr} KHR>"
