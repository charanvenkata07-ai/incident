"""Add missing model columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22 00:58:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    def has_col(table_name: str, col_name: str) -> bool:
        cols = [c['name'] for c in insp.get_columns(table_name)]
        return col_name in cols

    # 1. users table
    if not has_col('users', 'avatar_url'):
        op.add_column('users', sa.Column('avatar_url', sa.String(500), nullable=True))
    if not has_col('users', 'phone'):
        op.add_column('users', sa.Column('phone', sa.String(50), nullable=True))
    if not has_col('users', 'bio'):
        op.add_column('users', sa.Column('bio', sa.Text(), nullable=True))
    if not has_col('users', 'timezone'):
        op.add_column('users', sa.Column('timezone', sa.String(50), nullable=True, server_default='Asia/Kolkata'))
    if not has_col('users', 'notification_preferences'):
        op.add_column('users', sa.Column('notification_preferences', sa.Text(), nullable=True))
    if not has_col('users', 'chat_preferences'):
        op.add_column('users', sa.Column('chat_preferences', sa.Text(), nullable=True))

    # 2. teams table
    if not has_col('teams', 'work_domain'):
        op.add_column('teams', sa.Column('work_domain', sa.String(200), nullable=True))

    # 3. employees table
    if not has_col('employees', 'is_group_leader'):
        op.add_column('employees', sa.Column('is_group_leader', sa.Boolean(), nullable=False, server_default=sa.text('false')))

    # 4. incidents table
    if not has_col('incidents', 'current_cycle'):
        op.add_column('incidents', sa.Column('current_cycle', sa.Integer(), nullable=False, server_default=sa.text('1')))

    # 5. incident_assignments table
    if not has_col('incident_assignments', 'cycle_number'):
        op.add_column('incident_assignments', sa.Column('cycle_number', sa.Integer(), nullable=False, server_default=sa.text('1')))
    if not has_col('incident_assignments', 'scheduled_shift_name'):
        op.add_column('incident_assignments', sa.Column('scheduled_shift_name', sa.String(100), nullable=True))
    if not has_col('incident_assignments', 'scheduled_start'):
        op.add_column('incident_assignments', sa.Column('scheduled_start', sa.DateTime(timezone=True), nullable=True))
    if not has_col('incident_assignments', 'team_id'):
        op.add_column('incident_assignments', sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('teams.id', ondelete='SET NULL'), nullable=True))
    if not has_col('incident_assignments', 'assignment_cycle_id'):
        op.add_column('incident_assignments', sa.Column('assignment_cycle_id', sa.String(100), sa.ForeignKey('assignment_cycles.id', ondelete='CASCADE'), nullable=True))
    if not has_col('incident_assignments', 'previous_employee_id'):
        op.add_column('incident_assignments', sa.Column('previous_employee_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('employees.id'), nullable=True))
    if not has_col('incident_assignments', 'reassigned_reason'):
        op.add_column('incident_assignments', sa.Column('reassigned_reason', sa.Text(), nullable=True))
    if not has_col('incident_assignments', 'rotation_cycle'):
        op.add_column('incident_assignments', sa.Column('rotation_cycle', sa.Integer(), nullable=True))
    if not has_col('incident_assignments', 'rotation_position'):
        op.add_column('incident_assignments', sa.Column('rotation_position', sa.Integer(), nullable=True))
    if not has_col('incident_assignments', 'source_event_id'):
        op.add_column('incident_assignments', sa.Column('source_event_id', sa.String(255), nullable=True))

    # 6. notifications table
    if not has_col('notifications', 'read_at'):
        op.add_column('notifications', sa.Column('read_at', sa.DateTime(timezone=True), nullable=True))
    if not has_col('notifications', 'conversation_id'):
        op.add_column('notifications', sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not has_col('notifications', 'message_id'):
        op.add_column('notifications', sa.Column('message_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not has_col('notifications', 'assignment_id'):
        op.add_column('notifications', sa.Column('assignment_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not has_col('notifications', 'team_id'):
        op.add_column('notifications', sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not has_col('notifications', 'sender_id'):
        op.add_column('notifications', sa.Column('sender_id', postgresql.UUID(as_uuid=True), nullable=True))
    if not has_col('notifications', 'sender_name'):
        op.add_column('notifications', sa.Column('sender_name', sa.String(255), nullable=True))
    if not has_col('notifications', 'action_url'):
        op.add_column('notifications', sa.Column('action_url', sa.String(500), nullable=True))
    if not has_col('notifications', 'action_type'):
        op.add_column('notifications', sa.Column('action_type', sa.String(100), nullable=True))
    if not has_col('notifications', 'extra_data'):
        op.add_column('notifications', sa.Column('extra_data', sa.JSON(), nullable=True))

    # 7. integration_events table
    if not has_col('integration_events', 'idempotency_key'):
        op.add_column('integration_events', sa.Column('idempotency_key', sa.String(255), nullable=True))


def downgrade() -> None:
    pass
