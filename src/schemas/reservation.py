from datetime import date as Date
from datetime import datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from pydantic.alias_generators import to_camel

from schemas.response import BaseResponse, PageData


class ReservationResponse(BaseModel):
    """预约响应，支持读取 ORM 字段。"""

    model_config = ConfigDict(
        from_attributes=True, alias_generator=to_camel, populate_by_name=True
    )

    id: int
    user_id: UUID
    lab_id: int
    equipment_id: int | None
    date: Date
    start_time: time
    end_time: time
    remark: str | None
    status: Literal[0, 1, 2, 3]
    created_at: datetime
    updated_at: datetime
    user: "UserName"
    lab: "LabName"
    equipment: "EquipmentName | None" = None

    @computed_field
    @property
    def user_name(self) -> str:
        return self.user.name

    @computed_field
    @property
    def lab_name(self) -> str:
        return self.lab.name

    @computed_field
    @property
    def equipment_name(self) -> str | None:
        return self.equipment.name if self.equipment else None

    @computed_field
    @property
    def type(self) -> Literal["lab", "equipment"]:
        return "equipment" if self.equipment_id is not None else "lab"


class ReservationPageData[T](PageData[T]):
    """预约分页数据及各状态数量。"""

    pending_count: int = 0
    approved_count: int = 0
    rejected_count: int = 0
    cancelled_count: int = 0


class ReservationPageResponse[T](BaseResponse[ReservationPageData[T]]):
    """预约分页响应。"""


class UserName(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str


class LabName(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str


class EquipmentName(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str


class ReservationCreateRequest(BaseModel):
    """创建预约参数；设备为空时表示预约实验室。"""

    model_config = ConfigDict(extra="forbid")

    lab_id: int = Field(gt=0, description="实验室 ID")
    date: Date = Field(description="预约日期")
    equipment_id: int | None = Field(
        default=None, gt=0, description="设备 ID；为空表示预约实验室"
    )
    start_time: time = Field(description="开始时间")
    end_time: time = Field(description="结束时间")
    remark: str | None = Field(default=None, description="备注")

    @field_validator("date")
    @classmethod
    def validate_date_not_in_past(cls, value: Date) -> Date:
        china_today = datetime.now(timezone(timedelta(hours=8))).date()
        if value < china_today:
            raise ValueError("预约日期不能早于当前日期")
        return value


class ReservationStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[1, 2, 3] = Field(description="1-同意，2-拒绝，3-取消")
