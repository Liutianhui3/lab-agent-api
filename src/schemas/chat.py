"""聊天接口的请求与响应结构。"""

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from schemas.message import MessageResponse


class ChatRequest(BaseModel):
    """省略会话 ID 时自动创建会话，否则继续当前用户的指定会话。"""

    conversation_id: UUID | None = Field(default=None, description="已有会话 ID")
    content: str = Field(min_length=1, max_length=20000, description="用户输入的消息内容")

    enable_thinking: bool = Field(default=False, strict=True, description="是否启用模型思考")

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        """拒绝纯空白输入，保留代码等文本中的原始缩进。"""
        if not value.strip():
            raise ValueError("消息内容不能为空")
        return value


class ChatResponse(BaseModel):
    """返回会话标识及已保存的完整问答，便于客户端继续对话。"""

    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
