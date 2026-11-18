from typing import TYPE_CHECKING
from datetime import time

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from models.mixins import TimestampMixin


if TYPE_CHECKING:
    from models.reservation import Reservation


class Lab(TimestampMixin, Base):
    """实验室信息。"""

    __tablename__ = "labs"
    __table_args__ = (
        CheckConstraint("status IN (0, 1)", name="ck_labs_status"),
        {"comment": "实验室信息表"},
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        comment="内部主键",
    )
    lab_code: Mapped[str] = mapped_column(
        String(50), unique=True, comment="实验室业务编号"
    )
    name: Mapped[str] = mapped_column(String(100), comment="名称")
    location: Mapped[str | None] = mapped_column(String(255), comment="位置")
    capacity: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", comment="容量"
    )
    description: Mapped[str | None] = mapped_column(Text, comment="描述")
    img: Mapped[str | None] = mapped_column(String(2048), comment="封面图片")
    open_time: Mapped[time | None] = mapped_column(Time, comment="开放开始时间")
    close_time: Mapped[time | None] = mapped_column(Time, comment="开放结束时间")
    status: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1", comment="状态：0-关闭，1-开放"
    )

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="lab")
