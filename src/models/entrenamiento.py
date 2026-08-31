"""Orquestador de entrenamiento: entrena todos los modelos y elige el mejor.

Flujo:

1. Carga los datos (de la base de datos o de un `DataFrame` que se le pase).
2. Limpia y construye las variables predictoras.
3. Parte el conjunto **cronológicamente** en entrenamiento y prueba.
4. Entrena cada modelo del catálogo y lo evalúa sobre el conjunto de prueba.
5. Registra las métricas de todos en `ejecuciones_entrenamiento`.
6. Serializa el mejor con `joblib` en `src/models/artifacts/mejor_modelo.joblib`.

El criterio de selección por defecto es el **RMSE**, no el MAE: penaliza más
los errores grandes, y en un mercado energético equivocarse mucho en un pico de
precio cuesta bastante más que equivocarse un poco muchas veces.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.database.models import EjecucionEntrenamiento
from src.models import MODELOS_DISPONIBLES
from src.models.base import RUTA_ARTEFACTOS, ModeloPredictivo
from src.models.metricas import Metricas
from src.processing.features import (
    columnas_features,
    construir_features,
    dividir_train_test,
)
from src.processing.limpieza import limpiar

log = get_logger(__name__)

RUTA_MEJOR_MODELO = RUTA_ARTEFACTOS / "mejor_modelo.joblib"
METRICAS_VALIDAS = {"rmse", "mae", "mape"}


@dataclass
class ResultadoModelo:
    """Resultado del entrenamiento de un modelo concreto."""

    nombre: str
    modelo: ModeloPredictivo | None
    metricas: Metricas | None
    duracion_segundos: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.metricas is not None


@dataclass
class ResultadoEntrenamiento:
    """Resultado global de una ejecución de entrenamiento."""

    resultados: list[ResultadoModelo]
    mejor: ResultadoModelo | None
    ruta_artefacto: Path | None
    n_train: int
    n_test: int

    def tabla_comparativa(self) -> pd.DataFrame:
        """Tabla lista para pegar en el documento del trabajo de grado."""
        filas = [
            {
                "modelo": r.nombre,
                "MAE": round(r.metricas.mae, 2),
                "RMSE": round(r.metricas.rmse, 2),
                "MAPE (%)": round(r.metricas.mape, 2),
                "R2": round(r.metricas.r2, 4),
                "segundos": round(r.duracion_segundos, 1),
                "mejor": r is self.mejor,
            }
            for r in self.resultados
            if r.ok
        ]
        if not filas:
            return pd.DataFrame()
        return pd.DataFrame(filas).sort_values("RMSE").reset_index(drop=True)


def entrenar_todos(
    df: pd.DataFrame,
    *,
    db: Session | None = None,
    modelos: list[str] | None = None,
    horizonte: int = 24,
    proporcion_test: float = 0.2,
    criterio: str = "rmse",
    guardar_mejor: bool = True,
) -> ResultadoEntrenamiento:
    """Entrena y compara todos los modelos sobre los datos dados.

    Args:
        df: datos históricos crudos (con `fecha_hora` y `precio_bolsa`).
        db: sesión opcional; si se pasa, se registran las métricas en la BD.
        modelos: subconjunto de nombres a entrenar. Por defecto, todos.
        horizonte: horas hacia adelante a predecir.
        proporcion_test: tamaño del conjunto de prueba (corte cronológico).
        criterio: métrica de selección del mejor modelo.
        guardar_mejor: si se serializa el ganador a disco.
    """
    if criterio not in METRICAS_VALIDAS:
        raise ValueError(f"criterio debe ser uno de {sorted(METRICAS_VALIDAS)}")

    nombres = modelos or list(MODELOS_DISPONIBLES)
    desconocidos = set(nombres) - set(MODELOS_DISPONIBLES)
    if desconocidos:
        raise ValueError(
            f"Modelos desconocidos: {sorted(desconocidos)}. "
            f"Disponibles: {sorted(MODELOS_DISPONIBLES)}"
        )

    # --- Preparación de datos ---------------------------------------------
    log.info("Preparando datos (%d registros crudos)", len(df))
    datos = construir_features(limpiar(df), horizonte=horizonte)
    if datos.empty:
        raise ValueError("No quedaron datos tras la limpieza y el feature engineering")

    features = columnas_features(datos)
    train, test = dividir_train_test(datos, proporcion_test)

    if train.empty or test.empty:
        raise ValueError(
            f"Datos insuficientes para el split: train={len(train)}, test={len(test)}"
        )

    X_train, y_train = train[features], train["objetivo"]
    X_test, y_test = test[features], test["objetivo"]

    log.info(
        "Entrenando %d modelos | %d features | train=%d | test=%d",
        len(nombres),
        len(features),
        len(train),
        len(test),
    )

    # --- Entrenamiento -----------------------------------------------------
    resultados: list[ResultadoModelo] = []

    for nombre in nombres:
        log.info("--- %s ---", nombre)
        inicio = time.perf_counter()
        try:
            modelo = MODELOS_DISPONIBLES[nombre]()
            modelo.fit(X_train, y_train)
            metricas = modelo.evaluar(X_test, y_test)
            duracion = time.perf_counter() - inicio
            log.info("%s  %s  (%.1fs)", nombre, metricas, duracion)
            resultados.append(ResultadoModelo(nombre, modelo, metricas, duracion))
        except Exception as exc:  # noqa: BLE001 - un modelo caído no debe tumbar el resto
            duracion = time.perf_counter() - inicio
            log.exception("El modelo '%s' falló: %s", nombre, exc)
            resultados.append(
                ResultadoModelo(nombre, None, None, duracion, error=f"{type(exc).__name__}: {exc}")
            )

    exitosos = [r for r in resultados if r.ok]
    if not exitosos:
        raise RuntimeError("Ningún modelo se entrenó correctamente")

    mejor = min(exitosos, key=lambda r: getattr(r.metricas, criterio))
    log.info("Mejor modelo por %s: %s (%s)", criterio.upper(), mejor.nombre, mejor.metricas)

    # --- Persistencia ------------------------------------------------------
    ruta_artefacto: Path | None = None
    if guardar_mejor and mejor.modelo is not None:
        ruta_artefacto = mejor.modelo.guardar(RUTA_MEJOR_MODELO)
        mejor.modelo.guardar(RUTA_ARTEFACTOS / f"{mejor.nombre}.joblib")
        log.info("Mejor modelo guardado en %s", ruta_artefacto)

    if db is not None:
        _registrar_en_bd(db, resultados, mejor, ruta_artefacto, len(train), len(test))

    return ResultadoEntrenamiento(
        resultados=resultados,
        mejor=mejor,
        ruta_artefacto=ruta_artefacto,
        n_train=len(train),
        n_test=len(test),
    )


def cargar_mejor_modelo(ruta: Path | None = None) -> ModeloPredictivo:
    """Carga el modelo ganador del último entrenamiento."""
    ruta = ruta or RUTA_MEJOR_MODELO
    if not ruta.exists():
        raise FileNotFoundError(
            f"No hay modelo entrenado en {ruta}. "
            "Ejecuta primero: python -m scripts.entrenar (o POST /entrenar)"
        )
    return ModeloPredictivo.cargar(ruta)


# ---------------------------------------------------------------------------


def _registrar_en_bd(
    db: Session,
    resultados: list[ResultadoModelo],
    mejor: ResultadoModelo,
    ruta_artefacto: Path | None,
    n_train: int,
    n_test: int,
) -> None:
    """Guarda las métricas de todos los modelos para dejar trazabilidad."""
    for resultado in resultados:
        if not resultado.ok:
            continue
        assert resultado.metricas is not None and resultado.modelo is not None

        db.add(
            EjecucionEntrenamiento(
                nombre_modelo=resultado.nombre,
                mae=resultado.metricas.mae,
                rmse=resultado.metricas.rmse,
                mape=resultado.metricas.mape,
                r2=resultado.metricas.r2,
                n_muestras_entrenamiento=n_train,
                n_muestras_prueba=n_test,
                hiperparametros=json.dumps(
                    resultado.modelo.hiperparametros, default=str
                )[:1000],
                ruta_artefacto=str(ruta_artefacto) if resultado is mejor else None,
                es_mejor=resultado is mejor,
                duracion_segundos=resultado.duracion_segundos,
            )
        )
    db.commit()
    log.info("Métricas registradas en la base de datos")
