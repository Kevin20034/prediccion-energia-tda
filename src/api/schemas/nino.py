"""Esquemas del fenómeno del Niño: estado ENSO, mapa de anomalía y efecto medido."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PuntoOni(BaseModel):
    mes: str
    oni: float
    fase: str


class RespuestaEstado(BaseModel):
    """Situación ENSO actual, según el último ONI disponible."""

    #: `None` cuando aún no se ha ingerido nada.
    fase: str | None = None
    oni: float | None = None
    #: débil · moderado · fuerte · muy fuerte, según el criterio de la NOAA.
    intensidad: str | None = None
    actualizado_en: datetime | None = None
    serie: list[PuntoOni] = Field(default_factory=list)


class DepartamentoNino(BaseModel):
    """Cómo está un departamento respecto a su propia normal."""

    codigo_dane: str
    departamento: str
    interconectado: bool = True

    temperatura: float | None = None
    #: Media de ese departamento en ese mes del año, sobre toda su historia.
    media_mensual: float | None = None
    #: `temperatura - media_mensual`. Positiva es más caliente de lo normal.
    anomalia: float | None = None
    demanda_kwh: float | None = None


class RespuestaMapa(BaseModel):
    instante: datetime | None = None
    horas_agregadas: int = 24
    departamentos: list[DepartamentoNino] = Field(default_factory=list)
    #: Extremo de la escala divergente, para que la leyenda sea simétrica.
    anomalia_maxima: float = 0.0


class EfectoFase(BaseModel):
    """Precio, demanda y generación medios bajo una fase ENSO."""

    fase: str
    horas: int
    precio: float | None = None
    demanda: float | None = None
    temperatura: float | None = None
    generacion_hidraulica: float | None = None
    generacion_termica: float | None = None

    #: Variación porcentual frente a la fase neutra. `None` para NEUTRO, que es
    #: la propia referencia.
    variacion_precio: float | None = None
    variacion_demanda: float | None = None
    variacion_generacion_hidraulica: float | None = None
    variacion_generacion_termica: float | None = None

    #: "solida" o "debil". Una fase con pocas horas no sostiene una afirmación,
    #: y la interfaz tiene que poder decirlo en vez de presentarlo todo igual.
    evidencia: str = "solida"


class RespuestaEfecto(BaseModel):
    fases: list[EfectoFase] = Field(default_factory=list)
    horas_para_evidencia_solida: int
