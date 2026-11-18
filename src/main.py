from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.v1.api import api_router
from core.config import UPLOAD_DIR
from core.exceptions import register_exception_handlers
from tasks.reservation_tasks import cancel_expired_reservations

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        cancel_expired_reservations,
        trigger="interval",
        hours=12,
        id="cancel-expired-reservations",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title="My FastAPI App", lifespan=lifespan)

# ==================== 配置 CORS 跨域 ====================
# 实际企业项目中，origins 通常会通过 pydantic-settings 从环境变量或配置文件读取
origins = [
    "http://localhost:3800",  # Vite / Vue 默认开发地址
    # 生产环境前端域名后续添加
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 允许访问的源列表（生产环境切忌盲目用 ["*"]）
    allow_credentials=True,  # 允许携带 Cookie / Authorization 凭证
    allow_methods=["*"],  # 允许的 HTTP 方法 (GET, POST, PUT, DELETE 等)
    allow_headers=["*"],  # 允许的请求头 (如 Authorization, Content-Type 等)
)

app.include_router(api_router)

# 注册全局异常处理器
register_exception_handlers(app)

# 挂载静态文件目录
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
