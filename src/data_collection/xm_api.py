"""Transporte crudo contra la API pública de XM (``servapibi.xm.com.co``).

Este módulo no sabe nada del dominio: solo pide métricas, trocea rangos, lanza
las peticiones en paralelo y aplana las respuestas a `DataFrame`. Quien decide
*qué* métricas pedir y *qué* significan es `xm_client`, `xm_departamentos` o
`xm_upme`.

Separarlo tiene una razón concreta: la versión anterior pedía 9 métricas en
serie y tardaba lo mismo que tarda una petición multiplicado por el número de
lotes. Al subir a ~30 métricas eso pasaba de "lento" a "inusable". Aquí las
peticiones van en un `ThreadPoolExecutor` —son E/S pura, así que el GIL no
estorba— y el tiempo total lo marca el lote más lento, no la suma.

Formatos de respuesta de XM
---------------------------

``POST /hourly``
    ``Items[].HourlyEntities[].Values`` = ``{"code": ..., "Hour01": ...,
    "Hour24": ...}``. Una entrada por día y entidad, con las 24 horas dentro.

``POST /daily``
    ``Items[].DailyEntities[].Value`` = un valor por día y entidad.

``POST /monthly``
    ``Items[].MonthlyEntities[].Value`` = un valor por mes y entidad.

``POST /lists``
    ``Items[].ListEntities[].Values`` = un diccionario de atributos por fila
    (catálogos: recursos, agentes, embalses, ríos).

.. note::
   XM limita cada consulta a ``MaxDays`` días: 31 para las series horarias y
   diarias, 731 para las mensuales y los catálogos. Los rangos se trocean
   respetando ese límite.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from threading import local

import pandas as pd
import requests

from src.core.config import settings
from src.core.logging import get_logger

log = get_logger(__name__)

#: Días máximos por consulta según el tipo de serie (los publica XM en
#: `ListadoMetricas`, campo `MaxDays`).
MAX_DIAS = {"hourly": 31, "daily": 31, "monthly": 731, "lists": 731}

TIMEOUT_SEGUNDOS = 90
#: Peticiones concurrentes. Seis es un compromiso: acelera ~5x frente a la
#: descarga en serie sin que XM empiece a cortar conexiones.
CONCURRENCIA = 6
#: Reintentos por lote. XM devuelve 502/504 esporádicos en rangos largos.
REINTENTOS = 3


class ErrorXM(RuntimeError):
    """La API de XM no pudo atender la petición."""


@dataclass(frozen=True)
class Peticion:
    """Una consulta concreta: métrica + entidad + tramo de fechas."""

    periodo: str
    metric_id: str
    entidad: str
    inicio: date
    fin: date

    @property
    def url(self) -> str:
        return f"{settings.XM_API_URL.rstrip('/')}/{self.periodo}"

    @property
    def cuerpo(self) -> dict[str, str]:
        return {
            "MetricId": self.metric_id,
            "StartDate": self.inicio.isoformat(),
            "EndDate": self.fin.isoformat(),
            "Entity": self.entidad,
        }


# ---------------------------------------------------------------------------
# Sesión HTTP
# ---------------------------------------------------------------------------

_hilo = local()


def _sesion() -> requests.Session:
    """Una `Session` por hilo.

    `requests.Session` no es *thread-safe*: compartir una sola entre los hilos
    del pool produce respuestas cruzadas y errores de conexión intermitentes,
    que además son dificilísimos de reproducir. Una por hilo mantiene el
    *keep-alive* (que es lo que se buscaba) sin compartir estado.
    """
    sesion = getattr(_hilo, "sesion", None)
    if sesion is None:
        sesion = requests.Session()
        sesion.headers.update({"Content-Type": "application/json"})
        _hilo.sesion = sesion
    return sesion


# ---------------------------------------------------------------------------
# Descarga
# ---------------------------------------------------------------------------


def partir_rango(inicio: date, fin: date, dias: int) -> list[tuple[date, date]]:
    """Parte ``[inicio, fin]`` en tramos de como mucho `dias` días."""
    tramos: list[tuple[date, date]] = []
    actual = inicio
    while actual <= fin:
        tramo_fin = min(actual + timedelta(days=dias - 1), fin)
        tramos.append((actual, tramo_fin))
        actual = tramo_fin + timedelta(days=1)
    return tramos


def peticiones_para(
    periodo: str, metric_id: str, entidad: str, inicio: date, fin: date
) -> list[Peticion]:
    """Genera los lotes necesarios para cubrir el rango sin pasarse de `MaxDays`."""
    dias = MAX_DIAS.get(periodo, 31)
    return [
        Peticion(periodo, metric_id, entidad, tramo_inicio, tramo_fin)
        for tramo_inicio, tramo_fin in partir_rango(inicio, fin, dias)
    ]


def ejecutar(peticion: Peticion) -> dict | None:
    """Lanza una petición con reintentos. `None` si XM rechaza esa métrica.

    Un `400` significa "esta métrica/entidad no existe o no está disponible":
    no es un fallo transitorio y reintentarlo solo gasta tiempo. Se devuelve
    `None` para que la descarga global continúe sin esa serie en vez de
    abortarse entera por una métrica que XM haya retirado.
    """
    ultimo_error: Exception | None = None

    for intento in range(1, REINTENTOS + 1):
        try:
            respuesta = _sesion().post(
                peticion.url, json=peticion.cuerpo, timeout=TIMEOUT_SEGUNDOS
            )
        except requests.RequestException as exc:
            ultimo_error = exc
            log.debug(
                "XM %s %s intento %d/%d: %s",
                peticion.metric_id,
                peticion.inicio,
                intento,
                REINTENTOS,
                exc,
            )
            continue

        if respuesta.status_code == 400:
            log.warning(
                "XM rechaza %s/%s: %s",
                peticion.metric_id,
                peticion.entidad,
                respuesta.text[:120],
            )
            return None

        if respuesta.status_code >= 500:
            ultimo_error = ErrorXM(f"HTTP {respuesta.status_code}")
            continue

        try:
            respuesta.raise_for_status()
            return respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            ultimo_error = exc

    log.warning(
        "XM: %s/%s [%s..%s] falló tras %d intentos (%s)",
        peticion.metric_id,
        peticion.entidad,
        peticion.inicio,
        peticion.fin,
        REINTENTOS,
        ultimo_error,
    )
    return None


def ejecutar_todas(peticiones: Iterable[Peticion]) -> Iterator[tuple[Peticion, dict]]:
    """Ejecuta las peticiones en paralelo y va soltando las que respondieron.

    Se omiten silenciosamente las que devolvieron `None` (métrica rechazada o
    agotados los reintentos): el `log` ya dejó constancia.
    """
    peticiones = list(peticiones)
    if not peticiones:
        return

    with ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
        for peticion, payload in zip(peticiones, pool.map(ejecutar, peticiones), strict=True):
            if payload is not None:
                yield peticion, payload


# ---------------------------------------------------------------------------
# Aplanado de respuestas
# ---------------------------------------------------------------------------


def aplanar_horaria(payload: dict, columna: str, *, por_entidad: bool = False) -> pd.DataFrame:
    """Convierte ``Values.Hour01..Hour24`` en una fila por hora.

    XM numera las horas 1..24, donde ``Hour01`` es el bloque que empieza a las
    00:00. Por eso el desplazamiento es ``hora - 1`` y no ``hora``.

    Args:
        payload: respuesta cruda de ``POST /hourly``.
        columna: nombre de la columna destino con el valor.
        por_entidad: si `True`, se conserva el código de entidad en la columna
            `entidad` (necesario para las series desagregadas por mercado o por
            recurso). Si `False`, se promedia sobre las entidades, que es lo
            correcto cuando solo hay una (``Sistema``).
    """
    filas: list[dict] = []

    for item in payload.get("Items") or []:
        fecha_txt = item.get("Date")
        if not fecha_txt:
            continue
        fecha = pd.to_datetime(fecha_txt).normalize()

        for entidad in item.get("HourlyEntities") or []:
            valores = entidad.get("Values") or {}
            codigo = valores.get("code") or entidad.get("Id")

            for clave, valor in valores.items():
                if not clave.lower().startswith("hour"):
                    continue
                try:
                    hora = int(clave[4:])
                except ValueError:
                    continue

                fila = {
                    "fecha_hora": fecha + pd.Timedelta(hours=hora - 1),
                    columna: pd.to_numeric(valor, errors="coerce"),
                }
                if por_entidad:
                    fila["entidad"] = codigo
                filas.append(fila)

    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    claves = ["fecha_hora", "entidad"] if por_entidad else ["fecha_hora"]
    return df.groupby(claves, as_index=False)[columna].mean().sort_values(claves)


def aplanar_por_valor(
    payload: dict, columna: str, clave_entidades: str, *, por_entidad: bool = False
) -> pd.DataFrame:
    """Aplana las respuestas de ``/daily`` y ``/monthly`` (un `Value` por fila)."""
    filas: list[dict] = []

    for item in payload.get("Items") or []:
        fecha_txt = item.get("Date")
        if not fecha_txt:
            continue
        fecha = pd.to_datetime(fecha_txt).normalize()

        for entidad in item.get(clave_entidades) or []:
            valor = entidad.get("Value")
            if valor is None or valor == "":
                continue
            fila = {"fecha_hora": fecha, columna: pd.to_numeric(valor, errors="coerce")}
            if por_entidad:
                fila["entidad"] = (entidad.get("Values") or {}).get("code") or entidad.get("Id")
            filas.append(fila)

    if not filas:
        return pd.DataFrame()

    df = pd.DataFrame(filas)
    claves = ["fecha_hora", "entidad"] if por_entidad else ["fecha_hora"]
    return df.groupby(claves, as_index=False)[columna].mean().sort_values(claves)


def aplanar_diaria(payload: dict, columna: str, *, por_entidad: bool = False) -> pd.DataFrame:
    return aplanar_por_valor(payload, columna, "DailyEntities", por_entidad=por_entidad)


def aplanar_mensual(payload: dict, columna: str, *, por_entidad: bool = False) -> pd.DataFrame:
    return aplanar_por_valor(payload, columna, "MonthlyEntities", por_entidad=por_entidad)


def descargar_catalogo(metric_id: str, entidad: str = "Sistema") -> pd.DataFrame:
    """Descarga un catálogo de ``POST /lists`` (recursos, agentes, embalses...).

    Los catálogos ignoran el rango de fechas, pero la API lo exige igualmente.
    """
    hoy = date.today()
    payload = ejecutar(Peticion("lists", metric_id, entidad, hoy - timedelta(days=1), hoy))
    if not payload:
        return pd.DataFrame()

    filas = [
        entrada.get("Values") or {}
        for item in payload.get("Items") or []
        for entrada in item.get("ListEntities") or []
    ]
    return pd.DataFrame(filas) if filas else pd.DataFrame()


def concatenar(trozos: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Une los `DataFrame` no vacíos. Devuelve uno vacío si no hay ninguno."""
    utiles = [t for t in trozos if t is not None and not t.empty]
    return pd.concat(utiles, ignore_index=True) if utiles else pd.DataFrame()
