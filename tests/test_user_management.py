import unittest
from uuid import uuid4

from pydantic import ValidationError

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.database import Base
from core.exceptions import AppException
from core.security import verify_password
from models.user import User
from schemas.user import UserCreateRequest, UserUpdateRequest
from services.user_service import create_user, delete_user, update_managed_user


class UserManagementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_create_update_delete(self):
        created = create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='测试'))
        user = self.db.get(User, created.id)
        self.assertEqual(user.role, 'student')
        self.assertEqual(user.status, 1)
        self.assertTrue(verify_password('Custom789Pass', user.password))
        with self.assertRaises(AppException):
            delete_user(self.db, user.id)
        updated = update_managed_user(self.db, user.id, UserUpdateRequest(role='admin', status=0))
        self.assertEqual(updated.role, 'admin')
        delete_user(self.db, user.id)
        self.assertIsNone(self.db.get(User, user.id))

    def test_conflicts_and_missing_user(self):
        create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='测试'))
        with self.assertRaises(AppException):
            create_user(self.db, UserCreateRequest(password='Custom789Pass', username='test', name='重复'))
        with self.assertRaises(AppException):
            update_managed_user(self.db, uuid4(), UserUpdateRequest(name='测试'))
        with self.assertRaises(AppException):
            delete_user(self.db, uuid4())

    def test_create_password_validation(self):
        for password in [None, "short", "abcdefgh", "ABCDEFGH1", "Abcdef12 ", "Abcdef12中文", "A1a" * 8]:
            with self.subTest(password=password), self.assertRaises(ValidationError):
                UserCreateRequest(username="test", name="测试", password=password)
        with self.assertRaises(ValidationError):
            UserCreateRequest(username="test", name="测试")
