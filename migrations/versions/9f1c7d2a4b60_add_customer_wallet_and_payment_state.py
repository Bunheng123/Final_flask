"""Add customer wallet ledger and payment state.

Revision ID: 9f1c7d2a4b60
Revises: 9c4a2d8e1f70
Create Date: 2026-11-07 11:48:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '9f1c7d2a4b60'
down_revision = '9c4a2d8e1f70'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'wallet_balance_khr',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ))

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'payment_status',
            sa.String(length=20),
            server_default='unpaid',
            nullable=False,
        ))
        batch_op.add_column(sa.Column('payment_reference', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column(
            'total_khr',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ))
        batch_op.add_column(sa.Column(
            'wallet_used_khr',
            sa.Integer(),
            server_default='0',
            nullable=False,
        ))
        batch_op.add_column(sa.Column('paid_at', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_orders_payment_reference', ['payment_reference'])

    op.create_table(
        'wallet_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=True),
        sa.Column('transaction_type', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='completed', nullable=False),
        sa.Column('amount_khr', sa.Integer(), nullable=False),
        sa.Column('balance_after_khr', sa.Integer(), nullable=False),
        sa.Column('reference', sa.String(length=128), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('amount_khr != 0', name='ck_wallet_transaction_nonzero_amount'),
        sa.CheckConstraint(
            "transaction_type IN ('top_up', 'debit', 'refund')",
            name='ck_wallet_transaction_type',
        ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference', name='uq_wallet_transactions_reference'),
    )
    op.create_index(
        'idx_wallet_transactions_user_created',
        'wallet_transactions',
        ['user_id', 'created_at'],
        unique=False,
    )


def downgrade():
    op.drop_index('idx_wallet_transactions_user_created', table_name='wallet_transactions')
    op.drop_table('wallet_transactions')
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_constraint('uq_orders_payment_reference', type_='unique')
        batch_op.drop_column('paid_at')
        batch_op.drop_column('wallet_used_khr')
        batch_op.drop_column('total_khr')
        batch_op.drop_column('payment_reference')
        batch_op.drop_column('payment_status')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('wallet_balance_khr')
