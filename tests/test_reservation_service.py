import unittest
from datetime import date, time, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from pydantic import ValidationError

from core.database import Base
from core.exceptions import AppException
from models.equipment import Equipment
from models.lab import Lab
from models.reservation import Reservation
from models.user import User
from schemas.reservation import ReservationCreateRequest
from services.reservation_service import create_reservation


class ReservationServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.user = User(username="booker", password="hash", name="预约人")
        self.lab = Lab(lab_code="L1", name="实验室", open_time=time(8), close_time=time(18))
        self.db.add_all([self.user, self.lab])
        self.db.flush()
        self.equipment = Equipment(code="E1", name="设备", lab_id=self.lab.id)
        self.other = Equipment(code="E2", name="其他设备", lab_id=self.lab.id)
        self.db.add_all([self.equipment, self.other])
        self.db.commit()
        self.day = date.today() + timedelta(days=7)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def request(self, **updates):
        data = dict(lab_id=self.lab.id, date=self.day, start_time=time(9), end_time=time(10))
        data.update(updates)
        return ReservationCreateRequest(**data)

    def create(self, **updates):
        return create_reservation(self.db, self.user, self.request(**updates))

    def reject(self, **updates):
        with self.assertRaises(AppException):
            self.create(**updates)

    def test_create_lab_and_equipment(self):
        reservation = self.create()
        self.assertEqual(reservation.status, 0)
        self.assertEqual(reservation.user_id, self.user.id)
        self.assertIsNone(reservation.equipment_id)
        equipment_booking = self.create(equipment_id=self.equipment.id, start_time=time(10), end_time=time(11))
        self.assertEqual(equipment_booking.equipment_id, self.equipment.id)

    def test_invalid_times_and_dates(self):
        for changes in (
            dict(start_time=time(10)),
            dict(start_time=time(11)),
            dict(start_time=time(7)),
            dict(end_time=time(19)),
            dict(start_time="09:00:00+08:00"),
        ):
            with self.subTest(changes=changes):
                self.reject(**changes)
        self.assertIsNone(self.db.scalar(select(Reservation.id)))

    def test_past_date_rejected_by_request_schema(self):
        with self.assertRaises(ValidationError):
            self.request(date=date.today() - timedelta(days=1))

    def test_closed_lab(self):
        self.lab.status = 0
        self.db.commit()
        self.reject()

    def test_missing_resources(self):
        self.reject(lab_id=999)
        self.reject(equipment_id=999)

    def test_unavailable_equipment(self):
        self.equipment.status = 0
        self.db.commit()
        self.reject(equipment_id=self.equipment.id)
        self.equipment.status = 1
        self.equipment.quantity = 0
        self.db.commit()
        self.reject(equipment_id=self.equipment.id)

    def test_equipment_in_another_lab(self):
        lab = Lab(lab_code="L2", name="其他实验室")
        self.db.add(lab)
        self.db.flush()
        self.equipment.lab_id = lab.id
        self.db.commit()
        self.reject(equipment_id=self.equipment.id)

    def test_lab_blocks_equipment(self):
        self.create()
        self.reject(equipment_id=self.equipment.id)

    def test_equipment_blocks_lab_and_same_equipment(self):
        self.create(equipment_id=self.equipment.id)
        self.reject()
        self.reject(equipment_id=self.equipment.id)
        self.create(equipment_id=self.other.id)

    def test_conflict_statuses(self):
        reservation = self.create()
        reservation.status = 1
        self.db.commit()
        self.reject()
        reservation.status = 2
        self.db.commit()
        replacement = self.create()
        replacement.status = 3
        self.db.commit()
        self.create()

    def test_other_day_and_opening_boundaries(self):
        self.create(start_time=time(8), end_time=time(18))
        self.create(date=self.day + timedelta(days=1))

    def test_disabled_user(self):
        self.user.status = 0
        self.db.commit()
        self.reject()

    def test_all_user_roles_can_reserve(self):
        for index, role in enumerate(("student", "admin")):
            with self.subTest(role=role):
                self.user.role = role
                self.db.commit()
                self.create(date=self.day + timedelta(days=index))

    def test_unconfigured_opening_hours(self):
        self.lab.open_time = None
        self.lab.close_time = None
        self.db.commit()
        self.create(start_time=time(1), end_time=time(23))
