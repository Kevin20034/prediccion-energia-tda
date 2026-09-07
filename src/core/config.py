"""Configuración central de la aplicación.

Toda la configuración se lee desde variables de entorno (archivo `.env`), nunca
se escribe en el código. Esto cumple el requisito no funcional de seguridad:
las credenciales de Neon y la clave JWT no viajan en el repositorio.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto: .../energia-tda
RAIZ_PROYECTO = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Configuración tipada y validada al arrancar.

    Si falta una variable obligatoria, la aplicación falla de inmediato con un
    mensaje claro en vez de reventar más adelante con un `None` inesperado.
    """

    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Base de datos -----------------------------------------------------
    # Endpoint pooled de Neon: lo usa la API.
    DATABASE_URL: str
    # Endpoint directo de Neon: lo usa Alembic. Si no se define, cae al pooled.
    DATABASE_URL_DIRECT: str | None = None

    # --- Seguridad ---------------------------------------------------------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # --- Administrador inicial --------------------------------------------
    ADMIN_EMAIL: str = "admin@tda.edu.co"
    ADMIN_PASSWORD: str = "Admin123*"

    # --- Fuentes de datos --------------------------------------------------
    XM_API_URL: str = "https://servapibi.xm.com.co"
    XM_API_KEY: str | None = None
    CLIMA_LATITUD: float = 6.2442  # Medellín
    CLIMA_LONGITUD: float = -75.5812

    # --- Aplicación --------------------------------------------------------
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- Ingesta automática ------------------------------------------------
    #: Apagada por defecto **a propósito**. Encendida, cada `pytest`, cada script
    #: y cada arranque con `--reload` dispararía descargas reales contra XM y
    #: Open-Meteo. Se enciende en el despliegue que deba mantenerse al día, y
    #: solo en uno: dos procesos con esto activo ingieren en paralelo.
    INGESTA_AUTOMATICA: bool = False
    #: XM publica una vez por hora en el mejor de los casos; revisar más a
    #: menudo solo gasta cuota de la API para traer lo mismo.
    INGESTA_INTERVALO_MINUTOS: int = 60

    # --- Derivados ---------------------------------------------------------
    @property
    def url_migraciones(self) -> str:
        """URL que debe usar Alembic.

        Neon expone dos endpoints. El *pooled* (con `-pooler`) pasa por PgBouncer
        en modo transacción, que no soporta bien las sentencias DDL con estado ni
        los `prepared statements` que Alembic emite. Por eso las migraciones van
        siempre por el endpoint directo.
        """
        return self.DATABASE_URL_DIRECT or self.DATABASE_URL

    @property
    def es_produccion(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada: se lee del disco una sola vez)."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
