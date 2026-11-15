from redis import Redis

from core.config import settings

# 使用 URL 构造连接池；连接在实际请求时建立，避免模块导入时访问网络。
redis_client = Redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
)
