"""Agent 路由的结构化模型输出。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Intent = Literal[
    "knowledge_qa", "resource_query", "availability_query", "reservation_query",
    "create_reservation", "cancel_reservation", "out_of_scope", "unclear", "greeting",
]


OutOfScopeReason = Literal["unrelated", "unsupported_action", "permission_restricted"]


class RouteDecision(BaseModel):
    """只分类，不接受模型提供的回复、用户身份或执行参数。"""

    model_config = ConfigDict(extra="forbid")
    intent: Intent
    out_of_scope_reason: OutOfScopeReason | None = Field(
        default=None, description="范围外原因；其他意图为 null"
    )
    route_reason: str = Field(min_length=1, max_length=200)

