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
DATABASE_URL=mysql+aiomysql://root:your_password@127.0.0.1:3306/lab_agent
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
uv run python -m alembic upgrade head
```

生成新迁移时，先修改 SQLAlchemy 模型，再执行：

```bash
uv run python -m alembic revision --autogenerate -m "describe_change"
uv run python -m alembic upgrade head
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
| `GET` | `/api/v1/lab/page` | 登录用户分页查询实验室及统计 |
| `GET` | `/api/v1/lab/info?lab_code=LAB-101` | 登录用户按业务编号查询实验室详情 |
| `GET` | `/api/v1/equipment/page` | 登录用户分页查询设备及统计 |
| `POST` | `/api/v1/lab/create` | 管理员新增实验室 |
| `PUT` | `/api/v1/lab/{lab_id}` | 管理员更新实验室 |
| `DELETE` | `/api/v1/lab/{lab_id}` | 删除已关闭的实验室（管理员） |
| `POST` | `/api/v1/files/upload` | 上传文件或头像（multipart/form-data） |

上传接口接收 `file` 文件字段，可选 `purpose` 字段为 `file` 或 `avatar`。上传后的文件保存在后端项目根目录的 `uploads/` 中，通过 `/uploads/...` 路径访问；该目录不纳入 Git。

### 实验室管理

实验室和设备的分页查询、按 `lab_code` 查询实验室详情需要登录用户 Bearer Token，普通用户也可访问；新增、编辑和删除仍需要管理员权限。实验室分页查询支持以下参数：

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
| `DATABASE_URL` | 是 | `mysql+aiomysql://...` | SQLAlchemy 数据库连接 URL |
| `SECRET_KEY` | 是 | 无 | JWT 签名密钥 |
| `ALGORITHM` | 否 | `HS256` | JWT 签名算法 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 否 | `1440` | 访问令牌有效期（分钟） |
| `redis_url` | 否 | `redis://127.0.0.1:6380/0` | Redis 连接 URL |

配置通过 `src/core/config.py` 中的 Pydantic Settings 加载。配置字段名区分大小写；Redis 字段当前为小写 `redis_url`。

## AI 聊天接口

`POST /api/v1/chat`，请求头携带 `Authorization: Bearer <token>`。

```json
{"content": "你好，请介绍一下实验室预约流程"}
```

首次请求省略 `conversation_id`，服务自动创建会话，以消息前 200 个字符作为标题。
继续对话时传入返回的 `data.conversation_id`：

```json
{"conversation_id": "替换为返回的会话 UUID", "content": "需要提前多久预约？"}
```

响应遵循 `BaseResponse`，`data` 包含 `conversation_id`、`user_message` 和
`assistant_message`；两条消息均含 ID、角色、内容和创建时间。
接口为非流式响应，加载该会话全部历史文本作为上下文。纯空白或超过 20000
字符的输入返回 422；会话不存在或不属于当前用户返回 404；模型异常或空回复返回
502，且不保存本轮消息及新建会话。模型连接使用 `LLM_*` 配置。

同一已有会话通过数据库行锁串行处理；等待模型期间会占用数据库连接和行锁，
高并发或超长会话场景后续应增加队列及上下文裁剪。SQLite 不提供同等行锁保证。

### 流式聊天（SSE）

`POST /api/v1/chat/stream` 使用相同的 Bearer Token 和 `ChatRequest` 请求体。
模型层通过 `llm.astream()` 实时读取文本，API 返回 `text/event-stream`：

```text
event: start
data: {"conversation_id":"会话 UUID"}

event: delta
data: {"content":"你好"}

event: delta
data: {"content":"，有什么可以帮你？"}

event: done
data: {"conversation_id":"会话 UUID","user_message":{},"assistant_message":{}}

```

上面的 done 消息对象为简写；实际返回与普通聊天相同的完整消息字段。
`start` 表示开始生成，其会话 ID 尚未持久化；`delta.content` 是增量文本，
前端应依次拼接。只有 `done` 表示完整回复已保存。
失败时发送 `event: error`，数据为 `{"code":5020,"message":"聊天未完成，请稍后重试"}`，
不保存本轮问答；前端应将已显示的部分回复标为未完成。
HTTP 响应头发送前的鉴权、参数和会话权限错误仍使用普通 HTTP 错误响应；
流启动后的错误使用 SSE error 事件。客户端应将未收到 done 的连接结束视为未完成。
客户端中途断开会关闭模型流并回滚未提交数据；若断开发生在事务提交之后，
已提交的消息仍保留，可通过历史查询确认。

```bash
curl -N -X POST http://localhost:8000/api/v1/chat/stream \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"content":"介绍一下实验室预约流程"}'
```

浏览器请使用 `fetch` 的 POST 请求并增量读取响应；原生 `EventSource` 不支持该 POST 请求。
解析 SSE 时需要缓存网络分片，按空行拆分事件，不能假设一次读取就是一个完整事件。


### 实验室 Agent（第一阶段）

普通聊天和 SSE 聊天均经过 LangGraph：

```text
START → route_request → respond_out_of_scope → END
                     ↘ respond_pending      → END
```

- `src/schemas/agent.py`：意图枚举、路由结构化输出。
- `src/services/agent/workflow.py`：State、范围限制 Prompt、节点与条件边。
- `src/services/llm/llm_service.py`：模型分类调用及现有聊天入口适配。
- `route_request` 使用模型的 function calling 结构化输出识别最新请求，并携带历史上下文。
- 范围外请求区分无关问题、不支持的操作和受限能力，由模型生成简短说明；生成失败、空回复或回复过长时使用对应模板兜底。问候、意图不明、尚未实现的业务请求分别返回明确提示。
- 本阶段未接入知识检索、业务工具和 checkpoint，不执行预约或取消操作。
- SSE 事件协议保持不变；分类完成后返回一个公开回复 delta，不输出分类 JSON 或内部分类依据。
- 分类失败仍走现有聊天错误与回滚流程，不退回无限制聊天。

新增测试使用模拟模型验证路由与边界；真实服务商的结构化输出兼容性需配置模型后联调。
