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
    database_url: str = "postgresql+asyncpg://kisan:password@localhost:5432/kisanai"
    redis_url: str = "redis://localhost:6379/0"

    # LLM fallback
    gemini_api_key: str = ""
    xai_api_key: str = ""

    # App
    app_env: str = "development"
    app_port: int = 8000
    log_level: str = "INFO"
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # Agmarknet / data.gov.in — accept either env name so existing scripts work.
    # The key is the same free key issued by data.gov.in for the Agmarknet
    # resource (9ef84268-d588-465a-a308-a864a43d0070).
    agmarknet_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AGMARKNET_API_KEY", "DATA_GOV_IN_API_KEY"),
    )

    # Weather APIs (Phase 2)
    openweather_api_key: str = ""  # OpenWeather API key (https://openweathermap.org)

    # Voice Message STT APIs (Phase 2 Module 2)
    google_speech_api_key: str = ""  # Google Cloud Speech-to-Text API key (https://cloud.google.com/speech-to-text)
    google_speech_language_code: str = "mr-IN"  # Marathi (India) language code
    voice_transcription_timeout: int = 30  # Max seconds per transcription request
    openai_api_key: str = ""  # OpenAI API key (for Whisper fallback)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
