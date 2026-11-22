"""Store feedback on assistant messages."""

import sqlalchemy as sa
from alembic import op

revision = "c4e20be46b31"
down_revision = "ae1d3c82b491"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("feedback", sa.String(8), nullable=True))
    op.create_check_constraint(
        "ck_messages_feedback", "messages",
        "feedback IN ('positive', 'negative') AND role = 'assistant' OR feedback IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_feedback", "messages", type_="check")
    op.drop_column("messages", "feedback")
