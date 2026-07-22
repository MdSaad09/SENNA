"""serving runs and lap frames (F10)

Revision ID: b7f10c54e21d
Revises: ce7a71148a82
Create Date: 2026-07-22 03:55:00.000000
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = 'b7f10c54e21d'
down_revision = 'ce7a71148a82'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable on purpose: F09's eval-card rows predate serving and stay valid
    op.add_column('simulation_runs', sa.Column('status', sa.String(), nullable=True))
    op.add_column('simulation_runs', sa.Column('seed', sa.Integer(), nullable=True))
    op.add_column('simulation_runs', sa.Column('circuit', sa.String(), nullable=True))
    op.add_column('simulation_runs', sa.Column('purpose', sa.String(), nullable=True))
    op.add_column('simulation_runs',
                  sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('simulation_runs', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('simulation_runs', sa.Column('finished_at', sa.DateTime(), nullable=True))
    op.create_table('lap_frames',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('lap', sa.Integer(), nullable=False),
    sa.Column('frame', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('run_id', 'lap')
    )


def downgrade() -> None:
    op.drop_table('lap_frames')
    op.drop_column('simulation_runs', 'finished_at')
    op.drop_column('simulation_runs', 'started_at')
    op.drop_column('simulation_runs', 'summary')
    op.drop_column('simulation_runs', 'purpose')
    op.drop_column('simulation_runs', 'circuit')
    op.drop_column('simulation_runs', 'seed')
    op.drop_column('simulation_runs', 'status')
