"""Configuración de logging para toda la aplicación."""

from __future__ import annotations

import logging
import sys

from src.core.config import settings

_FORMATO = "%(asctime)s | %(levelname)-8s | %(name)-28s | %(message)s"


def configurar_logging(nivel: str | None = None) -> None:
    """Configura el logger raíz. Idempotente: llamarla dos veces no duplica salida."""
    raiz = logging.getLogger()
    if raiz.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_FORMATO, datefmt="%Y-%m-%d %H:%M:%S"))
    raiz.addHandler(handler)
    raiz.setLevel(nivel or settings.LOG_LEVEL)

    # SQLAlchemy es muy verboso en INFO; lo subimos a WARNING.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(nombre: str) -> logging.Logger:
    """Atajo para obtener un logger ya configurado."""
    configurar_logging()
    return logging.getLogger(nombre)
