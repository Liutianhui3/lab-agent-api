from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from schemas.response import BaseResponse, PageData


# 创建会话时的请求结构
class ConversationCreate(BaseModel):
    title: str = Field(
        default="新对话",
        max_length=200,
    )


# 会话响应结构
class ConversationResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConversationPageData[T](PageData[T]):
    """会话分页数据。"""


class ConversationPageResponse[T](BaseResponse[ConversationPageData[T]]):
    """会话分页响应。"""
