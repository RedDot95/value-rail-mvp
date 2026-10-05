"""scheduler lease lock + persistent job state (Delivery 3 basics)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('scheduler_locks',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('owner', sa.String(length=200), nullable=False),
    sa.Column('acquired_at', sa.String(length=40), nullable=False),
    sa.Column('expires_at', sa.String(length=40), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )
    op.create_table('job_states',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('connector', sa.String(length=100), nullable=False),
    sa.Column('interval_seconds', sa.Integer(), nullable=False),
    sa.Column('next_due_at', sa.String(length=40), nullable=True),
    sa.Column('last_started_at', sa.String(length=40), nullable=True),
    sa.Column('last_finished_at', sa.String(length=40), nullable=True),
    sa.Column('last_success_at', sa.String(length=40), nullable=True),
    sa.Column('last_error_at', sa.String(length=40), nullable=True),
    sa.Column('last_status', sa.String(length=30), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('last_scan_run_id', sa.Integer(), nullable=True),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('runs_total', sa.Integer(), nullable=False),
    sa.Column('skipped_catchup_total', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('name')
    )


def downgrade() -> None:
    op.drop_table('job_states')
    op.drop_table('scheduler_locks')
