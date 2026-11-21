from typing import Literal
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.exceptions import AppException
from core.security import get_password_hash, verify_password
from models.user import User
from schemas.auth import PasswordUpdateRequest
from schemas.user import (
    UserCreateRequest,
    UserProfileUpdateRequest,
    UserPageData,
    UserResponse,
    UserUpdateRequest,
)


def get_user_info(current_user: User) -> UserResponse:
    """将认证依赖查到的最新用户记录转换为公开资料，不返回密码哈希。"""
    return UserResponse.model_validate(current_user)


async def get_user_page(
    db: AsyncSession, page: int, size: int, keyword: str | None = None,
    role: Literal["admin", "student"] | None = None
) -> UserPageData[UserResponse]:
    """组合角色与关键词条件查询用户，列表和总数使用相同筛选条件。"""
    query = select(User)
    count_query = select(func.count()).select_from(User)

    if role is not None:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)

    search = keyword.strip() if keyword else ""
    if search:
        pattern = f"%{search}%"
        conditions = or_(
            User.username.ilike(pattern),
            User.name.ilike(pattern),
            User.email.ilike(pattern),
            User.phone.ilike(pattern),
        )
        query = query.where(conditions)
        count_query = count_query.where(conditions)

    total = await db.scalar(count_query) or 0
    admin_count = await db.scalar(
        select(func.count()).select_from(User).where(User.role == "admin")
    ) or 0
    disabled_count = await db.scalar(
        select(func.count()).select_from(User).where(User.status == 0)
    ) or 0
    global_total = await db.scalar(select(func.count()).select_from(User)) or 0
    users = (await db.scalars(
        query.order_by(User.created_at.desc(), User.id).offset((page - 1) * size).limit(size)
    )).all()
    return UserPageData(
        total=total,
        items=[UserResponse.model_validate(user) for user in users],
        page=page,
        size=size,
        global_total=global_total,
        admin_count=admin_count,
        disabled_count=disabled_count,
    )


async def update_user(
    db: AsyncSession, current_user: User, request: UserProfileUpdateRequest | UserUpdateRequest
) -> UserResponse:
    """仅更新当前登录用户的资料；未提交的字段保持不变。"""
    updates = request.model_dump(exclude_unset=True)
    if not updates:
        return get_user_info(current_user)

    try:
        username = updates.get("username")
        if username is not None and await db.scalar(
            select(User.id).where(User.username == username, User.id != current_user.id)
        ) is not None:
            raise AppException(code=4008, message="用户名已被使用", status_code=409)

        # 提前查询提供友好提示；排除自己，允许继续使用原邮箱。
        # 数据库唯一约束仍负责处理并发更新时的邮箱冲突。
        email = updates.get("email")
        if email is not None and await db.scalar(
            select(User.id).where(User.email == email, User.id != current_user.id)
        ) is not None:
            raise AppException(code=4009, message="邮箱已被使用", status_code=409)

        # schema 仅开放个人资料字段；显式 null 会清空对应可空列。
        for field, value in updates.items():
            setattr(current_user, field, value)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        # 仅唯一键冲突转换为业务提示，其他完整性错误交给全局处理器。
        original = error.orig
        if (
            getattr(original, "args", (None,))[0] == 1062
            or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
        ):
            raise AppException(
                code=4009, message="用户名或邮箱已被使用", status_code=409
            ) from error
        raise
    except Exception:
        await db.rollback()
        raise

    # 获取数据库维护的 updated_at 等最新值，再返回公开资料。
    await db.refresh(current_user)
    return get_user_info(current_user)


async def update_password(
    db: AsyncSession, current_user: User, request: PasswordUpdateRequest
) -> None:
    """验证旧密码并更新密码哈希；业务校验失败时不修改数据库。"""
    old_password = request.old_password.get_secret_value()
    new_password = request.new_password.get_secret_value()

    # 旧密码是否匹配依赖当前数据库记录，属于业务校验而非请求格式校验。
    if not await run_in_threadpool(verify_password, old_password, current_user.password):
        raise AppException(code=4001, message="当前密码错误", status_code=400)

    # 新旧密码相同是业务规则，也在这里处理以保持 Schema 只关心输入格式。
    if await run_in_threadpool(verify_password, new_password, current_user.password):
        raise AppException(code=4002, message="新密码不能与当前密码相同", status_code=400)

    try:
        # 数据库只保存单向哈希，不保存明文密码。
        current_user.password = await run_in_threadpool(get_password_hash, new_password)
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def create_user(db: AsyncSession, request: UserCreateRequest) -> UserResponse:
    """创建用户并保存管理员输入密码的哈希。"""
    user = User(
        **request.model_dump(exclude={"password"}),
        password=await run_in_threadpool(
            get_password_hash, request.password.get_secret_value()
        ),
    )
    try:
        db.add(user)
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        original = error.orig
        if (
            getattr(original, "args", (None,))[0] == 1062
            or getattr(original, "sqlite_errorname", None) == "SQLITE_CONSTRAINT_UNIQUE"
        ):
            raise AppException(code=4009, message="用户名或邮箱已被使用", status_code=409) from error
        raise
    except Exception:
        await db.rollback()
        raise
    await db.refresh(user)
    return get_user_info(user)


async def update_managed_user(
    db: AsyncSession, user_id: UUID, request: UserUpdateRequest
) -> UserResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise AppException(code=4040, message="用户不存在", status_code=404)
    return await update_user(db, user, request)


async def delete_user(db: AsyncSession, user_id: UUID) -> None:
    """通过带状态条件的删除，保证只有禁用账号可删除。"""
    try:
        result = await db.execute(delete(User).where(User.id == user_id, User.status == 0))
        if result.rowcount == 0:
            if await db.get(User, user_id) is None:
                raise AppException(code=4040, message="用户不存在", status_code=404)
            raise AppException(code=4003, message="只有禁用状态的用户才允许删除", status_code=400)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
