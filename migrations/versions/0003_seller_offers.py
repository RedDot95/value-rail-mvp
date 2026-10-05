"""seller offer tracking for new-seller detection on marketplace pages

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('seller_offers',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source_key', sa.String(length=100), nullable=False),
    sa.Column('page_url', sa.String(length=500), nullable=False),
    sa.Column('offer_key', sa.String(length=300), nullable=False),
    sa.Column('seller', sa.String(length=200), nullable=False),
    sa.Column('sku', sa.String(length=200), nullable=False),
    sa.Column('region', sa.String(length=40), nullable=False),
    sa.Column('first_seen_at', sa.String(length=40), nullable=False),
    sa.Column('last_seen_at', sa.String(length=40), nullable=False),
    sa.Column('last_price', sa.String(length=40), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.Column('last_quantity', sa.String(length=40), nullable=False),
    sa.Column('seen_count', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_key', 'page_url', 'offer_key', name='uq_seller_offer')
    )
    op.create_table('seller_offer_events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('at', sa.String(length=40), nullable=False),
    sa.Column('scan_run_id', sa.Integer(), nullable=True),
    sa.Column('source_key', sa.String(length=100), nullable=False),
    sa.Column('page_url', sa.String(length=500), nullable=False),
    sa.Column('offer_key', sa.String(length=300), nullable=False),
    sa.Column('seller', sa.String(length=200), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('old_price', sa.String(length=40), nullable=False),
    sa.Column('new_price', sa.String(length=40), nullable=False),
    sa.Column('currency', sa.String(length=10), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_seller_offer_events_at', 'seller_offer_events', ['at'])


def downgrade() -> None:
    op.drop_index('ix_seller_offer_events_at', 'seller_offer_events')
    op.drop_table('seller_offer_events')
    op.drop_table('seller_offers')
