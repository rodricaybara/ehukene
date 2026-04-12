"""
Configuración del backend EHUkene.
Lee variables de entorno (o .env) mediante pydantic-settings.
Instancia única exportada como `settings`.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Base de datos
    database_url: str = "postgresql+asyncpg://ehukene:changeme@localhost:5432/ehukene"

    # Seguridad
    secret_key: str = "change-this-in-production"

    # Rate limiting (peticiones/minuto por IP)
    rate_limit_per_minute: int = 60

    # Deduplicación diaria (ventana en horas)
    dedup_window_hours: int = 25

    # Payload máximo en bytes
    max_payload_bytes: int = 1_048_576  # 1 MB

    # Entorno
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Instancia lista para importar directamente
settings = get_settings()
