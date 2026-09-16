from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "billpay_api"
    database_url: str = Field(
        default="postgresql+psycopg://billpay:billpay@localhost:5432/billpay",
        validation_alias="BILLPAY_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")


settings = Settings()
