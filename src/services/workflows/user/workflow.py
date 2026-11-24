"""UserWorkflow：查询当前登录用户的账户资料。"""

import json
from collections.abc import Sequence
from uuid import UUID

from langchain_core.messages import BaseMessage
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from services.workflows.user.agents import profile_agent


async def run(
    messages: Sequence[BaseMessage],
    *,
    db: AsyncSession | None,
    user_id: UUID | None,
    user_role: str = "student",
    enable_thinking: bool = False,
) -> str:
    """Orchestrate the shared read-only profile agent."""
    return await profile_agent.run(
        messages,
        db=db,
        user_id=user_id,
        user_role=user_role,
        enable_thinking=enable_thinking,
    )


async def edit_card(*, db: AsyncSession | None, user_id: UUID | None) -> str:
    """Build an edit card for the authenticated user's own profile."""
    if db is None or user_id is None:
        return "暂时无法读取你的账号资料，请登录后再试。"
    user = await db.get(User, user_id)
    if user is None:
        return "没有找到当前账号的资料，请重新登录后再试。"
    data = {
        "id": str(user.id),
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "avatar": user.avatar,
    }
    return json.dumps({"type": "user_profile_edit", "data": data}, ensure_ascii=False)
