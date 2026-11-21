import unittest
from uuid import uuid4

from pydantic import ValidationError

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from core.database import Base
from core.exceptions import AppException
from core.security import verify_password
from models.user import User
from schemas.user import UserCreateRequest, UserUpdateRequest
from services.user_service import create_user, delete_user, update_managed_user


class UserManagementTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite://')
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def test_create_update_delete(self):
        created = await create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='测试'))
        user = await self.db.get(User, created.id)
        self.assertEqual(user.role, 'student')
        self.assertEqual(user.status, 1)
        self.assertTrue(verify_password('Custom789Pass', user.password))
        with self.assertRaises(AppException):
            await delete_user(self.db, user.id)
        updated = await update_managed_user(self.db, created.id, UserUpdateRequest(role='admin', status=0))
        self.assertEqual(updated.role, 'admin')
        await delete_user(self.db, created.id)
        self.assertIsNone(await self.db.get(User, created.id))

    async def test_conflicts_and_missing_user(self):
        await create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='测试'))
        with self.assertRaises(AppException):
            await create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='重复'))
        with self.assertRaises(AppException):
            await update_managed_user(self.db, uuid4(), UserUpdateRequest(name='测试'))
        with self.assertRaises(AppException):
            await delete_user(self.db, uuid4())

    async def test_create_password_validation(self):
        for password in [None, "short", "abcdefgh", "ABCDEFGH1", "Abcdef12 ", "Abcdef12中文", "A1a" * 8]:
            with self.subTest(password=password), self.assertRaises(ValidationError):
                UserCreateRequest(username="test", name="测试", password=password)
        with self.assertRaises(ValidationError):
            UserCreateRequest(username="test", name="测试")
