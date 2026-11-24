"""Profile query tool authorization and database search contracts."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import HumanMessage

from services.workflows.user.agents import profile_agent as query
from services.workflows.user.tools import profile_tools
from services.workflows.supervisor import workflow
from services.workflows.supervisor.tools import workflow_tools
from services.workflows.supervisor.agents import supervisor_agent
from agent_fakes import call, model
from langchain_core.messages import AIMessage
import asyncio


class ProfileQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_student_search_denied_before_database_access(self):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(phone="13900000000", email=None, username="me", name="本人", role="student")
        runtime = SimpleNamespace(context={"user_role": "student", "user_id": uuid4(), "db": db})
        with patch.object(profile_tools.user_service, "get_user_page", new_callable=AsyncMock) as search:
            result = await profile_tools.search_user_profiles.coroutine(runtime=runtime, keyword="13800138000")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["total"], 0)
        search.assert_not_awaited()

    async def test_admin_phone_search_returns_only_public_fields(self):
        profile = SimpleNamespace(username="tina", name="学生", role="student", phone="13800138000",
                                  email=None, status=1, avatar=None, password="secret")
        runtime = SimpleNamespace(context={"user_role": "admin", "db": object()})
        with patch.object(profile_tools.user_service, "get_user_page", new_callable=AsyncMock) as search:
            search.return_value = SimpleNamespace(items=[profile], total=1, page=1, size=50)
            result = await profile_tools.search_user_profiles.coroutine(runtime=runtime, keyword="13800138000")
        self.assertEqual(search.await_args.kwargs["keyword"], "13800138000")
        self.assertEqual(result["items"][0]["username"], "tina")
        self.assertNotIn("password", result["items"][0])

    async def test_own_profile_uses_authenticated_id(self):
        db = AsyncMock()
        db.get.return_value = None
        identity = uuid4()
        result = await profile_tools.get_my_profile.coroutine(runtime=SimpleNamespace(context={"db": db, "user_id": identity}))
        db.get.assert_awaited_once_with(profile_tools.User, identity)
        self.assertIsNone(result["profile"])

    async def test_supervisor_passes_history_and_authenticated_context(self):
        messages = [HumanMessage(content="13800138000手机号是哪个用户的")]
        identity = uuid4()
        with patch.object(query, "run", new_callable=AsyncMock, return_value="tina") as run:
            result = await workflow_tools.query_profiles.coroutine(
                runtime=SimpleNamespace(context={"messages": messages, "user_role": "admin", "user_id": identity,
                    "db": None, "enable_thinking": False, "db_lock": asyncio.Lock()}), request=messages[-1].content)
        self.assertEqual(result, "tina")
        self.assertEqual(run.await_args.args[0][:len(messages)], messages)
        self.assertEqual(run.await_args.kwargs["user_role"], "admin")
        self.assertEqual(run.await_args.kwargs["user_id"], identity)

    async def test_student_exact_phone_match_returns_only_own_profile(self):
        profile = SimpleNamespace(username="me", name="本人", role="student", phone="13900000000",
                                  email=None, status=1, avatar=None)
        db = AsyncMock()
        db.get.return_value = profile
        runtime = SimpleNamespace(context={"user_role": "student", "user_id": uuid4(), "db": db})
        result = await profile_tools.search_user_profiles.coroutine(runtime=runtime, keyword=profile.phone)
        self.assertEqual(result["items"][0]["username"], "me")
        result = await profile_tools.search_user_profiles.coroutine(runtime=runtime, keyword="139")
        self.assertEqual(result["items"], [])

    async def test_own_profile_phone_mismatch_does_not_return_profile(self):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(phone="13900000000")
        runtime = SimpleNamespace(context={"user_id": uuid4(), "db": db})
        result = await profile_tools.get_my_profile.coroutine(runtime=runtime, phone="13800138000")
        self.assertEqual(result, {"error": "no_accessible_match"})

    async def test_student_workflow_reuses_agent(self):
        messages = [HumanMessage(content="我的资料")]
        with patch.object(query, "run", new_callable=AsyncMock, return_value="本人资料") as run:
            result = await workflow_tools.query_profiles.coroutine(
                runtime=SimpleNamespace(context={"messages": messages, "user_role": "student", "user_id": uuid4(),
                    "db": None, "enable_thinking": False, "db_lock": asyncio.Lock()}), request=messages[-1].content)
        self.assertEqual(result, "本人资料")
        self.assertEqual(run.await_args.kwargs["user_role"], "student")


class ProfileEditCardTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_edit_card_in_normal_and_stream_workflows(self):
        import json
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from core.database import Base
        from models.user import User
        from services.llm import llm_service

        engine = create_async_engine("sqlite+aiosqlite://")
        self.addAsyncCleanup(engine.dispose)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as db:
            owner = User(username="owner", name="本人", password="secret", role="student", status=1)
            other = User(username="other", name="其他人", password="secret", role="student", status=1)
            db.add_all([owner, other])
            await db.commit()
            messages = [HumanMessage(content="修改我的个人资料")]
            with (
                patch.object(llm_service, "llm", model(
                    call("prepare_my_profile_edit"), call("prepare_my_profile_edit", identity="call-2"))),
                patch.object(query, "run", new_callable=AsyncMock) as query_agent,
            ):
                reply = await workflow.run(messages, db=db, user_id=owner.id, user_role="student")
                events = [event async for event in workflow.stream(
                    messages, db=db, user_id=owner.id, user_role="student")]
            card = json.loads(reply)
            self.assertEqual(card["type"], "user_profile_edit")
            self.assertEqual(card["data"]["id"], str(owner.id))
            self.assertEqual(card["data"]["username"], "owner")
            self.assertNotIn("password", card["data"])
            self.assertEqual([payload["content"] for event, payload in events if event == "delta"], [reply])
            query_agent.assert_not_awaited()
