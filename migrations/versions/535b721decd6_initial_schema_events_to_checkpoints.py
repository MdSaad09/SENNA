"""initial schema: events to checkpoints

Revision ID: 535b721decd6
Revises: 
Create Date: 2026-07-14 22:35:17.853098
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '535b721decd6'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('events',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('round', sa.Integer(), nullable=False),
    sa.Column('event_name', sa.String(), nullable=False),
    sa.Column('event_format', sa.String(), nullable=True),
    sa.Column('event_date', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('season', 'round')
    )
    op.create_table('ingest_checkpoints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('season', sa.Integer(), nullable=False),
    sa.Column('round', sa.Integer(), nullable=False),
    sa.Column('event_name', sa.String(), nullable=True),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('session_name', sa.String(), nullable=False),
    sa.Column('state', sa.String(), nullable=False),
    sa.Column('rows_loaded', sa.Integer(), nullable=True),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('excluded_reason', sa.String(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('season', 'round', 'source', 'session_name')
    )
    op.create_table('simulation_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('env_config_hash', sa.String(), nullable=True),
    sa.Column('model_version', sa.String(), nullable=True),
    sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('agent_decisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('lap_number', sa.Integer(), nullable=False),
    sa.Column('decision', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.ForeignKeyConstraint(['run_id'], ['simulation_runs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('event_id', sa.Integer(), nullable=False),
    sa.Column('session_name', sa.String(), nullable=False),
    sa.Column('session_date_utc', sa.DateTime(), nullable=True),
    sa.Column('openf1_session_key', sa.Integer(), nullable=True),
    sa.Column('openf1_meeting_key', sa.Integer(), nullable=True),
    sa.Column('missing_channels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('event_id', 'session_name')
    )
    op.create_table('laps',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('driver', sa.String(), nullable=True),
    sa.Column('driver_number', sa.String(), nullable=False),
    sa.Column('team', sa.String(), nullable=True),
    sa.Column('lap_number', sa.Integer(), nullable=False),
    sa.Column('stint', sa.Integer(), nullable=True),
    sa.Column('compound', sa.String(), nullable=True),
    sa.Column('tyre_life', sa.Float(), nullable=True),
    sa.Column('fresh_tyre', sa.Boolean(), nullable=True),
    sa.Column('lap_time_s', sa.Float(), nullable=True),
    sa.Column('lap_time_imputed', sa.Boolean(), nullable=False),
    sa.Column('sector1_s', sa.Float(), nullable=True),
    sa.Column('sector2_s', sa.Float(), nullable=True),
    sa.Column('sector3_s', sa.Float(), nullable=True),
    sa.Column('speed_st_kmh', sa.Float(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=True),
    sa.Column('track_status', sa.String(), nullable=True),
    sa.Column('is_accurate', sa.Boolean(), nullable=True),
    sa.Column('is_green', sa.Boolean(), nullable=True),
    sa.Column('pit_in_time_s', sa.Float(), nullable=True),
    sa.Column('pit_out_time_s', sa.Float(), nullable=True),
    sa.Column('lap_start_time_s', sa.Float(), nullable=True),
    sa.Column('era', sa.String(), nullable=False),
    sa.Column('source', sa.String(), nullable=False),
    sa.Column('energy_deployed_mj', sa.Float(), nullable=True),
    sa.Column('energy_harvested_mj', sa.Float(), nullable=True),
    sa.Column('soc_end_mj', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'driver_number', 'lap_number', 'source')
    )
    op.create_table('openf1_pit_stops',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('driver_number', sa.Integer(), nullable=False),
    sa.Column('lap_number', sa.Integer(), nullable=False),
    sa.Column('pit_duration_s', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'driver_number', 'lap_number')
    )
    op.create_table('openf1_stints',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('driver_number', sa.Integer(), nullable=False),
    sa.Column('stint_number', sa.Integer(), nullable=False),
    sa.Column('compound', sa.String(), nullable=True),
    sa.Column('lap_start', sa.Integer(), nullable=True),
    sa.Column('lap_end', sa.Integer(), nullable=True),
    sa.Column('tyre_age_at_start', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'driver_number', 'stint_number')
    )
    op.create_table('race_control',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('time_utc', sa.DateTime(), nullable=True),
    sa.Column('category', sa.String(), nullable=True),
    sa.Column('flag', sa.String(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('message', sa.String(), nullable=True),
    sa.Column('lap', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('driver_abbrev', sa.String(), nullable=False),
    sa.Column('team_name', sa.String(), nullable=True),
    sa.Column('grid_position', sa.Integer(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('points', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'driver_abbrev')
    )
    op.create_table('weather',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('time_s', sa.Float(), nullable=False),
    sa.Column('air_temp_c', sa.Float(), nullable=True),
    sa.Column('track_temp_c', sa.Float(), nullable=True),
    sa.Column('humidity_pct', sa.Float(), nullable=True),
    sa.Column('rainfall', sa.Boolean(), nullable=True),
    sa.Column('wind_speed_ms', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('session_id', 'time_s')
    )


def downgrade() -> None:
    op.drop_table('weather')
    op.drop_table('results')
    op.drop_table('race_control')
    op.drop_table('openf1_stints')
    op.drop_table('openf1_pit_stops')
    op.drop_table('laps')
    op.drop_table('sessions')
    op.drop_table('agent_decisions')
    op.drop_table('simulation_runs')
    op.drop_table('ingest_checkpoints')
    op.drop_table('events')
