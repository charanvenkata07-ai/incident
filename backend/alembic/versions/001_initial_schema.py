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
    bind = op.get_bind()
    Base.metadata.create_all(bind)

def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind)
