"""offer judgments: INFERRED model signals (enrichment/safety layer, append-only)

Separate from all observed/deterministic tables; see docs/decisions.md D-42.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "offer_judgments"


def upgrade() -> None:
    op.create_table(TABLE,
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('offer_snapshot_id', sa.Integer(), nullable=True),
    sa.Column('route_evaluation_id', sa.Integer(), nullable=True),
    sa.Column('scan_run_id', sa.Integer(), nullable=True),
    sa.Column('route_key', sa.String(length=200), nullable=False),
    sa.Column('source_key', sa.String(length=100), nullable=False),
    sa.Column('question_id', sa.String(length=60), nullable=False),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('answer', sa.String(length=200), nullable=True),
    sa.Column('probability', sa.Float(), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=True),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('distribution', sa.Text(), nullable=True),
    sa.Column('selected_value', sa.String(length=64), nullable=True),
    sa.Column('selected_candidate', sa.Text(), nullable=True),
    sa.Column('signal', sa.String(length=40), nullable=False),
    sa.Column('abstained', sa.Boolean(), nullable=False),
    sa.Column('abstain_reason', sa.Text(), nullable=False),
    sa.Column('provider', sa.String(length=40), nullable=False),
    sa.Column('model', sa.String(length=60), nullable=False),
    sa.Column('created_at', sa.String(length=40), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['offer_snapshot_id'], ['offer_snapshots.id'], ),
    sa.ForeignKeyConstraint(['route_evaluation_id'], ['route_evaluations.id'], ),
    sa.ForeignKeyConstraint(['scan_run_id'], ['scan_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_offer_judgments_offer_snapshot_id'), ['offer_snapshot_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_offer_judgments_route_key'), ['route_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_offer_judgments_created_at'), ['created_at'], unique=False)
    # append-only, like the other evidence-grade tables (0001): corrections are new rows
    op.execute(f"CREATE TRIGGER {TABLE}_no_update BEFORE UPDATE ON {TABLE} "
               f"BEGIN SELECT RAISE(ABORT, 'immutable table {TABLE}: create a new version'); END;")
    op.execute(f"CREATE TRIGGER {TABLE}_no_delete BEFORE DELETE ON {TABLE} "
               f"BEGIN SELECT RAISE(ABORT, 'immutable table {TABLE}: delete not allowed'); END;")


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_update")
    op.execute(f"DROP TRIGGER IF EXISTS {TABLE}_no_delete")
    with op.batch_alter_table(TABLE, schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_offer_judgments_created_at'))
        batch_op.drop_index(batch_op.f('ix_offer_judgments_route_key'))
        batch_op.drop_index(batch_op.f('ix_offer_judgments_offer_snapshot_id'))
    op.drop_table(TABLE)
