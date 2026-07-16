import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Instagram Media API"
    app_version: str = "1.0.0"
    app_description: str = "Professional API to extract high-resolution photos and videos from Instagram posts."
    debug: bool = False

    # Request settings
    request_timeout: int = int(os.getenv("REQUEST_TIMEOUT", "20"))
    proxy_timeout: int = int(os.getenv("PROXY_TIMEOUT", "30"))
    impersonate_browser: str = os.getenv("IMPERSONATE_BROWSER", "chrome120")

    # CORS settings
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def cors_origins_list(self):
        if not self.cors_origins or self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
