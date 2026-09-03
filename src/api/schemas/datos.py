"""Esquemas del módulo de datos históricos."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatoHistoricoSalida(BaseModel):
    """Una hora del histórico, con todas las variables que XM publica.

    Se exponen todas y no un subconjunto: las gráficas dinámicas del frontend
    dejan al usuario elegir qué serie mirar, y recortar aquí obligaría a tocar
    el backend cada vez que se quiere graficar una variable más.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_hora: datetime
    precio_bolsa: float

    # Precio y mercado
    precio_bolsa_tx1: float | None = None
    precio_oferta_maximo: float | None = None
    costo_marginal: float | None = None
    precio_contratos_regulado: float | None = None
    precio_contratos_no_regulado: float | None = None
    precio_bolsa_ponderado: float | None = None

    # Demanda
    demanda_real: float | None = None
    demanda_comercial: float | None = None
    demanda_regulada: float | None = None
    demanda_no_regulada: float | None = None
    demanda_maxima_potencia: float | None = None

    # Generación
    generacion_total: float | None = None
    generacion_ideal: float | None = None
    generacion_hidraulica: float | None = None
    generacion_termica: float | None = None
    generacion_solar: float | None = None
    generacion_eolica: float | None = None
    generacion_cogeneracion: float | None = None
    disponibilidad_real: float | None = None

    # Sistema
    perdidas_energia: float | None = None
    restricciones_sin_alivio: float | None = None
    factor_emision_co2: float | None = None
    exportaciones_energia: float | None = None
    importaciones_energia: float | None = None

    # Hidrología y escasez
    aportes_hidricos: float | None = None
    aportes_media_historica: float | None = None
    volumen_util_energia: float | None = None
    capacidad_util_energia: float | None = None
    volumen_util_embalse: float | None = None
    vertimientos_energia: float | None = None
    precio_escasez: float | None = None
    precio_escasez_marginal: float | None = None

    # Clima
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
    demanda_minima: float | None = None
    demanda_media: float | None = None
    demanda_maxima: float | None = None
    #: Cuántas de las variables del esquema tienen al menos un dato. Es la forma
    #: rápida de ver, desde la interfaz, si una ingesta trajo el conjunto
    #: completo o solo las métricas básicas.
    variables_con_datos: int = 0
    variables_totales: int = 0


class PuntoSerie(BaseModel):
    """Un punto de una serie temporal genérica."""

    fecha_hora: datetime
    valor: float | None = None


class SerieSalida(BaseModel):
    """Una serie con su metadato de presentación."""

    variable: str
    etiqueta: str
    unidad: str
    puntos: list[PuntoSerie]


class RespuestaSeries(BaseModel):
    """Varias series alineadas en el mismo eje temporal."""

    desde: datetime | None = None
    hasta: datetime | None = None
    resolucion: str
    series: list[SerieSalida]


class PerfilHorario(BaseModel):
    """Media del objetivo por hora del día, separando laborables de festivos."""

    hora: int
    laboral: float | None = None
    fin_semana: float | None = None


class RespuestaPerfil(BaseModel):
    variable: str
    unidad: str
    perfil: list[PerfilHorario]


class RespuestaIngesta(BaseModel):
    """Resultado de `POST /datos/ingestar`."""

    registros_descargados: int
    registros_insertados: int
    registros_actualizados: int
    fecha_inicio: str
    fecha_fin: str
    mensaje: str
    variables_pobladas: list[str] = Field(default_factory=list)
