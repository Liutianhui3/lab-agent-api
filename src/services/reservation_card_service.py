"""Signed, user-bound reservation confirmation payloads."""
from datetime import UTC, datetime, timedelta
import jwt
from typing import Literal
from pydantic import BaseModel, ConfigDict
from core.config import settings
from core.exceptions import AppException


class CardConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class ApprovalConfirmation(CardConfirmation):
    decision: Literal[1, 2]


def sign_card(user_id, kind, data):
    return jwt.encode({"sub": str(user_id), "purpose": "reservation_card", "kind": kind,
        "data": data, "exp": datetime.now(UTC) + timedelta(minutes=15)},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def read_card(token, user_id, kind):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
                             options={"require": ["sub", "purpose", "kind", "data", "exp"]})
        if payload["sub"] != str(user_id) or payload["purpose"] != "reservation_card" or payload["kind"] != kind:
            raise ValueError("invalid card")
        return payload["data"]
    except (jwt.PyJWTError, ValueError) as exc:
        raise AppException(code=4000, message="确认卡片无效或已过期，请重新生成", status_code=400) from exc
