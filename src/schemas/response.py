from typing import Any

from pydantic import BaseModel, Field


class BaseResponse[T](BaseModel):
    """企业级通用标准 API 响应结构

    示例:
        {
            "code": 200,
            "message": "success",
            "data": { ... }
        }
    """

    code: int = Field(
        default=200, description="业务状态码：200 表示成功，其他为特定错误码"
    )
    message: str = Field(default="success", description="操作提示信息")
    data: T | None = Field(default=None, description="业务核心数据")

    # Pydantic v2 推荐的配置写法
    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {"code": 200, "message": "success", "data": None}
        },
    }

    @classmethod
    def success(cls, data: Any = None, message: str = "success") -> "BaseResponse[Any]":
        """成功响应快捷工厂方法

        Usage:
            return BaseResponse.success(data=user_info)
        """
        return cls(code=200, message=message, data=data)

    @classmethod
    def fail(
        cls, code: int = 400, message: str = "error", data: Any = None
    ) -> "BaseResponse[Any]":
        """失败响应快捷工厂方法

        Usage:
            return BaseResponse.fail(code=4001, message="用户不存在")
        """
        return cls(code=code, message=message, data=data)


class PageData[T](BaseModel):
    """分页数据通用容器结构"""

    total: int = Field(default=0, description="数据总条数")
    items: list[T] = Field(default_factory=list, description="当前页数据列表")
    page: int = Field(default=1, description="当前页码")
    size: int = Field(default=10, description="每页显示条数")


class PageResponse[T](BaseResponse[PageData[T]]):
    """分页标准响应结构"""

    @classmethod
    def success(
        cls,
        items: list[Any],
        total: int,
        page: int = 1,
        size: int = 10,
        message: str = "success",
    ) -> "PageResponse[Any]":
        """分页成功响应快捷工厂方法"""
        page_data = PageData(total=total, items=items, page=page, size=size)
        return cls(code=200, message=message, data=page_data)
