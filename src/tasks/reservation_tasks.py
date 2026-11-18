from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import update

from core.database import SessionLocal
from models.reservation import Reservation


def cancel_expired_reservations() -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

    with SessionLocal() as db:
        db.execute(
            update(Reservation)
            .where(
                Reservation.status == 0,
                (
                    (Reservation.date < now.date())
                    | (
                        (Reservation.date == now.date())
                        & (Reservation.end_time < now.time())
                    )
                ),
            )
            .values(status=3)
        )
        db.commit()
