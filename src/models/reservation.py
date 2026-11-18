from datetime import date, time
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
    Time,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import TimestampMixin

if TYPE_CHECKING:
    from models.equipment import Equipment
    from models.lab import Lab
    from models.user import User


class Reservation(TimestampMixin, Base):
    """预约信息；未指定设备时表示预约实验室。"""

    __tablename__ = "reservations"
    __table_args__ = (
        CheckConstraint("status IN (0, 1, 2, 3)", name="ck_reservations_status"),
        {"comment": "预约信息表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="预约 ID",
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", name="fk_reservations_user_id"),
        index=True,
        comment="预约人 ID",
    )
    lab_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("labs.id", name="fk_reservations_lab_id"),
        index=True,
        comment="实验室 ID",
    )
    equipment_id: Mapped[int | None] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        ForeignKey("equipments.id", name="fk_reservations_equipment_id"),
        index=True,
        comment="设备 ID；为空表示预约实验室",
    )
    date: Mapped[date] = mapped_column(Date, comment="预约日期")
    start_time: Mapped[time] = mapped_column(Time, comment="开始时间")
    end_time: Mapped[time] = mapped_column(Time, comment="结束时间")
    remark: Mapped[str | None] = mapped_column(Text, comment="备注")
    status: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        server_default="0",
        comment="预约状态：0-待审核，1-已通过，2-已拒绝，3-已取消",
    )

    user: Mapped["User"] = relationship(back_populates="reservations")
    lab: Mapped["Lab"] = relationship(back_populates="reservations")
    equipment: Mapped["Equipment | None"] = relationship(back_populates="reservations")
