"""Esquemas del módulo territorial: demanda por departamento y escenarios UPME."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartamentoSalida(BaseModel):
    """Estado actual de un departamento, tal como lo pinta el mapa."""

    codigo_dane: str
    departamento: str
    #: `False` para las Zonas No Interconectadas: no tienen demanda en el SIN y
    #: el mapa debe dibujarlas como "sin cobertura", no como demanda cero.
    interconectado: bool = True

    demanda_ultima_hora: float | None = None
    demanda_24h: float | None = None
    demanda_media_horaria_7d: float | None = None
    #: Variación porcentual de las últimas 24 h frente a las 24 h anteriores.
    variacion_24h: float | None = None
    #: Cuota sobre la demanda nacional del mismo periodo, en porcentaje.
    participacion: float | None = None
    pico_horario: int | None = Field(
        default=None, description="Hora del día con mayor demanda media"
    )

    #: `True` si el valor procede de repartir un mercado entre departamentos.
    estimado: bool = False
    mercados: str | None = None


class RespuestaMapa(BaseModel):
    """Instantánea completa para el mapa coroplético."""

    instante: datetime | None = None
    horas_agregadas: int
    total_nacional: float | None = None
    departamentos: list[DepartamentoSalida]


class PuntoDemanda(BaseModel):
    fecha_hora: datetime
    demanda_kwh: float


class SerieDepartamento(BaseModel):
    codigo_dane: str
    departamento: str
    estimado: bool
    unidad: str = "kWh"
    resolucion: str
    puntos: list[PuntoDemanda]


class RespuestaIngestaTerritorio(BaseModel):
    registros_descargados: int
    registros_insertados: int
    registros_actualizados: int
    departamentos: int
    fecha_inicio: str
    fecha_fin: str
    conserva_energia: bool
    error_relativo: float
    mensaje: str


class EscenarioUPME(BaseModel):
    mes: datetime
    escenario_alto: float | None = None
    escenario_medio: float | None = None
    escenario_bajo: float | None = None
    #: Demanda realmente observada ese mes, cuando ya existe.
    observado: float | None = None
    posicion: str | None = None


class RespuestaUPME(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    unidad: str = "kWh/mes"
    escenarios: list[EscenarioUPME]
