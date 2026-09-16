from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "billpay_api"
    database_url: str = Field(
        default="postgresql+psycopg://billpay:billpay@localhost:5433/billpay",
        validation_alias="BILLPAY_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    provider_base_url: str = Field(
        default="http://127.0.0.1:8502",
        validation_alias="BILLPAY_PROVIDER_BASE_URL",
    )
    provider_api_key: str = Field(
        default="dev_mock_provider_key_do_not_use_for_real_systems",
        validation_alias="BILLPAY_PROVIDER_API_KEY",
    )
    settlement_provider_account_id: str = Field(
        default="ba_seed_billpay_settlement",
        validation_alias="BILLPAY_SETTLEMENT_PROVIDER_ACCOUNT_ID",
    )


settings = Settings()
