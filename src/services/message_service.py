from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import NotFoundException
from models.message import Message
from schemas.message import MessageCreate, MessagePageData, MessageResponse
from services.conversation_service import get_conversation_detail


async def _require_conversation(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> None:
    if await get_conversation_detail(db, conversation_id, user_id) is None:
        raise NotFoundException(message="会话不存在")


async def add_message(
    db: AsyncSession,
    conversation_id: UUID,
    data: MessageCreate,
    user_id: UUID,
    *,
    role: Literal["user", "assistant"] = "user",
    commit: bool = True,
) -> Message:
    """添加消息；角色只能由服务端调用方指定，不接受客户端角色字段。

    默认独立提交；聊天使用 commit=False，将本轮问答纳入同一事务。
    此时提交和异常回滚均由调用方负责。
    """
    try:
        await _require_conversation(db, conversation_id, user_id)
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=data.content,
        )
        db.add(message)
        await db.flush()
        await db.refresh(message)
        if commit:
            await db.commit()
    except Exception:
        if commit:
            await db.rollback()
        raise

    return message


async def get_message_history(
    db: AsyncSession, conversation_id: UUID, user_id: UUID
) -> list[Message]:
    """校验会话归属并按时间返回完整历史，供聊天组装模型上下文。"""
    await _require_conversation(db, conversation_id, user_id)
    messages = await db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(messages)


async def get_messages(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: UUID,
    page: int = 1,
    size: int = 10,
) -> MessagePageData[MessageResponse]:
    """按时间正序分页获取当前用户的会话消息。"""
    await _require_conversation(db, conversation_id, user_id)
    conversation_filter = Message.conversation_id == conversation_id

    # 查询总数
    count_query = select(func.count()).select_from(Message).where(conversation_filter)
    total = await db.scalar(count_query)

    # 分页查询
    messages = await db.scalars(
        select(Message)
        .where(conversation_filter)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    )

    return MessagePageData[MessageResponse](
        total=total or 0,
        items=[MessageResponse.model_validate(message) for message in messages],
        page=page,
        size=size,
    )


async def delete_message(
    db: AsyncSession,
    message_id: UUID,
    conversation_id: UUID,
    user_id: UUID,
) -> bool:
    """删除指定消息"""

    try:
        await _require_conversation(db, conversation_id, user_id)
        message = await db.scalar(
            select(Message).where(
                Message.id == message_id,
                Message.conversation_id == conversation_id,
            )
        )
        if message is None:
            return False
        await db.delete(message)
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return True
