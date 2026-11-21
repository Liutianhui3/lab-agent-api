from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from schemas.response import BaseResponse, PageData


# 用户发送消息的请求
class MessageCreate(BaseModel):
    content: str = Field(
        min_length=1,
        max_length=20000,
    )


# 消息响应
class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessagePageData[T](PageData[T]):
    """消息分页数据。"""


class MessagePageResponse[T](BaseResponse[MessagePageData[T]]):
    """消息分页响应。"""
