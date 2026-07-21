"""initial

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from kalibr_amo_bot.db import Base
    from kalibr_amo_bot import models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    from kalibr_amo_bot.db import Base
    from kalibr_amo_bot import models  # noqa: F401
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
