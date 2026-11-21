from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import update

from core.database import SessionLocal
from models.reservation import Reservation


async def cancel_expired_reservations() -> None:
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

    async with SessionLocal.begin() as db:
        await db.execute(
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
