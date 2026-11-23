"""使用内存数据库验证聊天事务与权限，不调用真实模型服务。"""

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.database import Base
from core.exceptions import AppException, NotFoundException
from models.conversation import Conversation
from models.message import Message
from models.user import User
from schemas.agent import RouteDecision
from schemas.chat import ChatRequest
from services.chat_service import chat, prepare_chat_stream
from services.llm import llm_service


class ChatServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(self.engine, expire_on_commit=False)
        user = User(username="chat-user", password="hash", name="聊天用户")
        self.db.add(user)
        await self.db.commit()
        self.user_id = user.id
        self.original_chat = llm_service.chat
        self.model_patch = patch("services.chat_service.llm_service.chat", new_callable=AsyncMock)
        self.model = self.model_patch.start()
        self.model.return_value = "你好"

    async def asyncTearDown(self):
        self.model_patch.stop()
        await self.db.close()
        await self.engine.dispose()

    async def test_profile_workflow_reads_only_authenticated_account_in_chat_and_stream(self):
        owner = await self.db.get(User, self.user_id)
        owner.email = "self@example.com"
        self.db.add(User(
            username="other", password="hash", name="其他用户",
            email="other@example.com", role="admin",
        ))
        await self.db.commit()
        self.model.side_effect = self.original_chat

        with patch.object(llm_service, "classify_request", side_effect=[
            RouteDecision(intent="user_profile_query", route_reason="本人邮箱和角色", profile_fields=["email", "role"]),
            RouteDecision(intent="user_profile_query", route_reason="追问本人手机号", profile_fields=["phone"]),
        ]):
            reply = await chat(
                self.db, ChatRequest(content="我的邮箱和角色是什么？"), self.user_id, role="student",
            )
            stream = await prepare_chat_stream(
                self.db, ChatRequest(conversation_id=reply.conversation_id, content="那我的手机号呢？"),
                self.user_id, role="student",
            )
            events = [(event, payload) async for event, payload in stream]

        self.assertEqual(reply.assistant_message.content, "- 邮箱：self@example.com\n- 角色：学生")
        self.assertEqual([event for event, _ in events if event != "thinking"], ["start", "delta", "done"])
        self.assertTrue(any(event == "thinking" for event, _ in events))
        self.assertEqual(next(payload["content"] for event, payload in events if event == "delta"), "你的手机号：未填写。")

    async def test_reply_feedback_persists_and_requires_owned_assistant_message(self):
        from httpx import ASGITransport, AsyncClient
        from api.deps import get_current_user
        from core.database import get_db
        from main import app

        turn = await chat(self.db, ChatRequest(content="你好"), self.user_id)
        owner = await self.db.get(User, self.user_id)
        other = User(username="feedback-other", password="hash", name="其他用户")
        self.db.add(other)
        await self.db.commit()
        app.dependency_overrides[get_current_user] = lambda: owner
        app.dependency_overrides[get_db] = lambda: self.db
        self.addCleanup(app.dependency_overrides.clear)

        messages_url = f"/api/v1/conversations/{turn.conversation_id}/messages"
        reply_url = f"{messages_url}/{turn.assistant_message.id}/feedback"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for rating in ("positive", "negative", None):
                response = await client.put(reply_url, json={"feedback": rating})
                self.assertEqual(response.status_code, 200)
                history = await client.get(messages_url)
                self.assertEqual(history.json()["data"]["items"][1]["feedback"], rating)

            prompt_url = f"{messages_url}/{turn.user_message.id}/feedback"
            self.assertEqual((await client.put(prompt_url, json={"feedback": "positive"})).status_code, 404)
            app.dependency_overrides[get_current_user] = lambda: other
            self.assertEqual((await client.put(reply_url, json={"feedback": "positive"})).status_code, 404)

    async def test_create_and_continue_with_history(self):
        first = await chat(self.db, ChatRequest(content="第一问"), self.user_id)
        second = await chat(
            self.db, ChatRequest(conversation_id=first.conversation_id, content="第二问"), self.user_id
        )
        self.assertEqual(first.conversation_id, second.conversation_id)
        messages = self.model.call_args.args[0]
        self.assertEqual([item.content for item in messages], ["第一问", "你好", "第二问"])
        self.assertIsInstance(messages[0], HumanMessage)
        self.assertIsInstance(messages[1], AIMessage)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 4)

    async def test_missing_and_foreign_conversations_rejected(self):
        first = await chat(self.db, ChatRequest(content="私密消息"), self.user_id)
        self.model.reset_mock()
        for conversation_id, user_id in ((uuid4(), self.user_id), (first.conversation_id, uuid4())):
            with self.assertRaises(NotFoundException):
                await chat(self.db, ChatRequest(conversation_id=conversation_id, content="读取"), user_id)
        self.model.assert_not_called()

    async def test_model_failure_rolls_back_new_conversation(self):
        self.model.side_effect = TimeoutError("upstream timeout")
        with self.assertRaises(AppException) as caught:
            await chat(self.db, ChatRequest(content="失败请求"), self.user_id)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Conversation)), 0)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 0)

    async def test_empty_reply_preserves_existing_history(self):
        first = await chat(self.db, ChatRequest(content="成功请求"), self.user_id)
        self.model.return_value = "  "
        with self.assertRaises(AppException):
            await chat(self.db, ChatRequest(conversation_id=first.conversation_id, content="失败请求"), self.user_id)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 2)

    async def test_message_write_failure_rolls_back_entire_turn(self):
        from services import message_service

        original = message_service.add_message

        async def fail_assistant(*args, **kwargs):
            if kwargs.get("role") == "assistant":
                raise RuntimeError("模拟助手消息写入失败")
            return await original(*args, **kwargs)

        with patch("services.chat_service.message_service.add_message", side_effect=fail_assistant):
            with self.assertRaises(RuntimeError):
                await chat(self.db, ChatRequest(content="事务测试"), self.user_id)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Conversation)), 0)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 0)

    async def test_stream_success_saves_complete_reply(self):
        async def chunks(messages, *, enable_thinking=False):
            yield "你"
            yield "好\n世界"

        with patch("services.chat_service.llm_service.stream_chat", chunks):
            stream = await prepare_chat_stream(self.db, ChatRequest(content="问候"), self.user_id)
            events = [event async for event in stream]
        self.assertEqual([name for name, _ in events if name != "thinking"], ["start", "delta", "delta", "done"])
        self.assertTrue(any(name == "thinking" for name, _ in events))
        self.assertEqual(events[-1][1]["assistant_message"]["content"], "你好\n世界")
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 2)

    async def test_stream_failure_rolls_back(self):
        async def chunks(messages, *, enable_thinking=False):
            yield "部分回复"
            raise TimeoutError("模型断流")

        with patch("services.chat_service.llm_service.stream_chat", chunks):
            stream = await prepare_chat_stream(self.db, ChatRequest(content="失败"), self.user_id)
            events = [event async for event in stream]
        self.assertEqual([name for name, _ in events if name != "thinking"], ["start", "delta", "error"])
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Conversation)), 0)
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Message)), 0)

    async def test_stream_disconnect_closes_model_and_rolls_back(self):
        closed = []

        async def chunks(messages, *, enable_thinking=False):
            try:
                yield "部分回复"
                yield "剩余回复"
            finally:
                closed.append(True)

        with patch("services.chat_service.llm_service.stream_chat", chunks):
            stream = await prepare_chat_stream(self.db, ChatRequest(content="中断"), self.user_id)
            await anext(stream)
            while True:
                event, payload = await anext(stream)
                if event == "delta":
                    break
            await stream.aclose()
        self.assertEqual(closed, [True])
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Conversation)), 0)

    async def test_stream_checks_ownership_before_iteration(self):
        with self.assertRaises(NotFoundException):
            await prepare_chat_stream(
                self.db, ChatRequest(conversation_id=uuid4(), content="越权"), self.user_id
            )

    async def test_llm_stream_only_emits_public_response(self):
        self.model_patch.stop()
        from services.llm import llm_service

        with patch("services.workflows.supervisor.workflow.run", new_callable=AsyncMock) as run:
            run.return_value = "公开回复"
            result = [text async for text in llm_service.stream_chat([HumanMessage(content="问题")])]
        self.assertEqual(result, ["公开回复"])
        run.assert_awaited_once()

    async def test_stream_endpoint_returns_sse(self):
        from httpx import ASGITransport, AsyncClient
        from api.deps import get_current_user
        from core.database import get_db
        from main import app
        from types import SimpleNamespace

        async def chunks(messages, *, enable_thinking=False, db=None, user_role="student", user_id=None):
            yield "你好\n世界"

        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=self.user_id, role="student"
        )

        async def database():
            yield self.db

        app.dependency_overrides[get_db] = database
        try:
            with patch("services.chat_service.llm_service.stream_chat", chunks):
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    response = await client.post("/api/v1/chat/stream", json={"content": "你好"})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
            self.assertIn("event: delta", response.text)
            self.assertIn("event: done", response.text)
            self.assertNotIn("event: error", response.text)
        finally:
            app.dependency_overrides.clear()

    def test_blank_input_rejected(self):
        with self.assertRaises(ValidationError):
            ChatRequest(content=" \n\t")

    async def test_history_endpoint_pagination_and_ownership(self):
        from httpx import ASGITransport, AsyncClient
        from api.deps import get_current_user
        from core.database import get_db
        from main import app
        from types import SimpleNamespace

        result = await chat(self.db, ChatRequest(content="历史消息"), self.user_id)
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=self.user_id)

        async def database():
            yield self.db

        app.dependency_overrides[get_db] = database
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                url = f"/api/v1/conversations/{result.conversation_id}/messages"
                response = await client.get(url, params={"page": 2, "size": 1})
                self.assertEqual(response.status_code, 200)
                data = response.json()["data"]
                self.assertEqual(data["total"], 2)
                self.assertEqual(data["items"][0]["role"], "assistant")
                app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4())
                response = await client.get(url)
                self.assertEqual(response.status_code, 404)
        finally:
            app.dependency_overrides.clear()
