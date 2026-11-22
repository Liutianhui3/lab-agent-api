"""聊天入口适配器：普通与 SSE 请求共用实验室 Agent 工作流。"""

from collections.abc import AsyncIterator, Sequence
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_core.messages import BaseMessage

from schemas.agent import LaboratoryQuery, RouteDecision
from services.llm.llm_client import create_llm

llm = create_llm()


async def classify_request(messages: Sequence[BaseMessage], *, enable_thinking: bool = False) -> RouteDecision:
    router = llm.with_structured_output(RouteDecision, method="function_calling")
    decision = await router.ainvoke(list(messages), extra_body={"enable_thinking": enable_thinking})
    return RouteDecision.model_validate(decision)


async def plan_laboratory_query(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
) -> LaboratoryQuery:
    planner = llm.with_structured_output(LaboratoryQuery, method="function_calling")
    result = await planner.ainvoke(
        list(messages), extra_body={"enable_thinking": enable_thinking}
    )
    return LaboratoryQuery.model_validate(result)


async def generate_scope_response(messages: Sequence[BaseMessage], *, enable_thinking: bool = False) -> str:
    response = await llm.ainvoke(list(messages), extra_body={"enable_thinking": enable_thinking})
    return response.content


async def chat(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
) -> str:
    if not messages:
        raise ValueError("messages 不能为空")
    from services.agent import workflow

    return await workflow.run(
        messages, enable_thinking=enable_thinking, db=db, user_role=user_role, user_id=user_id
    )


async def stream_chat(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
) -> AsyncIterator[str]:
    """本阶段等待回复生成完成后发送一个完整文本块。

    不将分类模型的内部结构化输出作为 delta 暴露给用户。
    后续接入生成式回答节点时，再增加该节点的 token 流。
    """
    yield await chat(messages, enable_thinking=enable_thinking, db=db, user_role=user_role, user_id=user_id)
