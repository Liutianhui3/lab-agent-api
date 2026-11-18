from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# -------------------------------------------------------------
# 关键点 1：导入你的数据库 Base 以及环境变量配置
# -------------------------------------------------------------
from core.config import settings
from core.database import Base
from models.equipment import Equipment  # noqa: F401 -- 注册 equipments 表
from models.reservation import Reservation  # noqa: F401 -- 注册 reservations 表
from models.lab import Lab  # noqa: F401 -- 注册 labs 表
from models.user import User  # noqa: F401 -- 导入模型，将 users 表注册到 Base.metadata

# -------------------------------------------------------------
# 关键点 2：显式导入你的所有 Model
# （注意：必须在这里导入一次，Base.metadata 才能收集到它们的表结构）
# -------------------------------------------------------------

# 后续如果加了新表（如 item.py），也需要在这里 import 进来：
# from models.item import Item

# Alembic Config 对象，用于读取 alembic.ini 配置
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# -------------------------------------------------------------
# 关键点 3：将 target_metadata 指向你的 Base.metadata
# -------------------------------------------------------------
target_metadata = Base.metadata

# -------------------------------------------------------------
# 关键点 4：动态注入数据库连接 URL
# （直接从你的 pydantic-settings 配置中读取，无需写死在 alembic.ini 里）
# -------------------------------------------------------------
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))


def run_migrations_offline() -> None:
    """以离线模式运行迁移（只生成 SQL 脚本，不连接数据库）"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以在线模式运行迁移（直接连接数据库并执行变更）"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
