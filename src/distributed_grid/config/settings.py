"""Application settings using Pydantic."""

from __future__ import annotations

from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")
    file_path: str = Field(default="", env="LOG_FILE")


class APISettings(BaseSettings):
    """API configuration."""
    host: str = Field(default="0.0.0.0", env="API_HOST")
    port: int = Field(default=8000, env="API_PORT")
    prefix: str = Field(default="/api/v1", env="API_PREFIX")
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        env="API_ALLOWED_ORIGINS",
    )


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    url: str = Field(default="", env="DATABASE_URL")
    echo: bool = Field(default=False, env="DATABASE_ECHO")


class RedisSettings(BaseSettings):
    """Redis configuration."""
    url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    max_connections: int = Field(default=10, env="REDIS_MAX_CONNECTIONS")


class Settings(BaseSettings):
    """Application settings."""
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Sub-settings
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    api: APISettings = Field(default_factory=APISettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"
