"""Cliente de la API pública de XM (operador del mercado eléctrico colombiano).

XM expone en ``https://servapibi.xm.com.co`` un servicio REST **sin API key**
(el mismo que consume el paquete oficial ``pydataxm``). Los identificadores y la
estructura de respuesta de este módulo se verificaron contra la API en vivo.

Dos endpoints con formatos distintos:

``POST /hourly``
    ``Items[].HourlyEntities[].Values`` = ``{"code": ..., "Hour01": ..., ...,
    "Hour24": ...}``. Una fila por día con las 24 horas como campos.

``POST /daily``
    ``Items[].DailyEntities[].Value`` = un único valor por día.

Métricas usadas (todas comprobadas):

======================  ========  ==================================================
MetricId                Periodo   Significado
======================  ========  ==================================================
``PrecBolsNaci``        horario   Precio de bolsa nacional (COP/kWh) — **objetivo**
``DemaReal``            horario   Demanda real del sistema (kWh)
``DemaCome``            horario   Demanda comercial (kWh)
``Gene``                horario   Generación total del sistema (kWh)
``GeneIdea``            horario   Generación ideal, sin restricciones (kWh)
``AporEner``            diario    Aportes hídricos de energía (kWh)
``VoluUtilDiarEner``    diario    Volumen útil de los embalses (kWh)
``CapaUtilDiarEner``    diario    Capacidad útil total de los embalses (kWh)
``PrecEscaAct``         diario    Precio de escasez de activación (COP/kWh)
======================  ========  ==================================================

Las series diarias se propagan a las 24 horas del día correspondiente. Es lo
correcto conceptualmente: el volumen de un embalse es un estado diario, no una
magnitud horaria, y durante ese día es el mismo para todas las horas.

Si la API no responde, el cliente cae a un CSV de ejemplo **simulado**, de modo
que el proyecto siempre sea ejecutable sin depender de un servicio externo.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from src.core.config import settings
from src.core.logging import get_logger
from src.data_collection.base import ErrorRecoleccion, Recolector

log = get_logger(__name__)

RUTA_SAMPLES = Path(__file__).parent / "samples"
CSV_EJEMPLO = RUTA_SAMPLES / "xm_historico_ejemplo.csv"

#: Métricas horarias: MetricId -> columna destino.
METRICAS_HORARIAS: dict[str, str] = {
    "PrecBolsNaci": "precio_bolsa",
    "DemaReal": "demanda_real",
    "DemaCome": "demanda_comercial",
    "Gene": "generacion_total",
    "GeneIdea": "generacion_ideal",
}

#: Métricas diarias: MetricId -> columna destino.
METRICAS_DIARIAS: dict[str, str] = {
    "AporEner": "aportes_hidricos",
    "VoluUtilDiarEner": "volumen_util_energia",
    "CapaUtilDiarEner": "capacidad_util_energia",
    "PrecEscaAct": "precio_escasez",
}

ENTIDAD = "Sistema"
#: XM limita el rango por consulta; troceamos en lotes de 30 días.
DIAS_POR_LOTE = 30
TIMEOUT_SEGUNDOS = 60


class XMClient(Recolector):
    """Descarga series del mercado eléctrico colombiano y las unifica a resolución horaria."""

    nombre = "XM"

    def __init__(
        self,
        url_base: str | None = None,
        usar_respaldo: bool = True,
        timeout: int = TIMEOUT_SEGUNDOS,
    ) -> None:
        self.url_base = (url_base or settings.XM_API_URL).rstrip("/")
        self.usar_respaldo = usar_respaldo
        self.timeout = timeout
        self._sesion = requests.Session()

    # -- API pública --------------------------------------------------------

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Devuelve un `DataFrame` horario con todas las métricas del rango."""
        if fecha_inicio > fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

        try:
            df = self._descargar(fecha_inicio, fecha_fin)
            if not df.empty and "precio_bolsa" in df.columns:
                log.info("XM: %d registros horarios descargados", len(df))
                return df
            log.warning("XM no devolvió la métrica de precio para el rango pedido")
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.warning("XM no disponible (%s: %s)", type(exc).__name__, exc)

        if not self.usar_respaldo:
            raise ErrorRecoleccion("No se pudo obtener datos de XM y el respaldo está desactivado")

        log.info("Usando CSV de ejemplo (datos SIMULADOS) como respaldo")
        return self._cargar_respaldo(fecha_inicio, fecha_fin)

    # -- Descarga -----------------------------------------------------------

    def _descargar(self, inicio: date, fin: date) -> pd.DataFrame:
        resultado: pd.DataFrame | None = None

        for metric_id, columna in METRICAS_HORARIAS.items():
            serie = self._serie_horaria(metric_id, columna, inicio, fin)
            resultado = _fusionar(resultado, serie)

        for metric_id, columna in METRICAS_DIARIAS.items():
            serie = self._serie_diaria(metric_id, columna, inicio, fin)
            resultado = _fusionar(resultado, serie)

        if resultado is None or resultado.empty:
            return pd.DataFrame()

        resultado = resultado.sort_values("fecha_hora").reset_index(drop=True)
        resultado = _propagar_diarias(resultado)
        resultado = _derivar_columnas(resultado)
        resultado["fuente"] = self.nombre
        return resultado

    def _serie_horaria(
        self, metric_id: str, columna: str, inicio: date, fin: date
    ) -> pd.DataFrame:
        trozos = [
            _aplanar_horaria(payload, columna)
            for payload in self._peticiones("hourly", metric_id, inicio, fin)
        ]
        return _concatenar(trozos)

    def _serie_diaria(
        self, metric_id: str, columna: str, inicio: date, fin: date
    ) -> pd.DataFrame:
        trozos = [
            _aplanar_diaria(payload, columna)
            for payload in self._peticiones("daily", metric_id, inicio, fin)
        ]
        return _concatenar(trozos)

    def _peticiones(self, periodo: str, metric_id: str, inicio: date, fin: date):
        """Ejecuta las peticiones por lotes. Omite las métricas que XM rechace.

        Un `400` significa que ese identificador no está disponible; no debe
        tumbar la descarga completa, solo esa métrica.
        """
        for lote_inicio, lote_fin in _partir_rango(inicio, fin, DIAS_POR_LOTE):
            payload = {
                "MetricId": metric_id,
                "StartDate": lote_inicio.isoformat(),
                "EndDate": lote_fin.isoformat(),
                "Entity": ENTIDAD,
            }
            respuesta = self._sesion.post(
                f"{self.url_base}/{periodo}", json=payload, timeout=self.timeout
            )
            if respuesta.status_code == 400:
                log.warning("XM rechazó la métrica '%s': %s", metric_id, respuesta.text[:120])
                return
            respuesta.raise_for_status()
            yield respuesta.json()

    # -- Respaldo -----------------------------------------------------------

    @staticmethod
    def _cargar_respaldo(inicio: date, fin: date) -> pd.DataFrame:
        if not CSV_EJEMPLO.exists():
            raise ErrorRecoleccion(
                f"No hay datos de XM ni CSV de respaldo en {CSV_EJEMPLO}. "
                "Genéralo con: python scripts/generar_datos_ejemplo.py"
            )

        df = pd.read_csv(CSV_EJEMPLO, parse_dates=["fecha_hora"])
        mascara = (df["fecha_hora"].dt.date >= inicio) & (df["fecha_hora"].dt.date <= fin)
        recortado = df.loc[mascara].reset_index(drop=True)

        if recortado.empty:
            log.warning("El rango pedido no existe en el CSV de ejemplo; se devuelve completo")
            return df

        return recortado


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _partir_rango(inicio: date, fin: date, dias: int) -> list[tuple[date, date]]:
    """Parte [inicio, fin] en tramos de como mucho `dias` días."""
    tramos: list[tuple[date, date]] = []
    actual = inicio
    while actual <= fin:
        tramo_fin = min(actual + timedelta(days=dias - 1), fin)
        tramos.append((actual, tramo_fin))
        actual = tramo_fin + timedelta(days=1)
    return tramos


def _concatenar(trozos: list[pd.DataFrame]) -> pd.DataFrame:
    utiles = [t for t in trozos if not t.empty]
    return pd.concat(utiles, ignore_index=True) if utiles else pd.DataFrame()


def _fusionar(acumulado: pd.DataFrame | None, nuevo: pd.DataFrame) -> pd.DataFrame | None:
    if nuevo.empty:
        return acumulado
    if acumulado is None:
        return nuevo
    return acumulado.merge(nuevo, on="fecha_hora", how="outer")


def _aplanar_horaria(payload: dict, columna: str) -> pd.DataFrame:
    """Convierte ``Values.Hour01..Hour24`` en una fila por hora."""
    filas: list[dict] = []

    for item in payload.get("Items") or []:
        fecha_txt = item.get("Date")
        if not fecha_txt:
            continue
        fecha = pd.to_datetime(fecha_txt).normalize()

        for entidad in item.get("HourlyEntities") or []:
            for clave, valor in (entidad.get("Values") or {}).items():
                # Se ignora "code" y cualquier campo que no sea HourNN.
                if not clave.lower().startswith("hour"):
                    continue
                try:
                    hora = int(clave[4:])
                except ValueError:
                    continue
                # XM numera 1..24; Hour01 es las 00:00.
                filas.append(
                    {
                        "fecha_hora": fecha + pd.Timedelta(hours=hora - 1),
                        columna: pd.to_numeric(valor, errors="coerce"),
                    }
                )

    if not filas:
        return pd.DataFrame()

    return (
        pd.DataFrame(filas)
        .groupby("fecha_hora", as_index=False)[columna]
        .mean()
        .sort_values("fecha_hora")
    )


def _aplanar_diaria(payload: dict, columna: str) -> pd.DataFrame:
    """Convierte ``DailyEntities[].Value`` en una fila por día (a las 00:00)."""
    filas: list[dict] = []

    for item in payload.get("Items") or []:
        fecha_txt = item.get("Date")
        if not fecha_txt:
            continue
        fecha = pd.to_datetime(fecha_txt).normalize()

        for entidad in item.get("DailyEntities") or []:
            valor = entidad.get("Value")
            if valor is None:
                continue
            filas.append({"fecha_hora": fecha, columna: pd.to_numeric(valor, errors="coerce")})

    if not filas:
        return pd.DataFrame()

    return (
        pd.DataFrame(filas)
        .groupby("fecha_hora", as_index=False)[columna]
        .mean()
        .sort_values("fecha_hora")
    )


def _propagar_diarias(df: pd.DataFrame) -> pd.DataFrame:
    """Extiende los valores diarios (fijados a las 00:00) a las 24 horas del día.

    Se usa `ffill` limitado a 23 horas: así el valor de un día nunca se filtra
    al día siguiente si ese día falta en la respuesta de XM.
    """
    columnas = [c for c in METRICAS_DIARIAS.values() if c in df.columns]
    if not columnas:
        return df

    df[columnas] = df[columnas].ffill(limit=23)
    return df


def _derivar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula variables derivadas con significado físico directo."""
    volumen = "volumen_util_energia"
    capacidad = "capacidad_util_energia"

    # Porcentaje de llenado de los embalses: el indicador que realmente se
    # sigue en el sector, más informativo que el volumen absoluto en kWh.
    if volumen in df.columns and capacidad in df.columns:
        df["volumen_util_embalse"] = (
            df[volumen] / df[capacidad].where(df[capacidad] > 0) * 100
        ).round(2)

    return df
