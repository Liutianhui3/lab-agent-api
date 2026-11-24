"""Agent 路由的结构化模型输出。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "knowledge_qa", "resource_query", "user_profile_query", "user_profile_edit", "admin_user_create", "admin_user_edit", "admin_user_delete", "availability_query", "reservation_query",
    "create_reservation", "cancel_reservation", "out_of_scope", "unclear", "greeting",
]


OutOfScopeReason = Literal["unrelated", "unsupported_action", "permission_restricted"]


class RouteDecision(BaseModel):
    """分类并提取管理员操作目标和字段，不接受模型提供的回复或账户身份。"""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    out_of_scope_reason: OutOfScopeReason | None = Field(
        default=None, description="范围外原因；其他意图为 null"
    )
    route_reason: str = Field(min_length=1, max_length=200)
    # 管理员用户管理卡片的目标信息；仅管理员意图使用。
    user_identifier: str | None = Field(default=None, max_length=254)
    user_fields: dict[str, str | int | None] = Field(default_factory=dict)
