"""Esquemas del estado de los datos: qué tan al día está cada fuente."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FuenteSalida(BaseModel):
    """Frescura de una fuente de datos."""

    nombre: str
    #: Última marca temporal **publicada por la fuente**, no la de la última
    #: ingesta: son cosas distintas y confundirlas es lo que permite que un
    #: sistema parezca al día llevando días parado.
    ultimo_dato: datetime | None = None
    #: Horas transcurridas entre `ultimo_dato` y ahora. `None` si no hay datos:
    #: devolver 0 se leería en pantalla como "recién actualizado".
    horas_de_retraso: float | None = None
    filas: int = 0
    descripcion: str = ""


class RespuestaEstado(BaseModel):
    """Lo que la barra necesita para decir si lo que se ve está vigente."""

    fuentes: list[FuenteSalida]
    consultado_en: datetime
    #: `None` mientras la ingesta automática esté apagada.
    ultima_revision: datetime | None = None
    proxima_revision: datetime | None = None
    ingesta_automatica: bool = Field(
        default=False,
        description="Si está apagada, nadie está buscando datos nuevos aunque la pantalla se refresque",
    )
    intervalo_minutos: int | None = None
