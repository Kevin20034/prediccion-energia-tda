"""Fixtures compartidas.

Las pruebas corren contra **SQLite en memoria**, no contra Neon. Motivos:

* son instantáneas y no dependen de la red,
* no ensucian ni bloquean la base real,
* el esquema no usa tipos exclusivos de PostgreSQL (los enums se declaran con
  ``native_enum=False``), así que la compatibilidad es total.

Para probar contra PostgreSQL de verdad, Neon permite crear un *branch* de la
base (copia instantánea) y apuntar `DATABASE_URL` a él. Ver el README.
"""

from __future__ import annotations

import os

# Debe ejecutarse ANTES de importar cualquier módulo que lea la configuración.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "clave-de-pruebas-no-usar-en-produccion")

from collections.abc import Generator  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.api.main import app  # noqa: E402
from src.core.security import hashear_password  # noqa: E402
from src.database.models import Base, RolUsuario, Usuario  # noqa: E402
from src.database.session import get_db  # noqa: E402


@pytest.fixture(scope="session")
def engine_pruebas():
    """SQLite en memoria compartido por todas las conexiones de la sesión.

    `StaticPool` es imprescindible: sin él, cada conexión abriría su propia base
    en memoria y las tablas creadas en una no existirían en la siguiente.
    """
    motor = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(motor)
    yield motor
    motor.dispose()


@pytest.fixture
def db(engine_pruebas) -> Generator[Session, None, None]:
    """Sesión aislada por test: al terminar se revierte todo."""
    conexion = engine_pruebas.connect()
    transaccion = conexion.begin()
    sesion = sessionmaker(bind=conexion, expire_on_commit=False)()

    yield sesion

    sesion.close()
    transaccion.rollback()
    conexion.close()


@pytest.fixture
def cliente(db: Session) -> Generator[TestClient, None, None]:
    """Cliente HTTP con la dependencia de base de datos sustituida."""
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def usuario_admin(db: Session) -> Usuario:
    usuario = Usuario(
        email="admin@test.co",
        nombre="Admin de Pruebas",
        password_hash=hashear_password("Password123*"),
        rol=RolUsuario.ADMINISTRADOR,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@pytest.fixture
def usuario_institucional(db: Session) -> Usuario:
    usuario = Usuario(
        email="consulta@test.co",
        nombre="Usuario Institucional",
        password_hash=hashear_password("Password123*"),
        rol=RolUsuario.INSTITUCIONAL,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


@pytest.fixture
def datos_crudos() -> pd.DataFrame:
    """Serie horaria sintética de 30 días, con defectos deliberados.

    Incluye a propósito un duplicado, un nulo y un atípico extremo para que las
    pruebas de limpieza tengan algo real que corregir.
    """
    rng = np.random.default_rng(7)
    idx = pd.date_range("2025-01-01", periods=24 * 30, freq="h")

    df = pd.DataFrame(
        {
            "fecha_hora": idx,
            "precio_bolsa": 250 + 40 * np.sin(np.arange(len(idx)) / 12) + rng.normal(0, 15, len(idx)),
            "demanda_real": 9_000_000 + rng.normal(0, 200_000, len(idx)),
            "generacion_hidraulica": 5_000_000 + rng.normal(0, 300_000, len(idx)),
            "generacion_termica": 3_000_000 + rng.normal(0, 200_000, len(idx)),
            # Presente porque el pipeline la usa para detectar la demanda que XM
            # publica a medias: sin ella, esa comprobación no puede correr.
            "generacion_total": 9_100_000 + rng.normal(0, 250_000, len(idx)),
            "disponibilidad_real": 12_000_000 + rng.normal(0, 300_000, len(idx)),
            "temperatura": 22 + rng.normal(0, 2, len(idx)),
            "precipitacion": rng.exponential(1.5, len(idx)),
            "humedad_relativa": 70 + rng.normal(0, 5, len(idx)),
            "indice_oni": 0.3,
            "fenomeno_climatico": "NEUTRO",
            "fuente": "TEST",
        }
    )

    # Defectos intencionados
    df.loc[10, "precio_bolsa"] = np.nan          # nulo
    df.loc[50, "precio_bolsa"] = 99_999.0        # atípico extremo
    df = pd.concat([df, df.iloc[[100]]], ignore_index=True)  # duplicado

    return df
