from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # WhatsApp Cloud API
    whatsapp_phone_id: str = ""
    whatsapp_token: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_app_id: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://dhanyada:password@localhost:5432/dhanyada"
    redis_url: str = "redis://localhost:6379/0"

    # LLM fallback
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "mistralai/mistral-7b-instruct"
    xai_api_key: str = ""

    # App
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"

    # Admin Dashboard
    admin_username: str = "admin"
    admin_password: str = "changeme"
    jwt_secret: str = "your-secret-key-change-in-production"
    jwt_expiry_hours: int = 1

    # Agmarknet / data.gov.in — accept either env name so existing scripts work.
    # The key is the same free key issued by data.gov.in for the Agmarknet
    # resource (9ef84268-d588-465a-a308-a864a43d0070).
    agmarknet_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AGMARKNET_API_KEY", "DATA_GOV_IN_API_KEY"),
    )

    # Weather APIs (Phase 2)
    openweather_api_key: str = ""  # OpenWeather API key (https://openweathermap.org)
    agromonitoring_api_key: str = ""  # AgroMonitoring API key (https://agromonitoring.com)

    # Voice Message STT APIs (Phase 2 Module 2)
    google_speech_api_key: str = ""  # Google Cloud Speech-to-Text API key (https://cloud.google.com/speech-to-text)
    google_speech_language_code: str = "mr-IN"  # Marathi (India) language code
    voice_transcription_timeout: int = 30  # Max seconds per transcription request
    openai_api_key: str = ""  # OpenAI API key (for Whisper fallback)

    # Pest Diagnosis (Phase 2 Module 3)
    tensorflow_model_path: str = "models/crop_disease_classifier.h5"  # Path to TensorFlow model
    gemini_vision_enabled: bool = True  # Enable Gemini Vision fallback
    image_processing_timeout: int = 60  # Max seconds for image diagnosis
    diagnosis_confidence_threshold: float = 0.7  # Min confidence to report diagnosis

    # Government Schemes & MSP Alerts (Phase 2 Module 4)
    pmksy_api_enabled: bool = True  # PM-KISAN API enabled
    pmfby_api_enabled: bool = True  # PM-FASAL Bima Yojana API enabled
    scheme_ingestion_timeout: int = 30  # Max seconds per scheme source
    msp_alert_enabled: bool = True  # MSP alert feature enabled

    # Email & Alerting (Phase 3 Step 3)
    smtp_host: str = "smtp.gmail.com"  # SMTP server hostname
    smtp_port: int = 587  # SMTP port (587 for TLS, 465 for SSL)
    smtp_username: str = ""  # Gmail address or SMTP username
    smtp_password: str = ""  # Gmail app password or SMTP password
    admin_email: str = ""  # Admin's email (alert recipient)
    alert_error_threshold: float = 5.0  # % errors to trigger alert
    alert_latency_threshold: int = 1000  # ms latency to trigger alert
    alert_cooldown_minutes: int = 60  # Don't send duplicate alerts within N minutes
    error_retention_days: int = 90  # Keep error logs for N days
    health_check_interval_minutes: int = 60  # Run health checks every N minutes

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Railway / Heroku-style Postgres URLs come through as `postgresql://...`;
    # our async SQLAlchemy engine needs the asyncpg driver explicitly.
    if s.database_url.startswith("postgresql://"):
        s.database_url = s.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif s.database_url.startswith("postgres://"):
        s.database_url = s.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return s


settings = get_settings()
