"""Persist safe workflow thinking summaries on assistant messages."""
import sqlalchemy as sa
from alembic import op
revision = "e8f4c2b1a901"
down_revision = "c4e20be46b31"
branch_labels = None
depends_on = None
def upgrade() -> None:
    op.add_column("messages", sa.Column("thinking_steps", sa.JSON(), nullable=True))
    op.add_column("messages", sa.Column("thinking_duration", sa.Integer(), nullable=True))
def downgrade() -> None:
    op.drop_column("messages", "thinking_duration")
    op.drop_column("messages", "thinking_steps")
