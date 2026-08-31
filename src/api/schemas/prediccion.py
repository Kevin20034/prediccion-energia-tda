"""Esquemas del módulo predictivo."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SolicitudEntrenamiento(BaseModel):
    """Cuerpo de `POST /entrenar`."""

    modelos: list[str] | None = Field(
        default=None,
        description="Subconjunto a entrenar. Por defecto: todos.",
        examples=[["regresion_lineal", "random_forest", "xgboost"]],
    )
    horizonte: int = Field(default=24, ge=1, le=168, description="Horas a futuro")
    proporcion_test: float = Field(default=0.2, gt=0.05, lt=0.5)
    criterio: str = Field(default="rmse", pattern="^(rmse|mae|mape)$")


class MetricasSalida(BaseModel):
    mae: float
    rmse: float
    mape: float
    r2: float


class ResultadoModeloSalida(BaseModel):
    nombre: str
    metricas: MetricasSalida | None = None
    duracion_segundos: float
    es_mejor: bool
    error: str | None = None


class RespuestaEntrenamiento(BaseModel):
    """Respuesta de `POST /entrenar`: la tabla comparativa del trabajo de grado."""

    mejor_modelo: str
    criterio: str
    n_muestras_entrenamiento: int
    n_muestras_prueba: int
    resultados: list[ResultadoModeloSalida]


class SolicitudPrediccion(BaseModel):
    """Cuerpo de `POST /predicciones`."""

    horas: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Cuántas horas hacia adelante estimar",
    )
    guardar: bool = Field(default=True, description="Persistir las predicciones en la BD")


class PrediccionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    fecha_objetivo: datetime
    precio_estimado: float
    precio_real: float | None = None
    nombre_modelo: str
    generado_en: datetime | None = None


class EjecucionSalida(BaseModel):
    """Histórico de entrenamientos, para trazabilidad."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_modelo: str
    mae: float
    rmse: float
    mape: float
    r2: float | None = None
    n_muestras_entrenamiento: int
    n_muestras_prueba: int
    es_mejor: bool
    duracion_segundos: float | None = None
    ejecutado_en: datetime
