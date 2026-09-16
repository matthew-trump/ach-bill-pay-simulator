from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "mock_provider"
    database_url: str = Field(
        default="postgresql+psycopg://mock_provider:mock_provider@localhost:5433/mock_provider",
        validation_alias="MOCK_PROVIDER_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    api_key: str = Field(
        default="dev_mock_provider_key_do_not_use_for_real_systems",
        validation_alias="MOCK_PROVIDER_API_KEY",
    )
    webhook_timeout_seconds: float = Field(
        default=2.0,
        validation_alias="MOCK_PROVIDER_WEBHOOK_TIMEOUT_SECONDS",
    )


settings = Settings()
