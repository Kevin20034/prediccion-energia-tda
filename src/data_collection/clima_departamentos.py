"""Clima horario en la capital de cada departamento.

Para qué
--------

El mapa del fenómeno del Niño necesita saber si un departamento está más caliente
de lo normal *para él y para esta época del año*. Eso exige dos cosas que el
sistema no tenía: una serie de temperatura **por departamento** —hasta ahora solo
se guardaba un punto, Medellín— y suficiente historia para saber qué es "lo
normal" en cada sitio y cada mes.

Los dos endpoints de Open-Meteo
-------------------------------

Hacen falta los dos, y esto no es un detalle de implementación:

* ``archive-api`` sirve el reanálisis, que es el dato bueno para la historia,
  pero **publica con unos cinco días de retraso**.
* ``api.open-meteo.com/v1/forecast`` con ``past_days`` cubre justo esa cola
  reciente.

Con solo el archivo, el mapa de "la temperatura de ahora" mostraría siempre la de
hace una semana: exactamente el problema que la ingesta automática vino a
resolver, reintroducido por la puerta de atrás.

Paralelismo
-----------

33 departamentos son 33 peticiones. Lanzarlas todas a la vez hace que Open-Meteo
responda 429; se usa el mismo grado de concurrencia acotada que ya emplea
`xm_api` con XM.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import requests

from src.core.logging import get_logger
from src.data_collection.base import Recolector
from src.data_collection.clima_client import ClimaClient
from src.data_collection.departamentos import DEPARTAMENTOS

log = get_logger(__name__)

URL_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"

#: Peticiones simultáneas a Open-Meteo. Seis es lo que ya usa `xm_api` contra XM
#: y no dispara el límite por minuto del servicio.
CONCURRENCIA = 6

#: Días de retraso con los que publica el reanálisis. Todo lo posterior se pide
#: al endpoint de pronóstico, que sí cubre el pasado inmediato.
RETRASO_ARCHIVO_DIAS = 5

#: Tope de `past_days` que admite el endpoint de pronóstico.
MAX_PAST_DAYS = 92

TIMEOUT_SEGUNDOS = 30


class ClimaDepartamentosClient(Recolector):
    """Descarga el clima horario de las 33 capitales departamentales."""

    nombre = "Clima-Departamentos"

    def __init__(self, timeout: int = TIMEOUT_SEGUNDOS) -> None:
        self.timeout = timeout

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Clima horario por departamento en el rango pedido.

        Returns:
            `DataFrame` con `fecha_hora`, `codigo_dane`, `departamento`,
            `temperatura`, `precipitacion` y `humedad_relativa`.
        """
        if fecha_inicio > fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

        trozos: list[pd.DataFrame] = []
        with ThreadPoolExecutor(max_workers=CONCURRENCIA) as pool:
            futuros = {
                pool.submit(self._de_un_departamento, d, fecha_inicio, fecha_fin): d
                for d in DEPARTAMENTOS
            }
            for futuro in as_completed(futuros):
                departamento = futuros[futuro]
                try:
                    df = futuro.result()
                except Exception:  # noqa: BLE001 — un fallo no cancela a los demás
                    log.exception("Clima de %s: falló la descarga", departamento.nombre)
                    continue
                if not df.empty:
                    trozos.append(df)

        if not trozos:
            log.warning("Open-Meteo no devolvió clima para ningún departamento")
            return pd.DataFrame()

        completo = pd.concat(trozos, ignore_index=True)
        completo = completo.sort_values(["fecha_hora", "codigo_dane"]).reset_index(drop=True)

        log.info(
            "Clima: %d departamentos · %d horas",
            completo["codigo_dane"].nunique(),
            completo["fecha_hora"].nunique(),
        )
        return completo

    # -- por departamento ---------------------------------------------------

    def _de_un_departamento(self, departamento, inicio: date, fin: date) -> pd.DataFrame:
        """Une el tramo de archivo con el tramo reciente."""
        corte = date.today() - timedelta(days=RETRASO_ARCHIVO_DIAS)

        partes: list[pd.DataFrame] = []

        if inicio <= corte:
            cliente = ClimaClient(
                latitud=departamento.latitud,
                longitud=departamento.longitud,
                timeout=self.timeout,
            )
            # Se usa el descargador crudo y no `obtener`: el ONI es nacional y
            # mensual, así que adjuntarlo 33 veces sería descargarlo 33 veces
            # para escribir la misma columna.
            partes.append(cliente.descargar_open_meteo(inicio, min(fin, corte)))

        if fin > corte:
            partes.append(self._reciente(departamento, max(inicio, corte), fin))

        partes = [p for p in partes if not p.empty]
        if not partes:
            return pd.DataFrame()

        df = pd.concat(partes, ignore_index=True)
        # El solape entre archivo y pronóstico en el día del corte deja horas
        # repetidas; se queda la del archivo, que es reanálisis y no estimación.
        df = df.drop_duplicates(subset="fecha_hora", keep="first")

        df["codigo_dane"] = departamento.codigo
        df["departamento"] = departamento.nombre
        return df

    def _reciente(self, departamento, inicio: date, fin: date) -> pd.DataFrame:
        """Cola reciente que el reanálisis todavía no publica."""
        dias_atras = min((date.today() - inicio).days + 1, MAX_PAST_DAYS)

        params = {
            "latitude": departamento.latitud,
            "longitude": departamento.longitud,
            "past_days": max(dias_atras, 1),
            "forecast_days": 1,
            "hourly": "temperature_2m,precipitation,relative_humidity_2m",
            "timezone": "America/Bogota",
        }
        try:
            respuesta = requests.get(URL_PRONOSTICO, params=params, timeout=self.timeout)
            respuesta.raise_for_status()
            datos = respuesta.json().get("hourly") or {}
        except (requests.RequestException, ValueError) as exc:
            log.warning(
                "Clima reciente de %s no disponible (%s)", departamento.nombre, type(exc).__name__
            )
            return pd.DataFrame()

        if not datos.get("time"):
            return pd.DataFrame()

        df = pd.DataFrame(
            {
                "fecha_hora": pd.to_datetime(datos["time"]),
                "temperatura": datos.get("temperature_2m"),
                "precipitacion": datos.get("precipitation"),
                "humedad_relativa": datos.get("relative_humidity_2m"),
            }
        )
        # `past_days` cuenta días completos hacia atrás y suele traer de más.
        return df[(df["fecha_hora"].dt.date >= inicio) & (df["fecha_hora"].dt.date <= fin)]


# ---------------------------------------------------------------------------
# Anomalía
# ---------------------------------------------------------------------------


#: Columna auxiliar del cruce con las normales. No sale del módulo.
_MES = "_mes"


def normales_mensuales(clima: pd.DataFrame) -> pd.DataFrame:
    """La "normal" de cada sitio: `codigo_dane`, `_mes`, `media_mensual`.

    Es la media de ese **departamento** en ese **mes del año**, sobre toda la
    historia disponible. Las dos condiciones importan:

    * Por mes, porque comparar enero contra la media anual haría que todos los
      eneros salieran fríos: el mapa mostraría el calendario, no el fenómeno.
    * Por departamento, porque 26 °C es normal en Barranquilla y altísimo en
      Bogotá; una normal común pintaría la costa de rojo permanente.

    La observación evaluada entra en su propia normal, que es lo que significa
    "anomalía respecto a la media del periodo". Con más de dos mil horas por
    departamento y mes, el peso de una sola es despreciable.
    """
    df = clima.copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df[_MES] = df["fecha_hora"].dt.month

    return (
        df.groupby(["codigo_dane", _MES], as_index=False)["temperatura"]
        .mean()
        .rename(columns={"temperatura": "media_mensual"})
    )


def aplicar_anomalia(clima: pd.DataFrame, normales: pd.DataFrame) -> pd.DataFrame:
    """Cruza cada fila con la normal de su departamento y su mes, y resta.

    Separado de `normales_mensuales` porque las normales se pueden calcular de
    dos maneras según quién pregunte: en pandas cuando ya se tiene la serie en
    memoria, o con un `GROUP BY` cuando están en base de datos y traerse un
    millón de filas por petición no es una opción. Lo que **no** puede haber son
    dos definiciones de la resta; por eso vive aquí y solo aquí.
    """
    if clima.empty:
        return clima

    df = clima.copy()
    df["fecha_hora"] = pd.to_datetime(df["fecha_hora"])
    df[_MES] = df["fecha_hora"].dt.month

    df = df.merge(normales, on=["codigo_dane", _MES], how="left")
    df["anomalia"] = df["temperatura"] - df["media_mensual"]

    return df.drop(columns=[_MES])


def anomalia_mensual(clima: pd.DataFrame) -> pd.DataFrame:
    """Añade `media_mensual` y `anomalia` a una serie de clima completa."""
    if clima.empty:
        return clima

    return aplicar_anomalia(clima, normales_mensuales(clima))
