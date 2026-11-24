import json
import unittest
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from core.database import Base
from core.exceptions import AppException
from models.user import User
from models.lab import Lab
from models.reservation import Reservation
from services.workflows.reservation import workflow
from services.workflows.reservation.tools import reservation_tools as rt
from services.workflows.reservation.agents import approval_agent
from services.workflows.reservation.workflows import application
from schemas.reservation import ReservationApplicationDraft
from services.reservation_card_service import read_card, CardConfirmation, ApprovalConfirmation
from api.v1.endpoints.reservation import confirm_application, confirm_approval
from agent_fakes import model, call
from langchain_core.messages import HumanMessage, AIMessage


class ReservationWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(self.engine, expire_on_commit=False)
        self.student = User(username="student", name="学生", password="hash", role="student", status=1)
        self.admin = User(username="admin", name="管理员", password="hash", role="admin", status=1)
        self.lab = Lab(name="光学实验室", lab_code="OPT", status=1)
        self.db.add_all([self.student, self.admin, self.lab])
        await self.db.commit()
        self.day = (datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=2)).date()

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def context(self, user):
        return {"db": self.db, "user_id": user.id, "user_role": user.role,
                "enable_thinking": False, "messages": [], "cards": [], "resource_consulted": True}

    async def application(self, user=None):
        return await rt.prepare_application.coroutine(runtime=SimpleNamespace(context=self.context(user or self.student)),
            lab_code="OPT", reservation_date=self.day, start_time=time(10), end_time=time(11))

    async def test_application_card_is_readonly_bound_and_revalidated_on_confirmation(self):
        card = json.loads(await self.application())
        self.assertFalse(card["editable"])
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Reservation)), 0)
        with self.assertRaises(AppException):
            read_card(card["token"], self.admin.id, "application")
        with self.assertRaises(AppException):
            read_card(card["token"] + "tampered", self.student.id, "application")
        result = await confirm_application(CardConfirmation(token=card["token"]), self.student, self.db)
        self.assertEqual(result.data.status, 0)
        with self.assertRaises(AppException):
            await confirm_application(CardConfirmation(token=card["token"]), self.student, self.db)

    async def test_role_boundaries(self):
        self.assertIn("只有", await self.application(self.admin))
        result = await rt.search_approvals.coroutine(runtime=SimpleNamespace(context=self.context(self.student)))
        self.assertEqual(result, {"error": "permission_denied"})
        self.assertIn("只有", await rt.prepare_approval.coroutine(
            runtime=SimpleNamespace(context=self.context(self.student)), reservation_id=1))

    async def test_approval_queries_card_and_click_only(self):
        item = Reservation(user_id=self.student.id, lab_id=self.lab.id, date=self.day,
            start_time=time(10), end_time=time(11), status=0)
        self.db.add(item)
        await self.db.commit()
        runtime = SimpleNamespace(context=self.context(self.admin))
        for status in range(4):
            result = await rt.search_approvals.coroutine(runtime=runtime, status=status)
            self.assertEqual(result["total"], 1 if status == 0 else 0)
        card = json.loads(await rt.prepare_approval.coroutine(runtime=runtime, reservation_id=item.id))
        self.assertEqual(item.status, 0)
        result = await confirm_approval(ApprovalConfirmation(token=card["token"], decision=2), self.admin, self.db)
        self.assertEqual(result.data.status, 2)
        with self.assertRaises(AppException):
            await confirm_approval(ApprovalConfirmation(token=card["token"], decision=1), self.admin, self.db)

    async def test_application_workflow_reuses_laboratory_agent(self):
        draft = ReservationApplicationDraft(lab_keyword="光学实验室", date=self.day,
            start_time=time(10), end_time=time(11))
        with patch.object(application, "extract_conditions", return_value=draft), patch.object(
            rt.laboratory_agent, "run", return_value="光学实验室编号 OPT") as labs:
            reply = await workflow.run([HumanMessage(content="预约光学实验室")],
                db=self.db, user_id=self.student.id, user_role="student")
        self.assertEqual(json.loads(reply)["type"], "reservation_application")
        labs.assert_awaited_once()
        self.assertEqual(await self.db.scalar(select(func.count()).select_from(Reservation)), 0)

    async def test_application_missing_time_stops_before_card(self):
        with patch.object(application, "extract_conditions", return_value=ReservationApplicationDraft(lab_keyword="OPT")), patch.object(
            rt.laboratory_agent, "run", return_value="光学实验室编号 OPT"), patch.object(
            rt.prepare_application, "coroutine") as prepare:
            reply = await workflow.run([HumanMessage(content="预约 OPT")],
                db=self.db, user_id=self.student.id, user_role="student")
        self.assertIn("请补充预约日期、开始时间、结束时间", reply)
        prepare.assert_not_called()

    async def test_approval_real_agent_queries_cancelled_records(self):
        with patch.object(approval_agent.llm_service, "llm", model(
            call("search_approvals", {"status": 3}), AIMessage(content="没有已取消预约。"))):
            result = await workflow.run([HumanMessage(content="查询已取消单据")],
                db=self.db, user_id=self.admin.id, user_role="admin")
        self.assertIn("没有", result)

    async def test_application_cannot_skip_resource_step(self):
        context = self.context(self.student)
        context["resource_consulted"] = False
        reply = await rt.prepare_application.coroutine(runtime=SimpleNamespace(context=context),
            lab_code="OPT", reservation_date=self.day, start_time=time(10), end_time=time(11))
        self.assertIn("请先", reply)
        self.assertEqual(context["cards"], [])

    async def test_conflict_or_closed_lab_never_generates_card(self):
        self.lab.status = 0
        await self.db.commit()
        self.assertIn("未开放", await self.application())

    async def test_supervisor_returns_reservation_card_unchanged(self):
        from services.workflows.supervisor import workflow as supervisor
        from services.workflows.supervisor.agents import supervisor_agent
        card = await self.application()
        with patch.object(supervisor_agent.llm_service, "llm", model(
            call("reservation_workflow", {"request": "申请预约"}))), patch.object(
                workflow, "run", return_value=card):
            events = [event async for event in supervisor.stream([HumanMessage(content="申请预约")],
                db=self.db, user_id=self.student.id, user_role="student")]
        self.assertEqual(events[-1][1]["content"], card)
        self.assertTrue(any(payload.get("stage") == "reservation_workflow" for _, payload in events))
