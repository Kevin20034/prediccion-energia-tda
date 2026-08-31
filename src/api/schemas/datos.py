"""Esquemas del módulo de datos históricos."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DatoHistoricoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora: datetime
    precio_bolsa: float
    demanda_real: float | None = None
    demanda_comercial: float | None = None
    generacion_total: float | None = None
    generacion_ideal: float | None = None
    generacion_hidraulica: float | None = None
    generacion_termica: float | None = None
    disponibilidad_real: float | None = None
    aportes_hidricos: float | None = None
    volumen_util_energia: float | None = None
    capacidad_util_energia: float | None = None
    volumen_util_embalse: float | None = None
    precio_escasez: float | None = None
    temperatura: float | None = None
    precipitacion: float | None = None
    humedad_relativa: float | None = None
    indice_oni: float | None = None
    fenomeno_climatico: str | None = None
    fuente: str


class ResumenDatos(BaseModel):
    """Estadísticos descriptivos, útiles para el dashboard del frontend."""

    total_registros: int
    fecha_minima: datetime | None = None
    fecha_maxima: datetime | None = None
    precio_minimo: float | None = None
    precio_medio: float | None = None
    precio_maximo: float | None = None


class RespuestaIngesta(BaseModel):
    """Resultado de `POST /datos/ingestar`."""

    registros_descargados: int
    registros_insertados: int
    registros_actualizados: int
    fecha_inicio: str
    fecha_fin: str
    mensaje: str
