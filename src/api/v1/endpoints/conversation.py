from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentUser
from core.database import get_db
from schemas.conversation import (
    ConversationCreate,
    ConversationPageResponse,
    ConversationResponse,
)
from schemas.response import BaseResponse
from services import conversation_service, message_service
from schemas.message import MessagePageData, MessageResponse

router = APIRouter(prefix="/conversations", tags=["ai会话"])


# 创建会话
@router.post(
    "",
    response_model=BaseResponse[ConversationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    data: ConversationCreate,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[ConversationResponse]:
    conversation = await conversation_service.create_conversation(
        db=db,
        user_id=current_user.id,
        title=data.title or "新对话",
    )
    return BaseResponse[ConversationResponse].success(
        data=conversation, message="创建成功"
    )


# 获取会话列表
@router.get("", response_model=ConversationPageResponse[ConversationResponse])
async def get_conversation_list(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    page: int = Query(default=1, ge=1, description="页码"),
    size: int = Query(default=10, ge=1, le=100, description="每页条数"),
) -> ConversationPageResponse[ConversationResponse]:
    data = await conversation_service.get_conversation_list(
        db, user_id=current_user.id, page=page, size=size
    )
    return ConversationPageResponse[ConversationResponse].success(data=data)


# 获取会话详情
@router.get("/{conversation_id}", response_model=BaseResponse[ConversationResponse])
async def get_conversation_detail(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[ConversationResponse]:
    conversation = await conversation_service.get_conversation_detail(
        db=db, conversation_id=conversation_id, user_id=current_user.id
    )

    if not conversation:
        raise HTTPException(status_code=404, detail="会话不存在")

    return BaseResponse[ConversationResponse].success(data=conversation)


# 删除会话
@router.delete("/{conversation_id}", response_model=BaseResponse[None])
async def delete_conversation(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
) -> BaseResponse[None]:
    success = await conversation_service.delete_conversation(
        db=db, conversation_id=conversation_id, user_id=current_user.id
    )

    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")

    return BaseResponse[None].success(message="删除成功")


@router.get("/{conversation_id}/messages", response_model=BaseResponse[MessagePageData[MessageResponse]])
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db, scope="function")],
    page: int = Query(default=1, ge=1),
    size: int = Query(default=100, ge=1, le=100),
) -> BaseResponse[MessagePageData[MessageResponse]]:
    """校验当前用户的会话归属，按时间正序返回消息。"""
    data = await message_service.get_messages(db, conversation_id, current_user.id, page, size)
    return BaseResponse.success(data=data)
