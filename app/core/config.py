from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用全局配置，从环境变量 / .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用
    APP_NAME: str = "Meta Service"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = True

    # 服务
    HOST: str = "0.0.0.0"
    PORT: int = 9093

    # 数据库 (SQLite)
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/meta_service.db"
    DATABASE_ECHO: bool = False

    # user-service 对接（JWT 消费方）
    USER_SERVICE_URL: str = "http://localhost:8000"
    JWKS_CACHE_TTL_SECONDS: int = 3600
    ALGORITHM: str = "RS256"

    # 超级用户白名单（兜底路径）
    SUPERUSER_USERNAMES: List[str] = ["superuser"]
    SUPERUSER_USER_IDS: List[int] = []

    # 元数据限额
    MAX_ENTRY_DATA_KEYS: int = 100
    MAX_ENTRY_DATA_DEPTH: int = 5
    MAX_TAGS_PER_ENTRY: int = 20
    MAX_TAG_LENGTH: int = 50
    MAX_VERSION_KEPT: int = 50
    ENTRY_KEY_MAX_LENGTH: int = 255

    # 日志
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/meta_service.log"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024
    LOG_BACKUP_COUNT: int = 5

    # CORS
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:9093"]

    # 日志操作类型
    LOG_OPERATIONS: List[str] = [
        "create",
        "update",
        "delete",
        "soft_delete",
        "restore",
        "hard_delete",
        "rollback",
        "create_version",
    ]

    @field_validator(
        "ALLOWED_ORIGINS",
        "LOG_OPERATIONS",
        "SUPERUSER_USERNAMES",
        "SUPERUSER_USER_IDS",
        mode="before",
    )
    @classmethod
    def _parse_list(cls, v):
        """支持从 .env 读取 JSON 数组字符串。"""
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [item.strip() for item in v.split(",") if item.strip()]
        return v


settings = Settings()
