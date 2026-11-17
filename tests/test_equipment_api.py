import asyncio
import json
import unittest
from uuid import uuid4
from urllib.parse import urlencode

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.deps import get_current_admin, get_current_user
from core.database import Base, get_db
from core.exceptions import AppException
from main import app
from models.equipment import Equipment
from models.lab import Lab
from models.user import User
from schemas.equipment import EquipmentCreateRequest, EquipmentUpdateRequest
from services.equipment_service import (
    create_equipment,
    delete_equipment,
    get_equipment_page,
    update_equipment,
)


class EquipmentApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all(
            [
                Lab(id=1, lab_code="LAB-101", name="纳米实验室", capacity=10, status=1),
                Lab(id=2, lab_code="LAB-102", name="光学实验室", capacity=8, status=1),
            ]
        )
        self.db.flush()
        self.db.add_all(
            [
                Equipment(id=1, code="EQ-101", name="电子显微镜", lab_id=1, quantity=2, status=1),
                Equipment(id=2, code="EQ-102", name="光谱仪", lab_id=1, quantity=1, status=0),
                Equipment(id=3, code="EQ-201", name="离心机", lab_id=2, quantity=4, status=1),
            ]
        )
        self.admin = User(
            id=uuid4(), username="equipment-admin", password="hash", name="管理员", role="admin", status=1
        )
        self.db.add(self.admin)
        self.db.commit()
        app.dependency_overrides[get_current_admin] = lambda: self.admin
        app.dependency_overrides[get_current_user] = lambda: self.admin
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def _request(self, method, path, query=None, body=None):
        async def run():
            events = []
            body_bytes = json.dumps(body).encode() if body is not None else b""
            received = False

            async def receive():
                nonlocal received
                if received:
                    return {"type": "http.request", "body": b"", "more_body": False}
                received = True
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            async def send(event):
                events.append(event)

            raw_path = path.encode()
            await app(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": method,
                    "path": path,
                    "raw_path": raw_path,
                    "query_string": urlencode(query or {}).encode(),
                    "root_path": "",
                    "scheme": "http",
                    "server": ("test", 80),
                    "client": ("test", 1234),
                    "headers": [(b"content-type", b"application/json")],
                },
                receive,
                send,
            )
            status_code = next(e["status"] for e in events if e["type"] == "http.response.start")
            response_body = b"".join(
                e.get("body", b"") for e in events if e["type"] == "http.response.body"
            )
            return status_code, json.loads(response_body)

        return asyncio.run(run())

    def test_admin_page_endpoint_filters_and_returns_global_stats(self):
        status_code, body = self._request(
            "GET", "/api/v1/equipment/page", {"page": 1, "size": 1, "lab_id": 1, "status": 1}
        )
        self.assertEqual(status_code, 200)
        self.assertEqual((body["data"]["total"], len(body["data"]["items"])), (1, 1))
        self.assertEqual(
            (body["data"]["global_total"], body["data"]["normal_count"],
             body["data"]["maintenance_count"], body["data"]["total_quantity"]),
            (3, 2, 1, 7),
        )

    def test_student_queries_and_admin_only_mutations(self):
        del app.dependency_overrides[get_current_admin]
        student = User(
            id=uuid4(), username="student", password="hash", name="学生", role="student", status=1
        )
        app.dependency_overrides[get_current_user] = lambda: student
        for path in ("/api/v1/lab/page", "/api/v1/equipment/page"):
            status_code, _ = self._request("GET", path)
            self.assertEqual(status_code, 200)

        status_code, body = self._request("GET", "/api/v1/lab/info", {"lab_code": "LAB-101"})
        self.assertEqual(status_code, 200)
        self.assertEqual(body["data"]["labCode"], "LAB-101")
        status_code, _ = self._request("GET", "/api/v1/lab/info", {"lab_code": "missing"})
        self.assertEqual(status_code, 404)
        status_code, _ = self._request("GET", "/api/v1/lab/info")
        self.assertEqual(status_code, 422)

        for resource in ("lab", "equipment"):
            for method, suffix, body in (
                ("POST", "create", {}), ("PUT", "1", {}), ("DELETE", "1", None)
            ):
                status_code, _ = self._request(method, f"/api/v1/{resource}/{suffix}", body=body)
                self.assertEqual(status_code, 403)

        del app.dependency_overrides[get_current_user]
        for path in ("/api/v1/lab/page", "/api/v1/equipment/page", "/api/v1/lab/info"):
            status_code, _ = self._request("GET", path, {"lab_code": "LAB-101"})
            self.assertEqual(status_code, 401)

    def test_create_update_delete_and_validation_errors(self):
        created = create_equipment(
            self.db,
            EquipmentCreateRequest(code="EQ-301", name="新设备", lab_id=2, quantity=3),
        )
        self.assertEqual((created.quantity, created.status), (3, 1))
        updated = update_equipment(
            self.db, created.id, EquipmentUpdateRequest(name="更新设备", status=0)
        )
        self.assertEqual((updated.name, updated.status), ("更新设备", 0))
        delete_equipment(self.db, created.id)
        self.assertIsNone(self.db.get(Equipment, created.id))

        with self.assertRaises(AppException):
            create_equipment(
                self.db, EquipmentCreateRequest(code="EQ-101", name="重复编号", lab_id=1)
            )
        with self.assertRaises(AppException):
            create_equipment(
                self.db, EquipmentCreateRequest(code="EQ-401", name="无效实验室", lab_id=999)
            )
        with self.assertRaises(AppException):
            delete_equipment(self.db, 999)

    def test_delete_endpoint_and_admin_dependency(self):
        status_code, body = self._request("DELETE", "/api/v1/equipment/1")
        self.assertEqual((status_code, body["message"]), (200, "删除成功"))
        app.dependency_overrides.clear()
        status_code, _ = self._request("GET", "/api/v1/equipment/page")
        self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
