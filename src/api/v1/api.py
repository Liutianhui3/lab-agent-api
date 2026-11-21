"""统一挂载业务模块路由。"""

from fastapi import APIRouter

from api.v1.endpoints.auth import router as auth_router
from api.v1.endpoints.chat import router as chat_router
from api.v1.endpoints.conversation import router as conversation_router
from api.v1.endpoints.equipment import router as equipment_router
from api.v1.endpoints.files import router as files_router
from api.v1.endpoints.lab import router as lab_router
from api.v1.endpoints.reservation import router as reservation_router
from api.v1.endpoints.user import router as user_router

api_router = APIRouter(prefix="/api/v1", tags=["API V1"])

api_router.include_router(auth_router)
api_router.include_router(user_router)
api_router.include_router(lab_router)
api_router.include_router(equipment_router)
api_router.include_router(reservation_router)
api_router.include_router(files_router)
api_router.include_router(conversation_router)
api_router.include_router(chat_router)
