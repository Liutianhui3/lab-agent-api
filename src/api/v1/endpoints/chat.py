"""聊天 HTTP 接口；业务流程由 chat_service 统一编排。"""

import json
from contextlib import aclosing
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser
from core.database import get_db
from schemas.chat import ChatRequest, ChatResponse
from schemas.response import BaseResponse
from services import chat_service

router = APIRouter(prefix="/chat", tags=["AI 聊天"])


@router.post("", response_model=BaseResponse[ChatResponse], summary="发送消息并获取模型回复")
async def chat(
    data: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[ChatResponse]:
    """需登录；不传 conversation_id 创建新会话，传入则携带历史继续聊天。"""
    result = await chat_service.chat(db=db, data=data, user_id=current_user.id)
    return BaseResponse[ChatResponse].success(data=result)


@router.post(
    "/stream", summary="流式聊天（SSE）", response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def chat_stream(
    data: ChatRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="request")],
) -> StreamingResponse:
    """通过 start、delta、done、error 事件返回结果；数据库会话覆盖整个响应。"""
    events = await chat_service.prepare_chat_stream(db, data, current_user.id)

    async def event_body():
        # 连接中断时关闭业务生成器，使其释放上游模型流及未提交事务。
        async with aclosing(events):
            async for event, payload in events:
                encoded = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event}\ndata: {encoded}\n\n"

    return StreamingResponse(
        event_body(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
