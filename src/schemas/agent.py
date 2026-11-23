"""Agent 路由的结构化模型输出。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "knowledge_qa", "resource_query", "user_profile_query", "user_profile_edit", "admin_user_create", "admin_user_edit", "admin_user_delete", "availability_query", "reservation_query",
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
    # 管理员用户管理卡片的目标信息；仅管理员意图使用。
    user_identifier: str | None = Field(default=None, max_length=254)
    user_fields: dict[str, str | int | None] = Field(default_factory=dict)

