from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore',
                                      case_sensitive=False,
                                      env_file_encoding="utf-8")

    # 项目元数据
    APP_NAME: str = ""
    APP_VERSION: str = ""
    APP_DESCRIPTION: str = ""
    APP_LICENSE: str = "{}"

    # 应用配置
    APP_ENV: Literal["dev", "pro", "test"] = "dev"
    DEBUG: bool = False

    # Logging
    LOG_LEVEL: str = "info"
    LOG_TO_CONSOLE: bool = True
    LOG_TO_FILE: bool = True
    LOG_FILE_PATH: str = "logs"
    LOG_FILE_MAX_BYTES: int = 10485760  # 10MB
    LOG_FILE_BACKUP_COUNT: int = 10
    LOG_FORMAT: Literal["json", "text", "colored"] = "json"

    # Access Log
    ENABLE_ACCESS_LOG: bool = True
    ACCESS_LOG_PATH: str = "logs/access.log"

    # SQL Log
    ENABLE_SQL_LOG: bool = False
    SQL_LOG_LEVEL: str = "INFO"

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8080

    DB_SERVER: str = ""
    DB_PORT: int = 0
    DB_USER: str = ""
    DB_PASSWORD: str = ""
    DB_NAME: str = ""

    # 飞书集成
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+psycopg2",
            username=self.DB_USER,
            password=self.DB_PASSWORD,
            host=self.DB_SERVER,
            port=self.DB_PORT,
            path=self.DB_NAME,
        )

    @property
    def parsed_license(self) -> dict:
        import json
        try:
            return json.loads(self.APP_LICENSE)
        except json.JSONDecodeError:
            return {}


# 创建全局配置实例
settings = Settings()


# 导出便捷函数
@lru_cache
def get_settings() -> Settings:
    return Settings()
