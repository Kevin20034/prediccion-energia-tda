"""Ingesta automática programada.

El problema que resuelve: las fuentes publican solas, pero nadie las consultaba.
Los datos del sistema se quedaron en el 31 de agosto mientras XM seguía
publicando, simplemente porque la ingesta era un comando que alguien tenía que
recordar ejecutar.

Por qué un bucle propio y no APScheduler
----------------------------------------

Lo que hace falta aquí es «cada N minutos, y no dos veces a la vez». Eso son unas
pocas decenas de líneas y ninguna dependencia nueva. APScheduler aporta cron,
persistencia de trabajos y almacenes distribuidos: nada de lo cual se usa, y
todo lo cual hay que mantener y explicar en un trabajo de grado.

Sobre «tiempo real»
-------------------

No lo hay, y el planificador no lo finge. XM publica con días de retraso; lo que
esto consigue es que el sistema esté **tan al día como la fuente permita**, y que
`GET /estado-datos` pueda decir exactamente cuánto es eso.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger(__name__)

#: Un trabajo es un nombre y algo que se puede llamar sin argumentos. Devolver
#: `(insertados, actualizados)` es lo habitual, pero no se exige: un trabajo que
#: devuelva otra cosa se registra igual, solo que sin cifras.
Trabajo = tuple[str, Callable[[], Any]]


class Planificador:
    """Ejecuta trabajos de ingesta cada cierto tiempo, sin solaparlos."""

    def __init__(self, intervalo_minutos: int = 60, trabajos: list[Trabajo] | None = None) -> None:
        self.intervalo = timedelta(minutes=intervalo_minutos)
        self.trabajos: list[Trabajo] = list(trabajos or [])
        self._ultima: datetime | None = None
        # Impide que dos corrutinas del mismo proceso entren a la vez. Entre
        # procesos distintos no protege nada: para eso está tener la ingesta
        # encendida en un solo despliegue.
        self._candado = asyncio.Lock()

    # -- guarda ------------------------------------------------------------

    def debe_correr(self, ahora: datetime) -> bool:
        """¿Ha pasado el intervalo desde la última revisión?"""
        if self._ultima is None:
            return True
        return ahora - self._ultima >= self.intervalo

    def marcar_ejecucion(self, momento: datetime) -> None:
        self._ultima = momento

    def estado(self) -> dict[str, datetime | None]:
        """Lo que `GET /estado-datos` publica sobre la revisión."""
        if self._ultima is None:
            return {"ultima_revision": None, "proxima_revision": None}
        return {
            "ultima_revision": self._ultima,
            "proxima_revision": self._ultima + self.intervalo,
        }

    # -- ejecución ---------------------------------------------------------

    def ejecutar_una_vez(self) -> dict[str, dict[str, Any]]:
        """Corre todos los trabajos y devuelve el resultado de cada uno.

        Cada trabajo va en su propio `try`: una fuente caída deja su dato viejo,
        que es degradación aceptable, pero no puede impedir que las demás se
        actualicen ni tumbar el proceso de la API.
        """
        resultados: dict[str, dict[str, Any]] = {}

        for nombre, trabajo in self.trabajos:
            try:
                devuelto = trabajo()
                insertados, actualizados = _cifras(devuelto)
                resultados[nombre] = {
                    "insertados": insertados,
                    "actualizados": actualizados,
                    "error": None,
                }
                log.info(
                    "Ingesta %s: %d nuevos, %d actualizados", nombre, insertados, actualizados
                )
            except Exception as error:  # noqa: BLE001 — el aislamiento es el objetivo
                resultados[nombre] = {"insertados": 0, "actualizados": 0, "error": str(error)}
                log.exception("Ingesta %s falló; se continúa con las demás fuentes", nombre)

        # Se marca pase lo que pase: se revisó. Si un fallo dejara la marca sin
        # poner, el bucle reintentaría sin pausa contra una fuente caída.
        self.marcar_ejecucion(datetime.now(UTC))
        return resultados

    async def ciclo(self) -> None:
        """Bucle de fondo. Se cancela al apagar la aplicación."""
        log.info(
            "Planificador activo: revisión cada %d min", int(self.intervalo.total_seconds() // 60)
        )
        try:
            while True:
                if self.debe_correr(datetime.now(UTC)):
                    async with self._candado:
                        # La ingesta es bloqueante (red y pandas). Ejecutarla en
                        # el bucle de eventos dejaría a la API sin responder
                        # durante los minutos que dura la descarga.
                        await asyncio.to_thread(self.ejecutar_una_vez)
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            log.info("Planificador detenido")
            raise


def _cifras(devuelto: Any) -> tuple[int, int]:
    """Normaliza lo que devuelve un trabajo a `(insertados, actualizados)`."""
    if isinstance(devuelto, tuple) and len(devuelto) == 2:
        try:
            return int(devuelto[0]), int(devuelto[1])
        except (TypeError, ValueError):
            return 0, 0
    return 0, 0


#: Instancia única que usan el `lifespan` y `GET /estado-datos`. Los trabajos se
#: registran en `main.py`, donde ya están importadas las funciones de ingesta.
planificador = Planificador(intervalo_minutos=settings.INGESTA_INTERVALO_MINUTOS)
