"""dry-race flag; lap-less pit stops

Revision ID: ce7a71148a82
Revises: 535b721decd6
Create Date: 2026-07-15 03:32:26.950759
"""
import sqlalchemy as sa
from alembic import op

revision = 'ce7a71148a82'
down_revision = '535b721decd6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('openf1_pit_stops', 'lap_number',
               existing_type=sa.INTEGER(),
               nullable=True)
    op.add_column('sessions', sa.Column('is_dry', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('sessions', 'is_dry')
    op.alter_column('openf1_pit_stops', 'lap_number',
               existing_type=sa.INTEGER(),
               nullable=False)
