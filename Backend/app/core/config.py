import os
from dataclasses import dataclass, field

def _csv(value: str, default: list[str]) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()] or default

@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Recova API"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "0.1.0"))
    api_prefix: str = field(default_factory=lambda: os.getenv("API_PREFIX", "/api/v1"))
    cors_origins: list[str] = field(default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "http://localhost:3000"), ["*"]))

settings = Settings()
