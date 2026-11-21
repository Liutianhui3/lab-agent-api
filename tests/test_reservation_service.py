import unittest
from datetime import date, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from pydantic import ValidationError

from core.database import Base
from core.exceptions import AppException
from models.equipment import Equipment
from models.lab import Lab
from models.reservation import Reservation
from models.user import User
from schemas.reservation import ReservationCreateRequest
from services.reservation_service import create_reservation


class ReservationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.db = AsyncSession(self.engine, expire_on_commit=False)
        self.user = User(username="booker", password="hash", name="预约人")
        self.lab = Lab(lab_code="L1", name="实验室", open_time=time(8), close_time=time(18))
        self.db.add_all([self.user, self.lab])
        await self.db.flush()
        self.equipment = Equipment(code="E1", name="设备", lab_id=self.lab.id)
        self.other = Equipment(code="E2", name="其他设备", lab_id=self.lab.id)
        self.db.add_all([self.equipment, self.other])
        await self.db.commit()
        self.day = date.today() + timedelta(days=7)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    def request(self, **updates):
        data = dict(lab_id=self.lab.id, date=self.day, start_time=time(9), end_time=time(10))
        data.update(updates)
        return ReservationCreateRequest(**data)

    async def create(self, **updates):
        return await create_reservation(self.db, self.user, self.request(**updates))

    async def reject(self, **updates):
        with self.assertRaises(AppException):
            await self.create(**updates)
        for item in (self.user, self.lab, self.equipment, self.other):
            await self.db.refresh(item)

    async def test_create_lab_and_equipment(self):
        reservation = await self.create()
        self.assertEqual(reservation.status, 0)
        self.assertEqual(reservation.user_id, self.user.id)
        self.assertIsNone(reservation.equipment_id)
        equipment_booking = await self.create(equipment_id=self.equipment.id, start_time=time(10), end_time=time(11))
        self.assertEqual(equipment_booking.equipment_id, self.equipment.id)

    async def test_invalid_times_and_dates(self):
        for changes in (
            dict(start_time=time(10)),
            dict(start_time=time(11)),
            dict(start_time=time(7)),
            dict(end_time=time(19)),
            dict(start_time="09:00:00+08:00"),
        ):
            with self.subTest(changes=changes):
                await self.reject(**changes)
        self.assertIsNone(await self.db.scalar(select(Reservation.id)))

    async def test_past_date_rejected_by_request_schema(self):
        with self.assertRaises(ValidationError):
            self.request(date=date.today() - timedelta(days=1))

    async def test_closed_lab(self):
        self.lab.status = 0
        await self.db.commit()
        await self.reject()

    async def test_missing_resources(self):
        await self.reject(lab_id=999)
        await self.reject(equipment_id=999)

    async def test_unavailable_equipment(self):
        self.equipment.status = 0
        await self.db.commit()
        await self.reject(equipment_id=self.equipment.id)
        self.equipment.status = 1
        self.equipment.quantity = 0
        await self.db.commit()
        await self.reject(equipment_id=self.equipment.id)

    async def test_equipment_in_another_lab(self):
        lab = Lab(lab_code="L2", name="其他实验室")
        self.db.add(lab)
        await self.db.flush()
        self.equipment.lab_id = lab.id
        await self.db.commit()
        await self.reject(equipment_id=self.equipment.id)

    async def test_lab_blocks_equipment(self):
        await self.create()
        await self.reject(equipment_id=self.equipment.id)

    async def test_equipment_blocks_lab_and_same_equipment(self):
        await self.create(equipment_id=self.equipment.id)
        await self.reject()
        await self.reject(equipment_id=self.equipment.id)
        await self.create(equipment_id=self.other.id)

    async def test_conflict_statuses(self):
        reservation = await self.create()
        reservation.status = 1
        await self.db.commit()
        await self.reject()
        reservation.status = 2
        await self.db.commit()
        replacement = await self.create()
        replacement.status = 3
        await self.db.commit()
        await self.create()

    async def test_other_day_and_opening_boundaries(self):
        await self.create(start_time=time(8), end_time=time(18))
        await self.create(date=self.day + timedelta(days=1))

    async def test_disabled_user(self):
        self.user.status = 0
        await self.db.commit()
        await self.reject()

    async def test_all_user_roles_can_reserve(self):
        for index, role in enumerate(("student", "admin")):
            with self.subTest(role=role):
                self.user.role = role
                await self.db.commit()
                await self.create(date=self.day + timedelta(days=index))

    async def test_unconfigured_opening_hours(self):
        self.lab.open_time = None
        self.lab.close_time = None
        await self.db.commit()
        await self.create(start_time=time(1), end_time=time(23))
