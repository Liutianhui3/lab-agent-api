import unittest
import json
from uuid import uuid4
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base
from api.deps import get_current_admin, get_current_user
from core.database import get_db
from main import app
from models.user import User
from models.lab import Lab
from models.equipment import Equipment
from core.exceptions import AppException
from schemas.lab import (
    LabCreateRequest,
    LabPageData,
    LabPageResponse,
    LabResponse,
    LabUpdateRequest,
)
from services.lab_service import create_lab, delete_lab, get_lab_page, update_lab


class LabPageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(
            "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(self.engine, expire_on_commit=False)
        self.db.add_all(
            [
                Lab(id=1, lab_code="LAB-101", name="纳米实验室", location="A-101", capacity=16, status=1),
                Lab(id=2, lab_code="LAB-102", name="光学实验室", location="B-102", capacity=8, status=1),
                Lab(id=3, lab_code="LAB-103", name="材料中心", location="C-103", capacity=6, status=0),
            ]
        )
        await self.db.commit()
        self.admin = User(
            id=uuid4(),
            username="lab-admin",
            password="hash",
            name="管理员",
            role="admin",
            status=1,
        )
        self.db.add(self.admin)
        await self.db.commit()
        app.dependency_overrides[get_current_admin] = lambda: self.admin
        app.dependency_overrides[get_current_user] = lambda: self.admin
        app.dependency_overrides[get_db] = lambda: self.db

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        await self.db.close()
        await self.engine.dispose()

    async def test_status_zero_query_parameter(self):
        async def request():
            events = []

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(event):
                events.append(event)

            path = "/api/v1/lab/page"
            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "GET",
                    "path": path,
                    "raw_path": path.encode(),
                    "query_string": urlencode({"page": 1, "size": 6, "keyword": "", "status": 0}).encode(),
                    "root_path": "",
                    "scheme": "http",
                    "server": ("test", 80),
                    "client": ("test", 1234),
                    "headers": [],
                },
                receive,
                send,
            )
            status_code = next(e["status"] for e in events if e["type"] == "http.response.start")
            body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
            return status_code, json.loads(body)

        status_code, body = await request()
        self.assertEqual(status_code, 200)
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["items"][0]["status"], 0)

    async def test_page_filter_and_global_stats(self):
        result = await get_lab_page(self.db, page=1, size=1, keyword="LAB", status=1)
        self.assertEqual((result.total, len(result.items)), (2, 1))
        self.assertEqual(
            (result.global_total, result.open_count, result.closed_count, result.total_capacity),
            (3, 2, 1, 30),
        )
        self.assertEqual((await get_lab_page(self.db, 1, 10, keyword="材料")).items[0].id, 3)

    async def test_empty_result_keeps_global_stats_and_schema_inheritance(self):
        result = await get_lab_page(self.db, 1, 10, keyword="missing")
        self.assertEqual(result.total, 0)
        self.assertEqual((result.global_total, result.total_capacity), (3, 30))
        self.assertTrue(issubclass(LabPageData, __import__("schemas.response", fromlist=["PageData"]).PageData))
        self.assertTrue(issubclass(LabPageResponse, __import__("schemas.response", fromlist=["BaseResponse"]).BaseResponse))
        self.assertEqual(LabPageResponse[LabResponse](data=result).data.total, 0)

    async def test_create_update_and_closed_only_delete(self):
        created = await create_lab(
            self.db,
            LabCreateRequest(lab_code="LAB-104", name="新实验室", capacity=12),
        )
        self.assertEqual((created.status, created.capacity), (1, 12))
        updated = await update_lab(
            self.db,
            created.id,
            LabUpdateRequest(name="更新实验室", location="D-104", status=0),
        )
        self.assertEqual((updated.name, updated.location, updated.status), ("更新实验室", "D-104", 0))
        await delete_lab(self.db, created.id)
        self.assertIsNone(await self.db.get(Lab, created.id))

        with self.assertRaises(AppException) as error:
            await delete_lab(self.db, 1)
        self.assertEqual(error.exception.message, "只有关闭状态的实验室才允许删除")

    async def test_cannot_delete_closed_lab_with_equipment(self):
        self.db.add(
            Equipment(code="EQ-LAB-103", name="关联设备", lab_id=3, quantity=1, status=1)
        )
        await self.db.commit()

        with self.assertRaises(AppException) as error:
            await delete_lab(self.db, 3)

        self.assertEqual(error.exception.message, "实验室仍关联设备，无法删除")
        self.assertIsNotNone(await self.db.get(Lab, 3))

    async def test_duplicate_code_and_missing_lab(self):
        with self.assertRaises(AppException):
            await create_lab(
                self.db,
                LabCreateRequest(lab_code="LAB-101", name="重复编号"),
            )
        with self.assertRaises(AppException):
            await update_lab(self.db, 999, LabUpdateRequest(name="不存在"))
        with self.assertRaises(AppException):
            await delete_lab(self.db, 999)


if __name__ == "__main__":
    unittest.main()
