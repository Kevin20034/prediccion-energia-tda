"""Esquemas del módulo predictivo."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.processing.features import OBJETIVO_POR_DEFECTO

PATRON_OBJETIVO = "^(precio_bolsa|demanda_real)$"
PATRON_CRITERIO = "^(rmse|mae|mape|smape|mase)$"


class SolicitudEntrenamiento(BaseModel):
    """Cuerpo de `POST /entrenar`."""

    modelos: list[str] | None = Field(
        default=None,
        description="Subconjunto a entrenar. Por defecto: todos.",
        examples=[["baseline_estacional", "xgboost", "lightgbm"]],
    )
    objetivo: str = Field(default=OBJETIVO_POR_DEFECTO, pattern=PATRON_OBJETIVO)
    horizonte: int = Field(default=24, ge=1, le=720, description="Horas a futuro")
    proporcion_test: float = Field(default=0.2, gt=0.05, lt=0.5)
    criterio: str = Field(default="rmse", pattern=PATRON_CRITERIO)
    pliegues_validacion: int = Field(
        default=0,
        ge=0,
        le=8,
        description=(
            "Pliegues de validación walk-forward. 0 la desactiva: multiplica el "
            "tiempo de entrenamiento por el número de pliegues y esta petición "
            "es síncrona."
        ),
    )


class MetricasSalida(BaseModel):
    mae: float
    rmse: float
    mape: float
    r2: float
    smape: float | None = None
    mase: float | None = None


class ResultadoModeloSalida(BaseModel):
    nombre: str
    familia: str = "otro"
    metricas: MetricasSalida | None = None
    duracion_segundos: float
    es_mejor: bool
    error: str | None = None
    rmse_validacion: float | None = None
    desviacion_validacion: float | None = None
    importancia: dict[str, float] = Field(default_factory=dict)


class RespuestaEntrenamiento(BaseModel):
    """Respuesta de `POST /entrenar`: la tabla comparativa del trabajo de grado."""

    mejor_modelo: str
    objetivo: str
    horizonte: int
    criterio: str
    n_muestras_entrenamiento: int
    n_muestras_prueba: int
    resultados: list[ResultadoModeloSalida]


class SolicitudPrediccion(BaseModel):
    """Cuerpo de `POST /predicciones`."""

    objetivo: str = Field(default=OBJETIVO_POR_DEFECTO, pattern=PATRON_OBJETIVO)
    horizonte: int = Field(
        default=24,
        ge=1,
        le=720,
        description="Horas a pronosticar. Debe existir un modelo entrenado a ese horizonte.",
    )
    guardar: bool = Field(default=True, description="Persistir las predicciones en la BD")


class PrediccionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    fecha_objetivo: datetime
    objetivo: str = OBJETIVO_POR_DEFECTO
    horizonte_horas: int = 24
    unidad: str = "COP/kWh"
    valor_estimado: float
    limite_inferior: float | None = None
    limite_superior: float | None = None
    valor_real: float | None = None
    nombre_modelo: str
    generado_en: datetime | None = None


class PuntoObservado(BaseModel):
    fecha_hora: datetime
    valor: float


class RespuestaPronostico(BaseModel):
    """Todo lo que la gráfica de pronóstico necesita, en una sola petición.

    Devolver el histórico y el pronóstico juntos —y no en dos llamadas— evita el
    parpadeo de dibujar primero una serie y luego la otra, y garantiza que
    ambas provienen del mismo instante de corte.
    """

    objetivo: str
    unidad: str
    horizonte: int
    etiqueta_horizonte: str
    nombre_modelo: str | None = None
    entrenado_en: datetime | None = None
    metricas: MetricasSalida | None = None
    #: Último instante con dato medido: la frontera entre lo observado y lo
    #: inferido.
    corte: datetime | None = None
    observado: list[PuntoObservado] = Field(default_factory=list)
    pronostico: list[PrediccionSalida] = Field(default_factory=list)


class EjecucionSalida(BaseModel):
    """Histórico de entrenamientos, para trazabilidad."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre_modelo: str
    objetivo: str = OBJETIVO_POR_DEFECTO
    horizonte_horas: int = 24
    mae: float
    rmse: float
    mape: float
    smape: float | None = None
    mase: float | None = None
    r2: float | None = None
    rmse_validacion: float | None = None
    desviacion_validacion: float | None = None
    n_pliegues: int | None = None
    n_muestras_entrenamiento: int
    n_muestras_prueba: int
    es_mejor: bool
    duracion_segundos: float | None = None
    ejecutado_en: datetime


class FilaComparacion(BaseModel):
    """Una fila de la tabla comparativa consolidada."""

    nombre_modelo: str
    familia: str
    objetivo: str
    horizonte_horas: int
    mae: float
    rmse: float
    mape: float
    smape: float | None = None
    mase: float | None = None
    r2: float | None = None
    duracion_segundos: float | None = None
    es_mejor: bool
    ejecutado_en: datetime
    #: Mejora porcentual del RMSE frente al baseline estacional del mismo
    #: objetivo y horizonte. Negativa significa que es peor que no hacer nada.
    mejora_sobre_baseline: float | None = None


class GanadorHorizonte(BaseModel):
    objetivo: str
    horizonte_horas: int
    etiqueta: str
    nombre_modelo: str
    familia: str
    rmse: float
    mase: float | None = None
    mejora_sobre_baseline: float | None = None
    veredicto: str


class RespuestaComparacion(BaseModel):
    """Comparación consolidada: qué modelo gana en cada horizonte y por qué."""

    filas: list[FilaComparacion]
    ganadores: list[GanadorHorizonte]
    recomendacion: str
    importancia_ganador: dict[str, float] = Field(default_factory=dict)
