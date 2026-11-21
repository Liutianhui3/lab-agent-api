from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.conversation import Conversation
from schemas.conversation import ConversationPageData, ConversationResponse


# 创建会话
async def create_conversation(
    db: AsyncSession, user_id: UUID, title: str = "新对话", *, commit: bool = True
) -> Conversation:
    """创建会话；commit=False 时由调用方统一提交或回滚事务。"""
    conversation = Conversation(user_id=user_id, title=title)

    try:
        db.add(conversation)
        await db.flush()
        await db.refresh(conversation)
        if commit:
            await db.commit()
    except Exception:
        if commit:
            await db.rollback()
        raise

    return conversation


# 获取会话列表
async def get_conversation_list(
    db: AsyncSession, user_id: UUID, page: int, size: int
) -> ConversationPageData[ConversationResponse]:
    owner_filter = Conversation.user_id == user_id
    total = await db.scalar(
        select(func.count()).select_from(Conversation).where(owner_filter)
    )
    conversations = await db.scalars(
        select(Conversation)
        .where(owner_filter)
        .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )

    return ConversationPageData[ConversationResponse](
        total=total or 0,
        items=[ConversationResponse.model_validate(item) for item in conversations],
        page=page,
        size=size,
    )


# 获取会话详情
async def get_conversation_detail(
    db: AsyncSession, conversation_id: UUID, user_id: UUID, *, for_update: bool = False
) -> Conversation | None:
    """按归属查询会话；聊天编排可加行锁，串行处理同一会话。"""
    query = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if for_update:
        query = query.with_for_update()
    result = await db.execute(query)

    return result.scalar_one_or_none()


# 删除会话
async def delete_conversation(db: AsyncSession, conversation_id: UUID, user_id: UUID):
    conversation = await get_conversation_detail(db, conversation_id, user_id)

    if not conversation:
        return False

    await db.delete(conversation)
    await db.commit()

    return True
