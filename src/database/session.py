"""Motor y sesiones de SQLAlchemy.

Configuración pensada para **Neon** (PostgreSQL serverless). Neon suspende el
cómputo tras unos minutos de inactividad en el plan gratuito y, al hacerlo,
**corta las conexiones TCP abiertas**. Si el pool de SQLAlchemy conserva esas
conexiones muertas, la siguiente petición falla con
`SSL connection has been closed unexpectedly`.

Las dos opciones que lo evitan:

* ``pool_pre_ping=True`` — antes de entregar una conexión del pool, lanza un
  ``SELECT 1``; si falla, la descarta y abre otra. Es la pieza imprescindible.
* ``pool_recycle=300`` — recicla conexiones a los 5 minutos, por debajo del
  umbral de autosuspensión, para que casi nunca se llegue al caso anterior.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import settings


def crear_engine(url: str | None = None, **kwargs) -> Engine:
    """Crea un `Engine` con los parámetros adecuados según el backend.

    SQLite (usado en las pruebas) no admite los argumentos de pool de
    PostgreSQL, así que se ajustan dinámicamente.
    """
    url = url or settings.DATABASE_URL

    if url.startswith("sqlite"):
        opciones = {
            "connect_args": {"check_same_thread": False},
            "future": True,
        }
    else:
        opciones = {
            "pool_pre_ping": True,  # imprescindible con Neon
            "pool_recycle": 300,  # recicla antes de la autosuspensión
            "pool_size": 5,
            "max_overflow": 5,
            "pool_timeout": 30,
            "future": True,
            # Neon cierra conexiones ociosas; un timeout de conexión corto
            # evita que la API se quede colgada si el endpoint está frío.
            "connect_args": {"connect_timeout": 10},
        }

    opciones.update(kwargs)
    return create_engine(url, **opciones)


engine = crear_engine()

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: entrega una sesión y la cierra siempre."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
