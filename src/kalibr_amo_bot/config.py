from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_name: str = "Kalibr amoCRM Report Bot"
    app_version: str = "1.0.0"
    timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./local.db"
    redis_url: str = "redis://localhost:6379/0"

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""
    public_base_url: str = "http://localhost:10001"

    kommo_subdomain: str = ""
    kommo_long_lived_token: str = ""
    kommo_requests_per_second: int = Field(default=6, ge=1, le=7)
    kommo_user_cache_seconds: int = Field(default=300, ge=0, le=3600)
    kommo_webhook_secret: str = "change-me-kommo-webhook-secret"
    initial_import_days: int = Field(default=365, ge=1, le=3650)

    admin_username: str = "admin"
    admin_password: str = "change-me"
    admin_session_secret: str = "change-me-too"
    link_token_minutes: int = Field(default=30, ge=5, le=1440)
    phone_hash_salt: str = "change-me-phone-salt"

    sync_lookback_minutes: int = Field(default=15, ge=1, le=1440)
    daily_operator_time: str = "18:30"
    daily_manager_time: str = "19:00"
    daily_executive_time: str = "20:00"
    weekly_report_weekday: int = Field(default=0, ge=0, le=6)
    weekly_report_time: str = "09:00"
    monthly_report_time: str = "09:30"
    default_language: str = "ru"

    @field_validator("database_url")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return "postgresql+psycopg://" + value[len("postgres://"):]
        if value.startswith("postgresql://") and not value.startswith("postgresql+psycopg://"):
            return "postgresql+psycopg://" + value[len("postgresql://"):]
        return value

    @field_validator("redis_url")
    @classmethod
    def normalize_redis_url(cls, value: str) -> str:
        if value.startswith("rediss://") and "ssl_cert_reqs=" not in value:
            separator = "&" if "?" in value else "?"
            return f"{value}{separator}ssl_cert_reqs=CERT_REQUIRED"
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("default_language")
    @classmethod
    def valid_language(cls, value: str) -> str:
        return value if value in {"ru", "uz"} else "ru"

    @property
    def kommo_base_url(self) -> str:
        subdomain = self.kommo_subdomain.strip().replace("https://", "").replace("http://", "")
        subdomain = subdomain.split(".")[0]
        return f"https://{subdomain}.kommo.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
