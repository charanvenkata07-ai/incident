"""Initial schema

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-09-16 22:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.models import Base

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # We use a shortcut to create all tables from metadata to avoid writing a massive migration file
    # This works nicely with run_sync
    op.run_sync(lambda conn: Base.metadata.create_all(conn))

def downgrade() -> None:
    op.run_sync(lambda conn: Base.metadata.drop_all(conn))
