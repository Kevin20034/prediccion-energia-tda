"""Esquemas de la vista de usuario: una sola respuesta con el estado del sistema."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Indicador(BaseModel):
    """Una magnitud del sistema con su contexto inmediato.

    Lleva el valor, la unidad **ya escalada para leerse** y la variación frente
    al día anterior. Un número suelto no dice nada: 8.400.000 kWh no significa
    nada sin saber si eso es mucho o poco comparado con ayer.
    """

    valor: float | None = None
    unidad: str = ""
    variacion_24h: float | None = Field(default=None, description="Porcentaje")
    media_7d: float | None = None
    #: Hora a la que corresponde el valor. Cada métrica tiene la suya: XM
    #: publica el precio casi al momento y la demanda con días de retraso, y la
    #: interfaz tiene que poder decirlo en vez de dar todo por igual de fresco.
    instante: datetime | None = None


class Embalses(BaseModel):
    """Nivel de los embalses, que en Colombia es el contexto de todo lo demás."""

    nivel: float | None = Field(default=None, description="Porcentaje de llenado")
    variacion_7d: float | None = None
    #: `holgado`, `normal`, `ajustado` o `critico`. La interfaz lo usa para el
    #: color; el texto se muestra tal cual porque un porcentaje sin categoría
    #: obliga al usuario a saber qué es un nivel normal en el sistema colombiano.
    estado: str = "desconocido"
    descripcion: str = ""


class ParteMezcla(BaseModel):
    clave: str
    etiqueta: str
    porcentaje: float


class ResumenPronostico(BaseModel):
    horizonte: int
    etiqueta: str
    valor_final: float | None = None
    unidad: str = ""
    variacion: float | None = None
    #: `sube`, `baja` o `estable`.
    tendencia: str = "estable"
    limite_inferior: float | None = None
    limite_superior: float | None = None
    nombre_modelo: str | None = None
    #: Error típico del modelo, para poder decir "suele acertar dentro de ±X".
    error_tipico: float | None = None
    #: Hay un pronóstico vigente que enseñar.
    disponible: bool = False
    #: Existe un modelo entrenado para esta combinación.
    #:
    #: Separar las dos cosas importa para lo que se le dice al usuario. Sin
    #: modelo, no hay nada que hacer desde esta pantalla. Con modelo pero sin
    #: pronóstico vigente —porque acaban de llegar datos nuevos y los guardados
    #: se quedaron atrás— basta con recalcular, y decir "sin modelo entrenado"
    #: sería sencillamente falso.
    hay_modelo: bool = False


class DepartamentoResumen(BaseModel):
    codigo_dane: str
    departamento: str
    demanda_24h: float | None = None
    participacion: float | None = None
    estimado: bool = False


class Panorama(BaseModel):
    """Todo lo que la vista de usuario necesita, resuelto en una sola llamada.

    La alternativa —cuatro peticiones encadenadas— llena la pantalla de
    indicadores de carga que aparecen y desaparecen en distinto momento, que es
    justo lo que hace que una interfaz se sienta enredada.
    """

    instante: datetime | None = None
    #: Frase en lenguaje llano que resume la situación. Se redacta en el
    #: servidor, donde están los datos, y no en la interfaz.
    titular: str = ""
    detalle: str = ""

    precio: Indicador = Field(default_factory=Indicador)
    demanda: Indicador = Field(default_factory=Indicador)
    embalses: Embalses = Field(default_factory=Embalses)

    mezcla: list[ParteMezcla] = Field(default_factory=list)
    pronosticos: list[ResumenPronostico] = Field(default_factory=list)
    departamentos: list[DepartamentoResumen] = Field(default_factory=list)
