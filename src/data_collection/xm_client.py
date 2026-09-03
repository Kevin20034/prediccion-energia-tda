"""Cliente de la API pública de XM — series del Sistema Interconectado Nacional.

XM expone en ``https://servapibi.xm.com.co`` un servicio REST **sin API key**
(el mismo que consume el paquete oficial ``pydataxm``). El transporte, el
troceado por lotes y el aplanado viven en `xm_api`; aquí se decide *qué*
métricas se piden y *qué significan*.

Todos los identificadores de este módulo se verificaron contra la API en vivo:
las métricas que XM tiene publicadas pero devuelven vacío (``PrecTransBolsa``,
``CapaUtilDiarMasa``) están deliberadamente fuera.

Familias de variables
---------------------

**Mercado y precio** (horarias)
    Precio de bolsa —la variable objetivo—, precio de oferta máximo, costo
    marginal del despacho, precios promedio de contratos y precio TX1.

**Demanda** (horarias)
    Real, comercial y su desglose regulado / no regulado. La brecha entre real
    y comercial mide pérdidas y desviaciones del sistema.

**Generación y disponibilidad** (horarias)
    Total, ideal (sin restricciones) y —vía el cruce con el catálogo de
    recursos— el desglose por tecnología: hidráulica, térmica, solar, eólica y
    cogeneración. Ese desglose es la variable estructural que más explica el
    precio en Colombia, y hasta ahora el proyecto la tenía vacía porque XM no
    la publica agregada: hay que agregarla planta a planta.

**Restricciones y emisiones** (horarias)
    Restricciones con y sin alivio, pérdidas, importaciones/exportaciones y
    factor de emisión de CO₂ equivalente.

**Hidrología y escasez** (diarias, propagadas a las 24 horas del día)
    Aportes, aportes respecto de la media histórica, volumen útil de embalses
    en energía y en porcentaje, vertimientos y la familia de precios de
    escasez. Un estado diario es el mismo durante todo el día: propagarlo es lo
    correcto, no una interpolación de conveniencia.

Si la API no responde, el cliente cae a un CSV de ejemplo **simulado** para que
el proyecto siga siendo ejecutable sin depender de un servicio externo.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.core.logging import get_logger
from src.data_collection import xm_api
from src.data_collection.base import ErrorRecoleccion, Recolector

log = get_logger(__name__)

RUTA_SAMPLES = Path(__file__).parent / "samples"
CSV_EJEMPLO = RUTA_SAMPLES / "xm_historico_ejemplo.csv"

ENTIDAD_SISTEMA = "Sistema"
ENTIDAD_RECURSO = "Recurso"

#: Métricas horarias del sistema: ``MetricId -> columna destino``.
METRICAS_HORARIAS: dict[str, str] = {
    # Precio y mercado
    "PrecBolsNaci": "precio_bolsa",
    "PrecBolsNaciTX1": "precio_bolsa_tx1",
    "MaxPrecOferNal": "precio_oferta_maximo",
    "CostMargDesp": "costo_marginal",
    "PrecPromContRegu": "precio_contratos_regulado",
    "PrecPromContNoRegu": "precio_contratos_no_regulado",
    # Demanda
    "DemaReal": "demanda_real",
    "DemaCome": "demanda_comercial",
    "DemaComeReg": "demanda_regulada",
    "DemaComeNoReg": "demanda_no_regulada",
    # Generación
    "Gene": "generacion_total",
    "GeneIdea": "generacion_ideal",
    # Sistema
    "PerdidasEner": "perdidas_energia",
    "RestAliv": "restricciones_aliviadas",
    "RestSinAliv": "restricciones_sin_alivio",
    "factorEmisionCO2e": "factor_emision_co2",
    "ExpoEner": "exportaciones_energia",
    "ImpoEner": "importaciones_energia",
    # Transacciones
    "CompBolsNaciEner": "compras_bolsa_energia",
    "CompContEner": "compras_contratos_energia",
}

#: Métricas diarias del sistema: ``MetricId -> columna destino``.
METRICAS_DIARIAS: dict[str, str] = {
    "AporEner": "aportes_hidricos",
    "AporEnerMediHist": "aportes_media_historica",
    "PorcApor": "porcentaje_aportes",
    "VoluUtilDiarEner": "volumen_util_energia",
    "CapaUtilDiarEner": "capacidad_util_energia",
    "PorcVoluUtilDiar": "porcentaje_volumen_util",
    "VertEner": "vertimientos_energia",
    "PrecEscaAct": "precio_escasez",
    "PrecEsca": "precio_escasez_base",
    "PrecEscaMarg": "precio_escasez_marginal",
    "DemaSIN": "demanda_sin_diaria",
    "DemaMaxPot": "demanda_maxima_potencia",
    "PPPrecBolsNaci": "precio_bolsa_ponderado",
    "DeltaNal": "delta_nacional",
}

#: Tipo de recurso de XM -> columna de generación. `ListadoRecursos` mezcla
#: mayúsculas y minúsculas en `Type` ("SOLAR" y "Solar" conviven), así que la
#: clave se normaliza a mayúsculas antes de buscar aquí.
TECNOLOGIAS: dict[str, str] = {
    "HIDRAULICA": "generacion_hidraulica",
    "TERMICA": "generacion_termica",
    "SOLAR": "generacion_solar",
    "EOLICA": "generacion_eolica",
    "COGENERADOR": "generacion_cogeneracion",
}

#: Todas las columnas numéricas que este cliente puede producir.
COLUMNAS_XM: tuple[str, ...] = (
    *METRICAS_HORARIAS.values(),
    *METRICAS_DIARIAS.values(),
    *TECNOLOGIAS.values(),
    "disponibilidad_real",
    "volumen_util_embalse",
)


class XMClient(Recolector):
    """Descarga las series del mercado eléctrico colombiano a resolución horaria."""

    nombre = "XM"

    def __init__(
        self,
        usar_respaldo: bool = True,
        incluir_tecnologias: bool = True,
    ) -> None:
        """
        Args:
            usar_respaldo: si se cae al CSV simulado cuando XM no responde.
            incluir_tecnologias: si se descarga la generación planta a planta
                para agregarla por tecnología. Es la parte más pesada de la
                descarga (una fila por recurso, hora y día), así que se puede
                desactivar para ingestas rápidas.
        """
        self.usar_respaldo = usar_respaldo
        self.incluir_tecnologias = incluir_tecnologias
        self._catalogo_recursos: pd.DataFrame | None = None

    # -- API pública --------------------------------------------------------

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Devuelve un `DataFrame` horario con todas las métricas del rango."""
        if fecha_inicio > fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

        try:
            df = self._descargar(fecha_inicio, fecha_fin)
            if not df.empty and "precio_bolsa" in df.columns:
                log.info(
                    "XM: %d registros horarios · %d variables",
                    len(df),
                    len([c for c in df.columns if c != "fecha_hora"]),
                )
                return df
            log.warning("XM no devolvió la métrica de precio para el rango pedido")
        except Exception as exc:  # noqa: BLE001 - cualquier fallo debe caer al respaldo
            log.warning("XM no disponible (%s: %s)", type(exc).__name__, exc)

        if not self.usar_respaldo:
            raise ErrorRecoleccion("No se pudo obtener datos de XM y el respaldo está desactivado")

        log.info("Usando CSV de ejemplo (datos SIMULADOS) como respaldo")
        return self._cargar_respaldo(fecha_inicio, fecha_fin)

    def catalogo_recursos(self) -> pd.DataFrame:
        """Catálogo de plantas con su tecnología. Se descarga una sola vez."""
        if self._catalogo_recursos is None:
            catalogo = xm_api.descargar_catalogo("ListadoRecursos")
            if not catalogo.empty and "Type" in catalogo.columns:
                catalogo = catalogo.assign(
                    tecnologia=catalogo["Type"].astype(str).str.upper().str.strip()
                )
            self._catalogo_recursos = catalogo
            log.info("Catálogo de recursos: %d plantas", len(catalogo))
        return self._catalogo_recursos

    # -- Descarga -----------------------------------------------------------

    def _descargar(self, inicio: date, fin: date) -> pd.DataFrame:
        resultado = self._series_sistema(inicio, fin)

        if self.incluir_tecnologias:
            resultado = _fusionar(resultado, self._generacion_por_tecnologia(inicio, fin))
            resultado = _fusionar(resultado, self._disponibilidad(inicio, fin))

        if resultado is None or resultado.empty:
            return pd.DataFrame()

        resultado = resultado.sort_values("fecha_hora").reset_index(drop=True)
        resultado = _propagar_diarias(resultado)
        resultado = _derivar_columnas(resultado)
        resultado["fuente"] = self.nombre
        return resultado

    def _series_sistema(self, inicio: date, fin: date) -> pd.DataFrame | None:
        """Descarga en paralelo todas las métricas horarias y diarias del sistema.

        Todas las peticiones se lanzan juntas —horarias y diarias mezcladas—
        para que el pool se llene y el tiempo total lo marque el lote más lento
        y no la suma de familias.
        """
        peticiones: list[xm_api.Peticion] = []
        destino: dict[tuple[str, str], str] = {}

        for periodo, metricas in (
            ("hourly", METRICAS_HORARIAS),
            ("daily", METRICAS_DIARIAS),
        ):
            for metric_id, columna in metricas.items():
                destino[(periodo, metric_id)] = columna
                peticiones.extend(
                    xm_api.peticiones_para(periodo, metric_id, ENTIDAD_SISTEMA, inicio, fin)
                )

        trozos: dict[str, list[pd.DataFrame]] = {}
        for peticion, payload in xm_api.ejecutar_todas(peticiones):
            columna = destino[(peticion.periodo, peticion.metric_id)]
            aplanar = (
                xm_api.aplanar_horaria if peticion.periodo == "hourly" else xm_api.aplanar_diaria
            )
            trozo = aplanar(payload, columna)
            if not trozo.empty:
                trozos.setdefault(columna, []).append(trozo)

        resultado: pd.DataFrame | None = None
        for columna, partes in trozos.items():
            serie = xm_api.concatenar(partes)
            if serie.empty:
                continue
            serie = serie.groupby("fecha_hora", as_index=False)[columna].mean()
            resultado = _fusionar(resultado, serie)

        return resultado

    def _generacion_por_tecnologia(self, inicio: date, fin: date) -> pd.DataFrame:
        """Agrega ``Gene`` por recurso en columnas por tecnología.

        XM publica la generación planta a planta, no por fuente. El cruce con
        `ListadoRecursos` es lo que convierte 2.000 códigos opacos en las cinco
        variables que de verdad explican el precio: cuánto de lo que se generó
        vino del agua, del gas/carbón, del sol, del viento o de cogeneración.
        """
        catalogo = self.catalogo_recursos()
        if catalogo.empty or "tecnologia" not in catalogo.columns:
            log.warning("Sin catálogo de recursos: no se puede desglosar la generación")
            return pd.DataFrame()

        tecnologia_de = dict(zip(catalogo["Code"], catalogo["tecnologia"], strict=False))

        peticiones = xm_api.peticiones_para("hourly", "Gene", ENTIDAD_RECURSO, inicio, fin)
        trozos = [
            xm_api.aplanar_horaria(payload, "valor", por_entidad=True)
            for _, payload in xm_api.ejecutar_todas(peticiones)
        ]

        crudo = xm_api.concatenar(trozos)
        if crudo.empty:
            return pd.DataFrame()

        crudo["columna"] = (
            crudo["entidad"].map(tecnologia_de).map(TECNOLOGIAS)  # type: ignore[arg-type]
        )
        # Los recursos sin tecnología conocida (códigos nuevos que aún no están
        # en el catálogo) se descartan del desglose: inventarles una fuente
        # sería peor que dejar la columna sin ellos.
        desconocidos = int(crudo["columna"].isna().sum())
        if desconocidos:
            log.debug("%d registros de generación con recurso no catalogado", desconocidos)
        crudo = crudo.dropna(subset=["columna"])
        if crudo.empty:
            return pd.DataFrame()

        pivot = (
            crudo.pivot_table(
                index="fecha_hora", columns="columna", values="valor", aggfunc="sum"
            )
            .reset_index()
            .rename_axis(None, axis=1)
        )
        log.info("Generación desglosada en %d tecnologías", len(pivot.columns) - 1)
        return pivot

    def _disponibilidad(self, inicio: date, fin: date) -> pd.DataFrame:
        """Suma ``DispoReal`` de todos los recursos: la holgura real del sistema."""
        peticiones = xm_api.peticiones_para("hourly", "DispoReal", ENTIDAD_RECURSO, inicio, fin)
        trozos = [
            xm_api.aplanar_horaria(payload, "disponibilidad_real", por_entidad=True)
            for _, payload in xm_api.ejecutar_todas(peticiones)
        ]

        crudo = xm_api.concatenar(trozos)
        if crudo.empty:
            return pd.DataFrame()

        return (
            crudo.groupby("fecha_hora", as_index=False)["disponibilidad_real"]
            .sum()
            .sort_values("fecha_hora")
        )

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


def _fusionar(acumulado: pd.DataFrame | None, nuevo: pd.DataFrame) -> pd.DataFrame | None:
    if nuevo is None or nuevo.empty:
        return acumulado
    if acumulado is None or acumulado.empty:
        return nuevo
    return acumulado.merge(nuevo, on="fecha_hora", how="outer")


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


#: Métricas cuyo hueco significa "no hubo flujo", no "no se sabe".
#:
#: XM devuelve cadena vacía en las horas sin intercambio internacional. Dejarlas
#: como nulo haría que la imputación temporal inventara importaciones donde
#: sencillamente no las hubo.
COLUMNAS_CERO_SI_FALTA: tuple[str, ...] = (
    "importaciones_energia",
    "exportaciones_energia",
    "vertimientos_energia",
)


def _derivar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula variables derivadas con significado físico directo."""
    for columna in COLUMNAS_CERO_SI_FALTA:
        if columna in df.columns:
            df[columna] = df[columna].fillna(0.0)

    # `PrecEscaAct` dejó de publicarse: XM devuelve `Items: []` para los rangos
    # recientes. `PrecEsca` es el precio de escasez vigente y ocupa su lugar
    # cuando el primero viene vacío, de modo que las variables derivadas del
    # precio de escasez siguen existiendo tanto en el histórico antiguo como en
    # los datos nuevos.
    if "precio_escasez_base" in df.columns:
        if "precio_escasez" not in df.columns:
            df["precio_escasez"] = df["precio_escasez_base"]
        else:
            df["precio_escasez"] = df["precio_escasez"].fillna(df["precio_escasez_base"])

    # Porcentaje de llenado de los embalses: el indicador que de verdad se sigue
    # en el sector. XM lo publica ya calculado (`PorcVoluUtilDiar`, en fracción),
    # así que se prefiere ese al cociente propio, que arrastra el error de dos
    # series distintas. El cociente queda como respaldo.
    if "porcentaje_volumen_util" in df.columns and df["porcentaje_volumen_util"].notna().any():
        df["volumen_util_embalse"] = (df["porcentaje_volumen_util"] * 100).round(2)
    elif {"volumen_util_energia", "capacidad_util_energia"} <= set(df.columns):
        capacidad = df["capacidad_util_energia"].where(df["capacidad_util_energia"] > 0)
        df["volumen_util_embalse"] = (df["volumen_util_energia"] / capacidad * 100).round(2)

    return df
