"""Agent 路由的结构化模型输出。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "knowledge_qa", "resource_query", "user_profile_query", "availability_query", "reservation_query",
    "create_reservation", "cancel_reservation", "out_of_scope", "unclear", "greeting",
]


OutOfScopeReason = Literal["unrelated", "unsupported_action", "permission_restricted"]


ProfileField = Literal["role", "email", "phone", "username", "name", "status"]


class RouteDecision(BaseModel):
    """分类并提取允许的资料字段，不接受模型提供的回复或账户身份。"""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    out_of_scope_reason: OutOfScopeReason | None = Field(
        default=None, description="范围外原因；其他意图为 null"
    )
    route_reason: str = Field(min_length=1, max_length=200)
    profile_format: Literal["text", "list", "table"] | None = Field(
        default=None, description="本人资料回复的格式，按用户表达和上下文判断"
    )
    profile_fields: list[ProfileField] = Field(
        default_factory=list,
        description="仅本人资料查询时填写请求的字段；概览填写全部支持的字段",
    )



LabField = Literal["name", "code", "capacity", "opening_hours", "location", "status", "description"]


class LaboratoryQuery(BaseModel):
    """实验室工作流允许的只读查询参数。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target: Literal["laboratory", "equipment", "clarify"]
    lab_keyword: str | None = Field(default=None, min_length=1, max_length=255)
    equipment_keyword: str | None = Field(default=None, min_length=1, max_length=255)
    lab_status: Literal["open", "closed", "all"] | None = None
    equipment_status: Literal["normal", "maintenance", "all"] | None = None
    page: int = Field(default=1, ge=1, le=10_000)
    full_lab_list: bool = Field(default=False, description="列出所有符合条件的实验室，取消分页")
    output_format: Literal["list", "table"] | None = Field(default=None, description="多字段清单或表格用 table，项目符号列表用 list")
    lab_fields: list[LabField] = Field(default_factory=list, description="用户要求展示的实验室字段，按原顺序")
