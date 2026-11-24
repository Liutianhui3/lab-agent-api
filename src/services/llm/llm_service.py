"""聊天入口适配器：普通与 SSE 请求共用实验室 Agent 工作流。"""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from services.llm.llm_client import create_llm

llm = create_llm()


async def chat(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
) -> str:
    if not messages:
        raise ValueError("messages 不能为空")
    from services.workflows.supervisor import workflow

    return await workflow.run(
        messages, enable_thinking=enable_thinking, db=db, user_role=user_role, user_id=user_id
    )


async def stream_chat(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
) -> AsyncIterator[str]:
    """本阶段等待回复生成完成后发送一个完整文本块。

    不将总调度的内部工具调用内容作为 delta 暴露给用户。
    后续接入生成式回答节点时，再增加该节点的 token 流。
    """
    yield await chat(messages, enable_thinking=enable_thinking, db=db, user_role=user_role, user_id=user_id)
