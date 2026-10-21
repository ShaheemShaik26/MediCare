from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MediCare"
    database_url: str = Field(default="sqlite:///./medicare.db")
    secret_key: str = Field(default="dev-secret-key-change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    upload_dir: str = "./storage"
    max_upload_size_mb: int = Field(default=10, ge=1, le=50)
    tesseract_cmd: str = "tesseract"
    ocr_languages: str = "eng"
    ocr_enabled: bool = True
    medical_ner_enabled: bool = True
    medical_ner_model: str = "d4data/biomedical-ner-all"
    medical_ner_min_score: float = Field(default=0.85, ge=0.0, le=1.0)
    cors_origins: str = "http://localhost:5173"
    secure_cookies: bool = True


settings = Settings()

UPLOAD_DIR = Path(settings.upload_dir).resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
