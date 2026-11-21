from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # 后端项目根目录，不依赖启动位置


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str = Field(min_length=1, repr=False)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440, gt=0)

    redis_url: str = "redis://127.0.0.1:6380/0"

    LLM_API_KEY: str
    LLM_BASE_URL: str
    LLM_MODEL: str = "qwen-plus"

    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096
    LLM_TIMEOUT: int = 60
    LLM_MAX_RETRIES: int = 2

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)  # 确保上传目录存在
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 最大上传文件大小，单位字节（100MB）

ALLOWED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".pdf",
    ".webp",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".zip",
}
