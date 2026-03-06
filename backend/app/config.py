from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql://localhost/teto_rpv"
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
    app_env: str = "development"
    api_key: str = "dev-key"


settings = Settings()
