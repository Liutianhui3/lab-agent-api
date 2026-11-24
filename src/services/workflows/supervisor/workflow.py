"""Authenticated entry point for autonomous business orchestration."""
import asyncio
from collections.abc import Sequence
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from services.workflows.supervisor.agents import supervisor_agent


async def stream(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
):
    if not messages or not isinstance(messages[-1], HumanMessage):
        raise ValueError("最后一条消息必须是用户输入")
    if user_role not in {"student", "admin"}:
        raise ValueError("未知用户角色")
    context = {
        "messages": list(messages), "db": db, "user_id": user_id,
        "user_role": user_role, "enable_thinking": enable_thinking,
        # One session is shared by nested workflows; model-selected parallel tool
        # calls must not use AsyncSession concurrently.
        "db_lock": asyncio.Lock(), "cards": [],
        "progress": [],
    }
    yield "thinking", {"stage": "identify_user_role", "label": "确认当前用户身份", "status": "complete"}
    yield "thinking", {"stage": "supervisor", "label": "理解请求并调度业务流程", "status": "complete"}
    async for event in supervisor_agent.stream(context):
        yield event


async def run(
    messages: Sequence[BaseMessage], *, enable_thinking: bool = False,
    db: AsyncSession | None = None, user_role: str = "student",
    user_id: UUID | None = None,
) -> str:
    parts = []
    async for event, payload in stream(
        messages, enable_thinking=enable_thinking, db=db,
        user_role=user_role, user_id=user_id,
    ):
        if event == "delta":
            parts.append(payload["content"])
    return "".join(parts)
