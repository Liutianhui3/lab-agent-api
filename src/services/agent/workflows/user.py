"""UserWorkflow：查询当前登录用户的账户资料。"""

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User
from schemas.agent import ProfileField

PROFILE_COLUMNS = {
    "role": (User.role, "角色"),
    "email": (User.email, "邮箱"),
    "phone": (User.phone, "手机号"),
    "username": (User.username, "用户名"),
    "name": (User.name, "姓名"),
    "status": (User.status, "账号状态"),
}
ROLE_NAMES = {"student": "学生", "admin": "管理员"}
STATUS_NAMES = {0: "禁用", 1: "正常"}


async def run(
    *, db: AsyncSession | None, user_id: UUID | None, fields: Sequence[ProfileField],
    output_format: Literal["text", "list", "table"] | None = None,
) -> str:
    if db is None or user_id is None:
        return "暂时无法读取你的账号资料，请登录后再试。"

    selected = [field for field in dict.fromkeys(fields) if field in PROFILE_COLUMNS]
    if not selected:
        return "你想查自己的哪项资料？比如角色、邮箱或手机号。"

    columns, labels = zip(*(PROFILE_COLUMNS[field] for field in selected))
    result = await db.execute(select(*columns).where(User.id == user_id))
    row = result.one_or_none()
    if row is None:
        return "没有找到当前账号的资料，请重新登录后再试。"

    rows = []
    for field, label, value in zip(selected, labels, row):
        if field == "role":
            value = ROLE_NAMES.get(value, value)
        elif field == "status":
            value = STATUS_NAMES.get(value, value)
        display = str(value) if value is not None and value != "" else "未填写"
        rows.append((label, " ".join(display.splitlines())))

    if output_format == "table":
        lines = ["| 项目 | 内容 |", "| --- | --- |"]
        for label, value in rows:
            cell = value.replace("|", "&#124;")
            lines.append(f"| {label} | {cell} |")
        return "\n".join(lines)
    lines = [f"{label}：{value}" for label, value in rows]
    if output_format == "text" or (output_format is None and len(lines) == 1):
        return "你的" + "，".join(lines) + "。"
    return "\n".join(f"- {line}" for line in lines)
