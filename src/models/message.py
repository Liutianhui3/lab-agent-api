from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.mysql import DATETIME, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.conversation import Conversation


class Message(TimestampMixin, Base):
    """会话消息。"""

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "feedback IN ('positive', 'negative') AND role = 'assistant' OR feedback IS NULL",
            name="ck_messages_feedback",
        ),
    )

    feedback: Mapped[str | None] = mapped_column(String(8))
    thinking_steps: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    thinking_duration: Mapped[int | None] = mapped_column(Integer, nullable=True)

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid4
    )

    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "conversations.id",
            ondelete="CASCADE",
        ),
    )

    role: Mapped[str] = mapped_column(String(20), comment="消息角色")

    content: Mapped[str] = mapped_column(
        Text().with_variant(LONGTEXT(), "mysql"), comment="消息内容"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime().with_variant(DATETIME(fsp=6), "mysql"),
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        comment="创建时间",
    )

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
