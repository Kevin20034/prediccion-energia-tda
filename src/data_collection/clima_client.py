"""Cliente de datos climáticos.

Dos fuentes, ambas públicas y **sin API key**:

* **Open-Meteo Archive API** — reanálisis histórico horario (temperatura,
  precipitación, humedad). Gratuita para uso no comercial, sin registro.
* **NOAA CPC** — índice ONI (*Oceanic Niño Index*), que es el estándar
  internacional para clasificar El Niño / La Niña. Es la variable que el
  trabajo de grado necesita para el factor "fenómenos climáticos".

Criterio de clasificación ONI (el que usa la NOAA):
``ONI >= +0.5`` → El Niño · ``ONI <= -0.5`` → La Niña · resto → Neutro.
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import requests

from src.core.config import settings
from src.core.logging import get_logger
from src.data_collection.base import Recolector

log = get_logger(__name__)

URL_OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"

#: Fichero **oficial** del ONI: media móvil de 3 meses de la anomalía en la
#: región Niño 3.4. Columnas: SEAS YR TOTAL ANOM.
URL_ONI_OFICIAL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

#: Respaldo: anomalía mensual (sin suavizar) de Niño 3.4. Columnas:
#: YR MON TOTAL ClimAdjust ANOM.
URL_ONI_MENSUAL = (
    "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/"
    "ensostuff/detrend.nino34.ascii.txt"
)

#: El ONI se publica por trimestres solapados. El mes representativo de cada
#: trimestre es el central: "DJF 1950" abarca dic-1949 a feb-1950 y se centra
#: en enero de 1950.
MES_CENTRAL_TRIMESTRE = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}

UMBRAL_NINO = 0.5
UMBRAL_NINA = -0.5
TIMEOUT_SEGUNDOS = 30


class ClimaClient(Recolector):
    """Descarga variables climáticas horarias y el índice ONI mensual."""

    nombre = "OpenMeteo"

    def __init__(
        self,
        latitud: float | None = None,
        longitud: float | None = None,
        timeout: int = TIMEOUT_SEGUNDOS,
    ) -> None:
        self.latitud = latitud if latitud is not None else settings.CLIMA_LATITUD
        self.longitud = longitud if longitud is not None else settings.CLIMA_LONGITUD
        self.timeout = timeout

    # -- API pública --------------------------------------------------------

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Devuelve temperatura, precipitación, humedad, ONI y fenómeno por hora."""
        clima = self._descargar_open_meteo(fecha_inicio, fecha_fin)
        if clima.empty:
            log.warning("Open-Meteo no devolvió datos; se continúa sin variables climáticas")
            return clima

        oni = self.descargar_oni()
        return _adjuntar_oni(clima, oni)

    # -- Open-Meteo ---------------------------------------------------------

    def _descargar_open_meteo(self, inicio: date, fin: date) -> pd.DataFrame:
        params = {
            "latitude": self.latitud,
            "longitude": self.longitud,
            "start_date": inicio.isoformat(),
            "end_date": fin.isoformat(),
            "hourly": "temperature_2m,precipitation,relative_humidity_2m",
            "timezone": "America/Bogota",
        }
        try:
            respuesta = requests.get(URL_OPEN_METEO, params=params, timeout=self.timeout)
            respuesta.raise_for_status()
            datos = respuesta.json().get("hourly") or {}
        except (requests.RequestException, ValueError) as exc:
            log.warning("Open-Meteo no disponible (%s: %s)", type(exc).__name__, exc)
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
        log.info("Open-Meteo: %d registros horarios descargados", len(df))
        return df

    # -- Índice ONI (NOAA) --------------------------------------------------

    def descargar_oni(self) -> pd.DataFrame:
        """Descarga la serie del índice ONI desde NOAA.

        Intenta primero el fichero oficial (media móvil trimestral, que es la
        definición formal del ONI) y, si falla, el de anomalía mensual.

        Returns:
            `DataFrame` con columnas `anio`, `mes`, `indice_oni`. Vacío si NOAA
            no responde (el pipeline sigue funcionando sin esta variable).
        """
        for url, parseador in (
            (URL_ONI_OFICIAL, _parsear_oni_trimestral),
            (URL_ONI_MENSUAL, _parsear_oni_mensual),
        ):
            try:
                respuesta = requests.get(url, timeout=self.timeout)
                respuesta.raise_for_status()
                oni = parseador(respuesta.text)
                if not oni.empty:
                    log.info("ONI: %d registros descargados de %s", len(oni), url.split("/")[-1])
                    return oni
                log.warning("El fichero %s no produjo registros", url.split("/")[-1])
            except requests.RequestException as exc:
                log.warning("No se pudo descargar %s (%s)", url.split("/")[-1], type(exc).__name__)
            except (ValueError, KeyError) as exc:
                log.warning("No se pudo interpretar %s: %s", url.split("/")[-1], exc)

        log.warning("ONI no disponible; el fenómeno climático quedará como NEUTRO")
        return pd.DataFrame(columns=["anio", "mes", "indice_oni"])


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _parsear_oni_trimestral(texto: str) -> pd.DataFrame:
    """Interpreta `oni.ascii.txt`: columnas SEAS YR TOTAL ANOM."""
    crudo = pd.read_csv(StringIO(texto), sep=r"\s+", engine="python")
    columnas = {c.upper().strip(): c for c in crudo.columns}

    col_seas, col_anio, col_anom = (
        columnas.get("SEAS"),
        columnas.get("YR"),
        columnas.get("ANOM"),
    )
    if not all([col_seas, col_anio, col_anom]):
        raise ValueError(f"formato inesperado, columnas: {list(crudo.columns)}")

    oni = pd.DataFrame(
        {
            "anio": pd.to_numeric(crudo[col_anio], errors="coerce"),
            "mes": crudo[col_seas].astype(str).str.upper().map(MES_CENTRAL_TRIMESTRE),
            "indice_oni": pd.to_numeric(crudo[col_anom], errors="coerce"),
        }
    ).dropna()

    oni["anio"] = oni["anio"].astype(int)
    oni["mes"] = oni["mes"].astype(int)
    return oni


def _parsear_oni_mensual(texto: str) -> pd.DataFrame:
    """Interpreta `detrend.nino34.ascii.txt`: columnas YR MON TOTAL ClimAdjust ANOM."""
    crudo = pd.read_csv(StringIO(texto), sep=r"\s+", engine="python")
    columnas = {c.upper().strip(): c for c in crudo.columns}

    col_anio, col_mes, col_anom = (
        columnas.get("YR"),
        columnas.get("MON"),
        columnas.get("ANOM"),
    )
    if not all([col_anio, col_mes, col_anom]):
        raise ValueError(f"formato inesperado, columnas: {list(crudo.columns)}")

    oni = crudo[[col_anio, col_mes, col_anom]].copy()
    oni.columns = ["anio", "mes", "indice_oni"]
    oni = oni.apply(pd.to_numeric, errors="coerce").dropna()
    oni["anio"] = oni["anio"].astype(int)
    oni["mes"] = oni["mes"].astype(int)
    return oni


def clasificar_fenomeno(indice_oni: float | None) -> str:
    """Traduce un valor ONI a la categoría del fenómeno climático."""
    if indice_oni is None or pd.isna(indice_oni):
        return "NEUTRO"
    if indice_oni >= UMBRAL_NINO:
        return "EL_NINO"
    if indice_oni <= UMBRAL_NINA:
        return "LA_NINA"
    return "NEUTRO"


def _adjuntar_oni(clima: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    """Cruza la serie horaria de clima con el ONI mensual."""
    clima = clima.copy()

    if oni.empty:
        clima["indice_oni"] = pd.NA
        clima["fenomeno_climatico"] = "NEUTRO"
        return clima

    clima["anio"] = clima["fecha_hora"].dt.year
    clima["mes"] = clima["fecha_hora"].dt.month
    clima = clima.merge(oni, on=["anio", "mes"], how="left")
    clima["fenomeno_climatico"] = clima["indice_oni"].apply(clasificar_fenomeno)
    return clima.drop(columns=["anio", "mes"])
