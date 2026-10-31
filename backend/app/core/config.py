from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Paytm Saathi Backend"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "DEMO"
    DATABASE_URL: str = "sqlite:///./paytm_saathi.db"
    
    # JWT & Auth
    JWT_SECRET: str = "paytm-saathi-super-secret-demo-key-2026-phase1"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours for demo
    DEMO_OTP: str = "123456"

    # Sarvam AI Indic Speech & Language
    SARVAM_API_KEY: str = ""
    SARVAM_BASE_URL: str = "https://api.sarvam.ai"

    # Google Gemini Models & Live Multi-modal
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.8-flash"
    GEMINI_LIVE_MODEL: str = "gemini-2.0-flash-exp"

    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
    ]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
