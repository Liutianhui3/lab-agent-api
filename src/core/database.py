from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings

# Engine 管理连接池；调用 connect() 或实际执行查询时才连接数据库。
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 5},
)

SessionLocal = sessionmaker(bind=engine)


def get_db() -> Generator[Session]:
    # yield 将会话交给接口，退出 with 时自动关闭；未提交事务会被回滚。
    with SessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    """所有 ORM 模型共用的基类，用于收集表结构定义。"""
