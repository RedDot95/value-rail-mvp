"""Persist successful alert channels across retries/restarts.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("delivered_sinks", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("alerts", "delivered_sinks")
