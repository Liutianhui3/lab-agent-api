import time

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from core.exceptions import AppException, AuthException, ForbiddenException
from core.redis_client import redis_client
from core.security import (
    create_access_token,
    decode_access_token,
    get_password_hash,
    verify_password,
)
from models.user import User
from schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from schemas.user import UserResponse


class UserAlreadyExistsError(AppException):
    """用户名或邮箱违反数据库唯一约束"""

    def __init__(self, message: str = "用户名或邮箱已被使用"):
        # code=4009（自定义业务码，可根据你的业务规则定义）
        # status_code=409（符合 HTTP 规范的冲突状态码）
        super().__init__(code=4009, message=message, status_code=409)


async def register_user(db: AsyncSession, request: RegisterRequest) -> User:
    """
    用户注册业务逻辑：
    1. 使用 passlib 对明文密码进行 bcrypt 哈希加密
    2. 实例化 User 模型并写入数据库
    3. 捕获数据库唯一索引冲突（IntegrityError），执行回滚并抛出业务异常
    """

    # 1. 密码加密
    hashed_pwd = await run_in_threadpool(
        get_password_hash, request.password.get_secret_value()
    )

    # 2. 构造 ORM 对象
    db_user = User(
        username=request.username,
        email=request.email,
        password=hashed_pwd,
        name=request.username,
        role="student",
        status=1,
    )

    try:
        # 3. 写入数据库会话并提交
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)  # 刷新以获取数据库自动生成的字段（如 id、created_at 等）
        return db_user

    except IntegrityError as error:
        # 4. 发生唯一键冲突时，必须先回滚事务，保证数据库连接干净
        await db.rollback()

        # 5. 将底层的数据库错误转译为你们统一的自定义业务异常
        raise UserAlreadyExistsError(message="用户名或邮箱已被使用") from error


async def login_user(db: AsyncSession, request: LoginRequest) -> LoginResponse:
    """校验用户名、密码和账号状态，成功后签发 JWT 并返回用户资料。"""
    # 1. 按唯一用户名查找账号；登录仅查询数据库，不需要 commit。
    user = await db.scalar(select(User).where(User.username == request.username))

    # 2. 使用哈希校验密码，不能直接比较明文和数据库中的密码哈希。
    # 用户不存在或密码错误时统一提示，避免通过错误信息判断用户名是否存在。
    if user is None or not await run_in_threadpool(
        verify_password, request.password.get_secret_value(), user.password
    ):
        raise AuthException(message="用户名或密码错误")

    # 3. 密码校验通过后检查状态，禁用账号不签发令牌。
    if user.status != 1:
        raise ForbiddenException(message="用户已被禁用")

    # 4. JWT 的 sub 保存用户 UUID，与 get_current_user 的解析方式保持一致。
    # 有效期由 security.py 中的 ACCESS_TOKEN_EXPIRE_MINUTES 配置控制。
    access_token = create_access_token(subject=user.id)

    # 5. 通过响应模型筛选字段，避免把 ORM 中的密码哈希返回给前端。
    return LoginResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
    )


def is_token_revoked(jti: str) -> bool:
    """受保护接口检查 Redis 黑名单；Redis 故障时拒绝放行。"""
    try:
        return bool(redis_client.exists(f"blacklist:{jti}"))
    except RedisError as error:
        raise AppException(
            code=5030, message="认证服务暂不可用", status_code=503
        ) from error


def logout_user(token: str) -> None:
    """登出仅将当前 jti 加入 Redis 黑名单，不再读写 MySQL。"""
    payload = decode_access_token(token)
    # 必须先验证签名、有效期及 jti，防止伪造令牌写入黑名单。
    if payload is None:
        raise AuthException(message="登录已失效，请重新登录")

    remaining = payload["exp"] - int(time.time())
    if remaining <= 0:
        return
    try:
        # TTL 与 JWT 剩余有效期一致，过期自动清理；重复登出也可安全执行。
        redis_client.set(f"blacklist:{payload['jti']}", "1", ex=remaining)
    except RedisError as error:
        # 写入失败不能宣称登出成功，否则原令牌仍可访问。
        raise AppException(
            code=5030, message="认证服务暂不可用", status_code=503
        ) from error
