"""只读用户资料查询工具；在工具层执行认证身份与查询范围校验。"""
from langchain.tools import ToolRuntime, tool

from models.user import User
from services import user_service


def public_profile(user) -> dict:
    return {key: getattr(user, key) for key in
            ("username", "name", "role", "email", "phone", "status", "avatar")}


@tool
async def get_my_profile(runtime: ToolRuntime[dict], phone: str | None = None) -> dict:
    """Read the authenticated user's own profile. Optional phone must exactly match the authenticated account; mismatches return no profile."""
    user_id = runtime.context.get("user_id")
    if user_id is None:
        return {"error": "authentication_required"}
    user = await runtime.context["db"].get(User, user_id)
    if phone is not None and (user is None or user.phone != phone):
        return {"error": "no_accessible_match"}
    return {"profile": public_profile(user) if user else None}


@tool
async def search_user_profiles(
    runtime: ToolRuntime[dict], keyword: str | None = None,
    role: str | None = None, page_number: int = 1,
) -> dict:
    """Search users by phone, email, username or name. Admin searches platform-wide; student searches exact matches within their own account only. Role may be admin or student."""
    if role not in {None, "admin", "student"} or page_number < 1:
        return {"error": "invalid_filter"}
    if runtime.context.get("user_role") == "student":
        user_id = runtime.context.get("user_id")
        if user_id is None:
            return {"error": "authentication_required"}
        user = await runtime.context["db"].get(User, user_id)
        # Exact matching within the authenticated account only. Never search other accounts,
        # return platform counts, or fall back to the student's profile on a mismatch.
        matches = user is not None and (role is None or role == user.role) and (
            keyword is None or keyword == "" or keyword in
            (user.phone, user.email, user.username, user.name)
        )
        return {"items": [public_profile(user)] if matches and page_number == 1 else [],
                "total": int(matches), "page": page_number, "size": 50, "has_more": False}
    if runtime.context.get("user_role") != "admin":
        return {"error": "permission_denied"}
    result = await user_service.get_user_page(
        runtime.context["db"], page=page_number, size=50, keyword=keyword, role=role,
    )
    return {"items": [public_profile(user) for user in result.items],
            "total": result.total, "page": result.page, "size": result.size,
            "has_more": result.page * result.size < result.total}


