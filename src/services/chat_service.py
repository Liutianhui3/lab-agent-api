"""聊天编排：负责会话鉴权、上下文组装、模型调用和本轮问答持久化。"""

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from datetime import UTC, datetime
from uuid import UUID

import anyio
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import AppException, NotFoundException
from models.conversation import Conversation
from schemas.chat import ChatRequest, ChatResponse
from schemas.message import MessageCreate, MessageResponse
from services import conversation_service, message_service
from services.llm import llm_service

logger = logging.getLogger(__name__)


async def chat(
    db: AsyncSession, data: ChatRequest, user_id: UUID, role: str | None = None
) -> ChatResponse:
    """完成一轮非流式聊天；仅在模型成功回复后提交会话及本轮两条消息。

    已有会话加行锁，避免同一会话的并发请求读取相同的旧上下文。
    复用会话和消息服务，关闭其自动提交，由本方法统一管理事务。
    """
    try:
        conversation, messages = await _prepare_chat(db, data, user_id)

        try:
            model_kwargs = {"enable_thinking": data.enable_thinking}
            if role is not None:
                model_kwargs.update(db=db, user_role=role, user_id=user_id)
            reply = await llm_service.chat(messages, **model_kwargs)
            if not isinstance(reply, str) or not reply.strip():
                raise ValueError("模型返回了空内容或非文本内容")
        except Exception as exc:
            logger.warning("聊天模型调用失败：%s", type(exc).__name__)
            raise AppException(
                code=5020, message="模型服务暂时不可用，请稍后重试", status_code=502
            ) from exc

        result = await _save_turn(db, conversation, data, user_id, reply)
        await db.commit()
        return result
    except BaseException:
        # 请求取消也要释放锁和未提交数据；异常继续交给上层处理。
        await db.rollback()
        raise


# 获取会话和历史消息
async def _prepare_chat(
    db: AsyncSession, data: ChatRequest, user_id: UUID
) -> tuple[Conversation, list[BaseMessage]]:
    """复用普通和流式聊天的会话归属检查、行锁与上下文构建。"""
    if data.conversation_id is None:
        conversation = await conversation_service.create_conversation(
            db, user_id, title=data.content[:200], commit=False
        )
    else:
        conversation = await conversation_service.get_conversation_detail(
            db, data.conversation_id, user_id, for_update=True
        )
        # 不区分不存在和非本人会话，避免泄露其他用户的会话信息。
        if conversation is None:
            raise NotFoundException(message="会话不存在")

    # 获取历史消息
    history = await message_service.get_message_history(db, conversation.id, user_id)
    role_types = {"user": HumanMessage, "assistant": AIMessage, "system": SystemMessage}
    messages = []
    for item in history:
        message_type = role_types.get(item.role)
        if message_type is None:
            # 当前为纯文本聊天，不能丢失工具调用标识后静默拼接工具消息。
            raise AppException(
                code=4090, message="当前会话包含不支持的消息类型", status_code=409
            )
        messages.append(message_type(content=item.content))
    messages.append(HumanMessage(content=data.content))
    return conversation, messages


# 保存本轮问答
async def _save_turn(
    db: AsyncSession,
    conversation: Conversation,
    data: ChatRequest,
    user_id: UUID,
    reply: str,
) -> ChatResponse:
    """仅写入并构造响应，由调用方决定何时提交事务。"""
    # 两次写入仅 flush；本轮问答最终统一 commit。
    user_message = await message_service.add_message(
        db,
        conversation.id,
        MessageCreate(content=data.content),
        user_id,
        commit=False,
    )
    assistant_message = await message_service.add_message(
        db,
        conversation.id,
        MessageCreate(content=reply),
        user_id,
        role="assistant",
        commit=False,
    )
    conversation.updated_at = datetime.now(UTC).replace(tzinfo=None)
    await db.flush()
    result = ChatResponse(
        conversation_id=conversation.id,
        user_message=MessageResponse.model_validate(user_message),
        assistant_message=MessageResponse.model_validate(assistant_message),
    )
    return result


# SSE 流式聊天
async def prepare_chat_stream(
    db: AsyncSession, data: ChatRequest, user_id: UUID, role: str | None = None
) -> AsyncIterator[tuple[str, dict]]:
    """在发送响应头前检查权限；返回按需消费的流，事务持续至生成完成。"""
    try:
        conversation, messages = await _prepare_chat(db, data, user_id)
    except BaseException:
        await db.rollback()
        raise
    return _stream_turn(db, conversation, messages, data, user_id, role)


# 执行流式聊天
async def _stream_turn(
    db: AsyncSession,
    conversation: Conversation,
    messages: list[BaseMessage],
    data: ChatRequest,
    user_id: UUID,
    role: str | None,
) -> AsyncIterator[tuple[str, dict]]:
    """逐段输出，完整生成并提交后才发送 done；中断不保存半条回复。"""
    committed = False
    try:
        yield "start", {"conversation_id": str(conversation.id)}
        parts: list[str] = []
        stream_kwargs = {"enable_thinking": data.enable_thinking}
        if role is not None:
            stream_kwargs.update(db=db, user_role=role, user_id=user_id)
        async with aclosing(llm_service.stream_chat(messages, **stream_kwargs)) as stream:
            async for content in stream:
                parts.append(content)
                yield "delta", {"content": content}
        reply = "".join(parts)
        if not reply.strip():
            raise ValueError("模型返回空内容")
        result = await _save_turn(db, conversation, data, user_id, reply)
        await db.commit()
        committed = True
        yield "done", result.model_dump(mode="json")
    except Exception as exc:
        logger.exception("流式聊天失败：%s", type(exc).__name__)
        # 流启动后不能更改 HTTP 状态码，使用事件传达失败，不暴露上游详情。
        yield "error", {"code": 5020, "message": "聊天未完成，请稍后重试"}
    finally:
        if not committed:
            # Starlette 断开连接时可能处于取消作用域，屏蔽取消以完成回滚。
            with anyio.CancelScope(shield=True):
                await db.rollback()
