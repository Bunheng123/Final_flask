from extensions import db
from helpers.time import utc_now

class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False, default='order')  # 'order', 'credit', 'system'
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)

    __table_args__ = (
        db.Index('idx_notification_user_unread', 'user_id', 'is_read'),
        db.Index('idx_notification_user_created', 'user_id', 'created_at'),
    )

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic', cascade='all, delete-orphan'))

    def __repr__(self):
        return f"<Notification {self.id}: {self.title} (User {self.user_id}, Read: {self.is_read})>"

