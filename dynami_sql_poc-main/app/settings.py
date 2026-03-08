# settings.py
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    TITLE: str = "Dynamic SQL Query API - Trino Edition"
    DESCRIPTION: str = "A FastAPI service for executing dynamic SQL queries against Trino/Pinot"
    VERSION: str = "1.0.0"

    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int = 5432
    POSTGRES_DATABASE: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None

    API_URL: str | None = None
    API_PORT: str | None = None

    EUREKA_SERVER_URL: str
    SERVICE_NAME: str
    SERVICE_HOST: str
    API_PROTOCOL: str
    SERVICE_PORT: int

    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

settings = Settings()