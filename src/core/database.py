from collections.abc import AsyncIterator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

# Engine 管理连接池；调用 connect() 或实际执行查询时才连接数据库。
database_url = make_url(settings.DATABASE_URL)
if database_url.drivername in {"mysql", "mysql+pymysql"}:
    database_url = database_url.set(drivername="mysql+aiomysql")

engine = create_async_engine(
    database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    # yield 将会话交给接口，退出 with 时自动关闭；未提交事务会被回滚。
    async with SessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    """所有 ORM 模型共用的基类，用于收集表结构定义。"""
