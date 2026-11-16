"""Role filtering contracts against an isolated SQLite database."""
import asyncio
import json
import unittest
from urllib.parse import urlencode

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.deps import get_current_admin
from core.database import Base, get_db
from main import app
from models.user import User
from services.user_service import get_user_page


class UserFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool,
                                    connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.admin = User(username="admin-one", password="hash", name="Shared admin",
                          role="admin", status=1)
        self.db.add_all([
            self.admin,
            User(username="admin-two", password="hash", name="Second admin", role="admin", status=0),
            User(username="student-one", password="hash", name="Shared student", role="student", status=1),
            User(username="student-two", password="hash", name="Other student", role="student", status=0),
        ])
        self.db.commit()
        app.dependency_overrides[get_current_admin] = lambda: self.admin
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def test_roles_filter_both_total_and_items_before_pagination(self):
        self.assertEqual(get_user_page(self.db, 1, 10).total, 4)
        for role in ("admin", "student"):
            first = get_user_page(self.db, 1, 1, role=role)
            second = get_user_page(self.db, 2, 1, role=role)
            self.assertEqual(first.total, 2)
            self.assertEqual(second.total, 2)
            self.assertEqual([first.items[0].role, second.items[0].role], [role, role])
            self.assertNotEqual(first.items[0].id, second.items[0].id)

    def test_role_and_keyword_are_combined_and_stats_stay_global(self):
        result = get_user_page(self.db, 1, 10, keyword=" Shared ", role="student")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].username, "student-one")
        self.assertEqual(get_user_page(self.db, 1, 10, keyword="admin-one", role="student").total, 0)
        self.assertEqual((result.admin_count, result.disabled_count, result.global_total), (2, 2, 4))

    async def get_page(self, **params):
        events = []
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}
        async def send(event):
            events.append(event)
        path = "/api/v1/user/page"
        await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                   "method": "GET", "path": path, "raw_path": path.encode(),
                   "query_string": urlencode(params).encode(), "root_path": "", "scheme": "http",
                   "server": ("test", 80), "client": ("test", 1234), "headers": []}, receive, send)
        status = next(event["status"] for event in events if event["type"] == "http.response.start")
        body = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
        return status, json.loads(body)

    def test_http_role_validation_and_filter_forwarding(self):
        status, body = asyncio.run(self.get_page(role="student", keyword="Shared"))
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["items"][0]["role"], "student")
        self.assertEqual(
            (body["data"]["admin_count"], body["data"]["disabled_count"], body["data"]["global_total"]),
            (2, 2, 4),
        )
        for invalid in ("owner", "", "ADMIN"):
            with self.subTest(role=invalid):
                self.assertEqual(asyncio.run(self.get_page(role=invalid))[0], 422)


if __name__ == "__main__":
    unittest.main()
