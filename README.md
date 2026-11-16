# Lab Agent API

智能实验室预约系统后端 API，基于 FastAPI、SQLAlchemy、MySQL 和 Redis 构建，提供用户与实验室管理、用户认证和文件上传接口。

## 技术栈

- Python 3.13+
- FastAPI、Uvicorn
- SQLAlchemy、Alembic
- MySQL（PyMySQL 驱动）
- Redis
- uv（Python 包管理器）

## 环境准备

需要准备 Python 3.13 或更高版本、MySQL，以及 Docker Compose（用于启动 Redis）。项目使用 `uv` 管理依赖；如尚未安装，可参考 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/)。

```bash
uv sync
cp .env.example .env
```

编辑 `.env`，填入本地 MySQL 连接地址和 JWT 密钥。例如：

```dotenv
DATABASE_URL=mysql+pymysql://root:your_password@127.0.0.1:3306/lab_agent
SECRET_KEY=替换为随机生成的长密钥
ACCESS_TOKEN_EXPIRE_MINUTES=30
ALGORITHM=HS256
redis_url=redis://127.0.0.1:6380/0
```

先在 MySQL 中创建 `lab_agent` 数据库（或将 `DATABASE_URL` 指向已有数据库）。`SECRET_KEY` 应使用随机且仅本地保存的值；不要提交 `.env`。

启动 Redis：

```bash
docker compose up -d redis
```

## 数据库迁移

应用已有的 Alembic 迁移：

```bash
uv run alembic upgrade head
```

生成新迁移时，先修改 SQLAlchemy 模型，再执行：

```bash
uv run alembic revision --autogenerate -m "describe_change"
uv run alembic upgrade head
```

生成的迁移需要检查后再提交。

## 启动服务

```bash
uv run python -m uvicorn main:app --app-dir src --reload
```

服务默认运行于 `http://127.0.0.1:8000`。交互式 API 文档：

- Swagger UI：<http://127.0.0.1:8000/docs>
- ReDoc：<http://127.0.0.1:8000/redoc>

## API 概览

所有 API 路由前缀为 `/api/v1`，成功及错误响应使用统一响应结构。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/v1/auth/register` | 注册用户 |
| `POST` | `/api/v1/auth/login` | 登录并获取访问令牌 |
| `POST` | `/api/v1/auth/logout` | 登出当前令牌 |
| `GET` | `/api/v1/user/info` | 获取当前用户资料（需 Bearer Token） |
| `POST` | `/api/v1/user/update` | 更新当前用户资料（需 Bearer Token） |
| `POST` | `/api/v1/user/password` | 修改当前用户密码（需 Bearer Token） |
| `GET` | `/api/v1/user/page` | 管理员分页查询用户及统计 |
| `POST` | `/api/v1/user/create` | 管理员新增用户 |
| `PUT` | `/api/v1/user/{user_id}` | 管理员更新用户 |
| `DELETE` | `/api/v1/user/{user_id}` | 删除已禁用的用户（管理员） |
| `GET` | `/api/v1/lab/page` | 管理员分页查询实验室及统计 |
| `POST` | `/api/v1/lab/create` | 管理员新增实验室 |
| `PUT` | `/api/v1/lab/{lab_id}` | 管理员更新实验室 |
| `DELETE` | `/api/v1/lab/{lab_id}` | 删除已关闭的实验室（管理员） |
| `POST` | `/api/v1/files/upload` | 上传文件或头像（multipart/form-data） |

上传接口接收 `file` 文件字段，可选 `purpose` 字段为 `file` 或 `avatar`。上传后的文件通过 `/uploads/...` 路径访问。

### 实验室管理

实验室管理接口需要管理员 Bearer Token。分页查询支持以下参数：

| 参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `page` | 整数 | `1` | 页码，从 1 开始 |
| `size` | 整数 | `10` | 每页条数，范围 1–100 |
| `keyword` | 字符串 | 无 | 按实验室名称、业务编号或位置模糊搜索 |
| `status` | 整数 | 无 | `0` 查询关闭实验室，`1` 查询开放实验室 |

示例：`GET /api/v1/lab/page?page=1&size=6&keyword=&status=0`

分页响应的 `data` 包含 `total`、`items`、`page`、`size`，以及不受筛选条件影响的全局统计：`global_total`、`open_count`、`closed_count`、`total_capacity`。

新增和更新请求支持 `lab_code`、`name`、`location`、`capacity`、`description`、`img`、`open_time`、`close_time`、`status`。新增时业务编号和名称必填，容量默认为 `0`，状态默认为 `1`。更新为部分更新：未提交的字段保持不变，可空字段传 `null` 时清空。删除接口只允许删除 `status=0` 的关闭实验室；开放中的实验室需先关闭。

## 测试

运行测试：

```bash
PYTHONPATH=src uv run python -m unittest discover -s tests -v
```

## 配置说明

| 变量 | 必填 | 默认值/示例 | 说明 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 是 | `mysql+pymysql://...` | SQLAlchemy 数据库连接 URL |
| `SECRET_KEY` | 是 | 无 | JWT 签名密钥 |
| `ALGORITHM` | 否 | `HS256` | JWT 签名算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `1440` | 访问令牌有效期（分钟） |
| `redis_url` | 否 | `redis://127.0.0.1:6380/0` | Redis 连接 URL |

配置通过 `src/core/config.py` 中的 Pydantic Settings 加载。配置字段名区分大小写；Redis 字段当前为小写 `redis_url`。
