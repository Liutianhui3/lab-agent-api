"""管理员用户管理工作流：生成待确认卡片，不直接修改数据。"""
import json
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User


async def run(*, db: AsyncSession | None, action: str, user_identifier: str | None = None, fields: dict | None = None) -> str:
    data = dict(fields or {})
    if db is not None and user_identifier and action in {"admin_user_edit", "admin_user_delete"}:
        criterion = (
            User.id == UUID(user_identifier)
            if _is_uuid(user_identifier)
            else or_(User.username == user_identifier, User.name == user_identifier)
        )
        targets = (await db.scalars(select(User).where(criterion).order_by(User.username).limit(20))).all()
        if not targets:
            return json.dumps({"type": "admin_user_not_found", "message": "用户不存在"}, ensure_ascii=False)
        if len(targets) > 1:
            return json.dumps({"type": "admin_user_select", "action": action, "query": user_identifier,
                "items": [_public_user(target) for target in targets]}, ensure_ascii=False)
        target = targets[0]
        if action == "admin_user_delete" and target.status != 0:
            return (
                f"用户“{target.name or target.username}”当前处于正常状态，"
                "只有禁用状态的用户才允许删除。"
                "请先在用户管理中禁用该账号，再发起删除。"
            )
        data = {**_public_user(target), **data}
        if action == "admin_user_delete":
            # Eligibility comes from the database, never from extracted user fields.
            data["id"] = str(target.id)
            data["status"] = target.status
    return json.dumps({"type": action, "data": data}, ensure_ascii=False)

def _is_uuid(value: str) -> bool:
    try:
        UUID(value); return True
    except (ValueError, AttributeError):
        return False

def _public_user(user: User) -> dict:
    return {"id": str(user.id), "username": user.username, "name": user.name,
            "email": user.email, "phone": user.phone, "role": user.role,
            "status": user.status, "avatar": user.avatar}
