"""Application settings using Pydantic."""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    format: str = Field(default="json", validation_alias="LOG_FORMAT")
    file_path: str = Field(default="", validation_alias="LOG_FILE")


class APISettings(BaseSettings):
    """API configuration."""
    host: str = Field(default="0.0.0.0", validation_alias="API_HOST")
    port: int = Field(default=8000, validation_alias="API_PORT")
    prefix: str = Field(default="/api/v1", validation_alias="API_PREFIX")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        validation_alias="API_ALLOWED_ORIGINS",
    )


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    url: str = Field(default="", validation_alias="DATABASE_URL")
    echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")


class RedisSettings(BaseSettings):
    """Redis configuration."""
    url: str = Field(default="redis://localhost:6379", validation_alias="REDIS_URL")
    max_connections: int = Field(default=10, validation_alias="REDIS_MAX_CONNECTIONS")


class Settings(BaseSettings):
    """Application settings."""
    debug: bool = Field(default=False, validation_alias="DEBUG")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    
    # Sub-settings
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    api: APISettings = Field(default_factory=APISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )
