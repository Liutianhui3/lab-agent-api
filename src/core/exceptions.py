import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from schemas.response import BaseResponse

logger = logging.getLogger(__name__)


# ==================== 1. 定义自定义业务异常基类 ====================
class AppException(Exception):
    """应用层自定义异常基类"""

    def __init__(
        self,
        code: int = 500,
        message: str = "error",
        status_code: int = status.HTTP_200_OK,
    ):
        self.code = code  # 业务状态码（如 4001, 5001）
        self.message = message  # 给前端展示的提示信息
        self.status_code = status_code
        super().__init__(self.message)


# ==================== 2. 定义具体的常见业务异常 ====================
class NotFoundException(AppException):
    """资源不存在异常"""

    def __init__(self, message: str = "请求的资源不存在"):
        super().__init__(code=4040, message=message, status_code=404)


class AuthException(AppException):
    """认证与权限异常"""

    def __init__(self, message: str = "认证失败或 Token 已过期"):
        super().__init__(code=4010, message=message, status_code=401)


class ForbiddenException(AppException):
    """无权限操作异常"""

    def __init__(self, message: str = "没有操作权限"):
        super().__init__(code=4030, message=message, status_code=403)


# ==================== 3. 注册全局异常处理器 ====================
def register_exception_handlers(app: FastAPI) -> None:
    """将所有自定义异常和系统异常注册到 FastAPI 应用中"""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """捕获所有自定义的业务异常"""
        return JSONResponse(
            status_code=exc.status_code,
            content=BaseResponse.fail(code=exc.code, message=exc.message).model_dump(
                mode="json"
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        """统一 HTTP 异常响应，并保留认证等响应头。"""
        return JSONResponse(
            status_code=exc.status_code,
            headers=exc.headers,
            content=BaseResponse.fail(
                code=exc.status_code * 10,
                message=str(exc.detail),
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """捕获 Pydantic 参数校验失败异常（前端传参格式不对时触发）"""
        error_msg = "请求参数校验错误"
        # 只返回校验提示，不回传包含明文密码的 input 或请求体。
        password_errors = [
            error["msg"].removeprefix("Value error, ")
            for error in exc.errors()
            if error["loc"] in {
                ("body", "password"),
                ("body", "new_password"),
            }
        ]
        if password_errors:
            error_msg = "；".join(password_errors)

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=BaseResponse.fail(code=4220, message=error_msg).model_dump(
                mode="json"
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        """捕获数据库操作异常（防止 SQL 报错直接暴露给前端）"""
        logger.exception("数据库操作异常", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=BaseResponse.fail(code=5000, message="数据库操作异常").model_dump(
                mode="json"
            ),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """捕获其他未预料的系统级异常"""
        logger.exception("未处理的服务器异常", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=BaseResponse.fail(code=5001, message="服务器内部错误").model_dump(
                mode="json"
            ),
        )
