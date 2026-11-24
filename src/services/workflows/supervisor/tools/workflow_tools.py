"""Authenticated adapters from the supervisor to business workflows."""
from typing import Literal

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage

from services.workflows.admin import workflow as admin
from services.workflows.laboratory import workflow as laboratory
from services.workflows.user import workflow as user


def query_messages(context: dict, request: str):
    # Keep the original user question and history, including ownership constraints.
    return [*context["messages"], HumanMessage(content="本次需要处理的子任务：" + request)]


@tool
async def query_resources(runtime: ToolRuntime[dict], request: str) -> str:
    """Query or analyze laboratories and equipment, locations, capacities, inventory and fixed opening hours. Not live availability."""
    context = runtime.context
    async with context["db_lock"]:
        return await laboratory.run(
            query_messages(context, request), db=context["db"],
            enable_thinking=context["enable_thinking"],
        )


@tool
async def query_profiles(runtime: ToolRuntime[dict], request: str) -> str:
    """Query account profiles. Admin can search platform users; student can only match their own account. Preserve phone/email/name from the original request exactly."""
    context = runtime.context
    if context["user_id"] is None:
        return "请登录后查询账号资料。"
    workflow = admin.query_profiles if context["user_role"] == "admin" else user.run
    async with context["db_lock"]:
        return await workflow(
            query_messages(context, request), db=context["db"],
            user_id=context["user_id"], user_role=context["user_role"],
            enable_thinking=context["enable_thinking"],
        )


@tool(return_direct=True)
async def prepare_my_profile_edit(runtime: ToolRuntime[dict]) -> str:
    """Prepare the authenticated user's own profile edit card. Does not save changes and accepts no target user ID."""
    context = runtime.context
    async with context["db_lock"]:
        result = await user.edit_card(db=context["db"], user_id=context["user_id"])
    context["cards"].append(result)
    return result


@tool(return_direct=True)
async def prepare_user_management(
    runtime: ToolRuntime[dict],
    action: Literal["admin_user_create", "admin_user_edit", "admin_user_delete"],
    user_identifier: str | None = None,
    fields: dict[str, str | int | None] | None = None,
) -> str:
    """Admin only: prepare a create/edit/delete user confirmation card, never execute a write. For edit/delete use the name or account supplied by the user; ask if target is missing."""
    context = runtime.context
    if context["user_role"] != "admin" or context["user_id"] is None:
        return "无权管理其他用户的账号。"
    if action != "admin_user_create" and not user_identifier:
        return "请提供要操作的用户姓名或账号。"
    if context["db"] is None:
        return "暂时无法读取用户资料，请稍后再试。"
    async with context["db_lock"]:
        result = await admin.run(
            db=context["db"], action=action,
            user_identifier=user_identifier, fields=fields,
        )
    context["cards"].append(result)
    return result


@tool(return_direct=True)
async def reservation_workflow(runtime: ToolRuntime[dict], request: str) -> str:
    """Students: apply, query availability or own reservations, and prepare cancellation cards. Admins: query approval records or prepare approval cards. Never execute writes."""
    from services.workflows.reservation import workflow
    import json
    c = runtime.context
    async with c["db_lock"]:
        result = await workflow.run(query_messages(c, request), db=c["db"], user_id=c["user_id"],
            user_role=c["user_role"], enable_thinking=c["enable_thinking"],
            progress=c.setdefault("progress", []))
    try:
        if json.loads(result).get("type") in {"reservation_application", "reservation_approval", "reservation_cancellation"}:
            c["cards"].append(result)
    except (ValueError, AttributeError):
        pass
    return result
