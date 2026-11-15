"""Profile contracts against an isolated SQLite database and temporary uploads."""
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.deps import get_current_user
from core.database import Base, get_db
from main import app
from models.user import User


async def request(path, payload=None, raw=None, content_type="application/json"):
    body = raw if raw is not None else json.dumps(payload or {}).encode()
    events = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(event):
        events.append(event)

    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "path": path,
               "raw_path": path.encode(), "query_string": b"", "root_path": "", "scheme": "http", "server": ("test", 80),
               "client": ("test", 1234), "headers": [(b"content-type", content_type.encode())]}, receive, send)
    status = next(event["status"] for event in events if event["type"] == "http.response.start")
    data = b"".join(event.get("body", b"") for event in events if event["type"] == "http.response.body")
    return status, json.loads(data)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(username="profile-test", password="hash", name="原姓名", role="student", email="original@example.test", status=1)
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        app.dependency_overrides[get_current_user] = lambda: self.user
        app.dependency_overrides[get_db] = lambda: self.db

    def tearDown(self):
        app.dependency_overrides.clear()
        self.db.close()
        self.engine.dispose()

    def post(self, payload):
        return asyncio.run(request("/api/v1/user/update", payload))

    def test_update_returns_complete_user_and_optional_contacts_can_clear(self):
        status, body = self.post({"name": "  新姓名  ", "email": None, "phone": None, "avatar": "/uploads/test.png"})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["name"], "新姓名")
        self.assertEqual(body["data"]["username"], "profile-test")
        self.assertEqual(body["data"]["role"], "student")
        self.assertIsNone(body["data"]["email"])
        self.assertNotIn("password", body["data"])
        self.db.refresh(self.user)
        self.assertEqual(self.user.avatar, "/uploads/test.png")

    def test_identity_cannot_change(self):
        for field, value in [("role", "admin"), ("id", str(self.user.id))]:
            with self.subTest(field=field):
                self.assertEqual(self.post({field: value})[0], 422)
        self.assertEqual(self.user.role, "student")

    def test_username_edit_validation_and_conflict(self):
        status, body = self.post({"username": "  renamed-user  "})
        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["username"], "renamed-user")
        self.assertEqual(body["data"]["id"], str(self.user.id))
        for value in [None, " ", "x" * 51]:
            self.assertEqual(self.post({"username": value})[0], 422)
        self.db.add(User(username="taken", password="hash", name="其他用户", role="student", status=1))
        self.db.commit()
        status, body = self.post({"username": "taken"})
        self.assertEqual(status, 409)
        self.assertEqual(body["message"], "用户名已被使用")
        self.assertEqual(self.user.username, "renamed-user")

    def test_invalid_fields_and_duplicate_email(self):
        for payload in [{"name": " "}, {"name": None}, {"email": "bad"}, {"phone": "bad"}, {"avatar": "javascript:alert(1)"}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.post(payload)[0], 422)
        self.db.add(User(username="other", password="hash", name="其他用户", email="taken@example.test", role="student", status=1))
        self.db.commit()
        self.assertEqual(self.post({"email": "taken@example.test"})[0], 409)
        self.assertEqual(self.user.email, "original@example.test")

    def test_auth_required(self):
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.post({"name": "测试"})[0], 401)

    def test_avatar_upload_contract_and_validation(self):
        def upload(content, filename="avatar.png", mime="image/png", purpose="avatar"):
            boundary = "profile-test-boundary"
            raw = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\n{purpose}\r\n"
                   f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
            return asyncio.run(request("/api/v1/files/upload", raw=raw, content_type=f"multipart/form-data; boundary={boundary}"))
        with tempfile.TemporaryDirectory() as directory, patch("services.file_service.UPLOAD_DIR", Path(directory)):
            status, body = upload(b"\x89PNG\r\n\x1a\n" + b"data")
            self.assertEqual(status, 200)
            self.assertTrue(body["data"]["url"].startswith("/uploads/"))
            self.assertTrue((Path(directory) / body["data"]["disk_name"]).exists())
            self.assertEqual(upload(b"not png")[0], 415)
            self.assertEqual(upload(b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024))[0], 413)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            # Preserve the existing general-purpose file endpoint.
            self.assertEqual(upload(b"document", "test.docx", "application/octet-stream", "file")[0], 200)


if __name__ == "__main__":
    unittest.main()
