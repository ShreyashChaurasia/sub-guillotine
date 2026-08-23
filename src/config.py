"""Configuration management for Sub Guillotine."""

import os
from pathlib import Path
from typing import Optional
import boto3
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # AWS & Bedrock Settings
    aws_access_key_id: Optional[str] = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: Optional[str] = Field(default=None, alias="AWS_SESSION_TOKEN")
    aws_default_region: str = Field(default="us-east-1", alias="AWS_DEFAULT_REGION")
    bedrock_model_id: str = Field(
        default="anthropic.claude-3-5-sonnet-20241022-v2:0",
        alias="BEDROCK_MODEL_ID",
    )

    # Application & Storage Settings
    database_path: str = Field(default="sub_guillotine.db", alias="DATABASE_PATH")
    screenshots_dir: str = Field(default="screenshots", alias="SCREENSHOTS_DIR")
    deadline_threshold_hours: int = Field(default=24, alias="DEADLINE_THRESHOLD_HOURS")

    # Mock SaaS Environment
    mock_portal_host: str = Field(default="127.0.0.1", alias="MOCK_PORTAL_HOST")
    mock_portal_port: int = Field(default=8888, alias="MOCK_PORTAL_PORT")
    mock_portal_url: str = Field(default="http://localhost:8888", alias="MOCK_PORTAL_URL")
    headless_browser: bool = Field(default=True, alias="HEADLESS_BROWSER")

    # HITL Notification Mode
    hitl_mode: str = Field(default="cli", alias="HITL_MODE")
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")

    def ensure_directories(self) -> None:
        """Ensure necessary output directories exist."""
        Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)
        db_dir = Path(self.database_path).parent
        if db_dir and str(db_dir) != ".":
            db_dir.mkdir(parents=True, exist_ok=True)


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """Singleton getter for application settings."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
        _settings_instance.ensure_directories()
    return _settings_instance


def get_bedrock_client(settings: Optional[Settings] = None):
    """Initializes a Boto3 Amazon Bedrock Runtime client using configured credentials."""
    cfg = settings or get_settings()
    kwargs = {"region_name": cfg.aws_default_region}

    if cfg.aws_access_key_id and cfg.aws_secret_access_key:
        kwargs["aws_access_key_id"] = cfg.aws_access_key_id
        kwargs["aws_secret_access_key"] = cfg.aws_secret_access_key
        if cfg.aws_session_token:
            kwargs["aws_session_token"] = cfg.aws_session_token

    return boto3.client("bedrock-runtime", **kwargs)
