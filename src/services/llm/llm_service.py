"""聊天入口适配器：普通与 SSE 请求共用实验室 Agent 工作流。"""

from collections.abc import AsyncIterator, Sequence

from langchain_core.messages import BaseMessage

from schemas.agent import RouteDecision
from services.llm.llm_client import create_llm

llm = create_llm()


async def classify_request(messages: Sequence[BaseMessage]) -> RouteDecision:
    router = llm.with_structured_output(RouteDecision, method="function_calling")
    decision = await router.ainvoke(list(messages))
    return RouteDecision.model_validate(decision)


async def generate_scope_response(messages: Sequence[BaseMessage]) -> str:
    response = await llm.ainvoke(list(messages))
    return response.content


async def chat(messages: Sequence[BaseMessage]) -> str:
    if not messages:
        raise ValueError("messages 不能为空")
    from services.agent import workflow

    return await workflow.run(messages)


async def stream_chat(messages: Sequence[BaseMessage]) -> AsyncIterator[str]:
    """本阶段等待回复生成完成后发送一个完整文本块。

    不将分类模型的内部结构化输出作为 delta 暴露给用户。
    后续接入生成式回答节点时，再增加该节点的 token 流。
    """
    yield await chat(messages)
