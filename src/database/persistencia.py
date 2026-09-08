"""Escritura idempotente de las series en la base de datos.

Toda la ingesta pasa por aquí, y toda es **idempotente**: reejecutar un rango ya
descargado actualiza los valores en lugar de fallar por clave duplicada. Es lo
que se necesita para dos cosas que ocurren constantemente en este proyecto:
reintentar una ingesta que se cortó a medias, y recoger las correcciones que XM
publica sobre datos que ya había dado por buenos.

En PostgreSQL se usa ``INSERT ... ON CONFLICT DO UPDATE``, que resuelve el lote
entero en una sentencia. En SQLite —el motor de las pruebas— se hace fila a
fila, porque su soporte de *upsert* con lotes grandes es más frágil y aquí el
volumen nunca es un problema.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.database.models import (
    Base,
    ClimaDepartamento,
    DatoHistorico,
    DemandaDepartamento,
    ProyeccionUPME,
)

log = get_logger(__name__)

TAMANO_LOTE = 1000


def guardar_datos_historicos(db: Session, df: pd.DataFrame) -> tuple[int, int]:
    """Inserta o actualiza registros horarios. Devuelve `(insertados, actualizados)`."""
    return _guardar(db, df, DatoHistorico, ["fecha_hora"])


def guardar_demanda_departamento(db: Session, df: pd.DataFrame) -> tuple[int, int]:
    """Inserta o actualiza la demanda por departamento.

    Espera las columnas que produce `xm_departamentos.repartir`; se renombran
    aquí a los nombres del modelo para que el recolector no tenga que conocer el
    esquema de la base de datos.
    """
    if df.empty:
        return 0, 0

    preparado = df.rename(columns={"estimado": "factor_estimado"})
    return _guardar(db, preparado, DemandaDepartamento, ["fecha_hora", "codigo_dane"])


def guardar_clima_departamento(db: Session, df: pd.DataFrame) -> tuple[int, int]:
    """Inserta o actualiza el clima horario por departamento.

    Espera las columnas que produce `clima_departamentos.ClimaDepartamentosClient`.
    Si el `DataFrame` trae `media_mensual` o `anomalia`, `_guardar` las descarta
    sola: son derivadas y se recalculan al consultar.
    """
    if df.empty:
        return 0, 0

    return _guardar(db, df, ClimaDepartamento, ["fecha_hora", "codigo_dane"])


def guardar_proyeccion_upme(db: Session, df: pd.DataFrame) -> tuple[int, int]:
    """Inserta o actualiza los escenarios mensuales de la UPME."""
    if df.empty:
        return 0, 0

    preparado = df.rename(
        columns={
            "alto": "escenario_alto",
            "medio": "escenario_medio",
            "bajo": "escenario_bajo",
        }
    )
    return _guardar(db, preparado, ProyeccionUPME, ["mes"], columna_fecha="mes")


# ---------------------------------------------------------------------------


def _guardar(
    db: Session,
    df: pd.DataFrame,
    modelo: type[Base],
    claves: list[str],
    columna_fecha: str = "fecha_hora",
) -> tuple[int, int]:
    """Escritura idempotente genérica sobre cualquier tabla del proyecto."""
    if df.empty:
        return 0, 0

    columnas_modelo = {c.name for c in modelo.__table__.columns}
    columnas = [c for c in df.columns if c in columnas_modelo]
    if not columnas:
        raise ValueError(
            f"Ninguna columna de los datos coincide con {modelo.__tablename__}: "
            f"{sorted(df.columns)}"
        )

    existentes_antes = db.execute(select(func.count()).select_from(modelo)).scalar_one()
    registros = _a_registros(df, columnas, columna_fecha)

    if db.get_bind().dialect.name == "postgresql":
        _upsert_postgres(db, modelo, registros, columnas, claves)
    else:
        _upsert_generico(db, modelo, registros, claves)

    db.commit()

    existentes_despues = db.execute(select(func.count()).select_from(modelo)).scalar_one()
    insertados = existentes_despues - existentes_antes
    return insertados, len(registros) - insertados


def _a_registros(
    df: pd.DataFrame, columnas: list[str], columna_fecha: str
) -> list[dict[str, Any]]:
    """Convierte el `DataFrame` en diccionarios listos para el `INSERT`."""
    recorte = df[columnas].copy()
    if columna_fecha in recorte.columns:
        recorte[columna_fecha] = pd.to_datetime(recorte[columna_fecha]).dt.to_pydatetime()

    registros = recorte.where(recorte.notna(), None).to_dict(orient="records")

    # `to_dict` puede dejar NaN de numpy, que SQLAlchemy insertaría como el texto
    # 'NaN' en vez de NULL.
    for registro in registros:
        for clave, valor in registro.items():
            if isinstance(valor, float) and valor != valor:  # NaN
                registro[clave] = None

    return registros


def _upsert_postgres(
    db: Session,
    modelo: type[Base],
    registros: list[dict],
    columnas: list[str],
    claves: list[str],
) -> None:
    actualizables = [c for c in columnas if c not in {"id", *claves}]

    for inicio in range(0, len(registros), TAMANO_LOTE):
        trozo = registros[inicio : inicio + TAMANO_LOTE]
        sentencia = pg_insert(modelo).values(trozo)
        sentencia = sentencia.on_conflict_do_update(
            index_elements=claves,
            set_={c: sentencia.excluded[c] for c in actualizables},
        )
        db.execute(sentencia)


def _upsert_generico(
    db: Session, modelo: type[Base], registros: list[dict], claves: list[str]
) -> None:
    """Camino para SQLite: busca y actualiza, o inserta."""
    for registro in registros:
        condiciones = [getattr(modelo, clave) == registro[clave] for clave in claves]
        existente = db.execute(select(modelo).where(*condiciones)).scalar_one_or_none()
        if existente:
            for clave, valor in registro.items():
                setattr(existente, clave, valor)
        else:
            db.add(modelo(**registro))
