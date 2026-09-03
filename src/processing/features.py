"""Ingeniería de variables (*feature engineering*) para el pronóstico.

Cuatro familias de variables:

* **Calendario cíclico y festivos** — la hora 23 y la hora 0 son adyacentes,
  pero numéricamente distan 23. Codificarlas con seno/coseno le da al modelo esa
  continuidad; sin ello, los modelos lineales aprenden una relación falsa. A eso
  se suma el calendario festivo colombiano, que en demanda pesa muchísimo: un
  lunes festivo tiene el perfil de un domingo, no el de un lunes, y la ley
  Emiliani mueve la mitad de los festivos al lunes siguiente, así que no basta
  con una lista de fechas fijas.
* **Rezagos (*lags*) y ventanas móviles** — tanto el precio como la demanda
  tienen fuerte autocorrelación. El rezago de 24 h (misma hora del día anterior)
  y el de 168 h (misma hora de la semana anterior) suelen ser las variables más
  predictivas del conjunto.
* **Exógenas de mercado** — hidrología, mezcla de generación, restricciones y
  margen de reserva.
* **Clima y ENSO** — temperatura, precipitación acumulada e índice ONI.

Objetivo configurable
---------------------

`objetivo` decide qué se predice: `precio_bolsa` (el del trabajo de grado) o
`demanda_real`. No es un parámetro cosmético: cambia qué serie se rezaga, qué
variable queda excluida de las predictoras para no filtrar el presente, y qué
exógenas tienen sentido. Un solo camino de código para ambos objetivos evita
que las dos ramas se desincronicen.

.. warning::
   **Fuga de información (*data leakage*).** Todos los rezagos usan `shift()`
   hacia el pasado y todas las medias móviles se calculan sobre valores ya
   desplazados. Nunca se usa información del instante *t* (ni futura) para
   predecir *t*. Por el mismo motivo el *split* train/test es **cronológico**,
   nunca aleatorio.
"""

from __future__ import annotations

from functools import lru_cache

import holidays
import numpy as np
import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)

COLUMNA_TIEMPO = "fecha_hora"

#: Objetivos admitidos: ``nombre -> unidad``.
OBJETIVOS: dict[str, str] = {
    "precio_bolsa": "COP/kWh",
    "demanda_real": "kWh",
}

OBJETIVO_POR_DEFECTO = "precio_bolsa"

#: Rezagos en horas: horas recientes, medio día, día anterior, semana anterior.
LAGS_OBJETIVO = (1, 2, 3, 6, 12, 24, 48, 72, 168, 336)
#: Rezagos de las exógenas más informativas.
LAGS_EXOGENAS = (1, 24, 168)
#: Ventanas móviles en horas: día, semana, mes.
VENTANAS = (24, 168, 720)

#: Exógenas a las que se les calculan rezagos propios (además del objetivo).
EXOGENAS_REZAGADAS = ("demanda_real", "precio_bolsa", "generacion_total", "volumen_util_embalse")

#: Columnas que nunca entran al modelo como predictoras.
EXCLUIDAS_SIEMPRE = frozenset(
    {COLUMNA_TIEMPO, "objetivo", "fuente", "fenomeno_climatico", "id", "creado_en"}
)

#: Columnas que filtrarían el valor a predecir si entraran en crudo.
#:
#: `precio_bolsa_ponderado` y `precio_bolsa_tx1` son transformaciones del propio
#: precio publicadas por XM; `demanda_sin_diaria` y `demanda_maxima_potencia`
#: son agregados diarios que contienen la demanda de la hora que se quiere
#: predecir. Dejarlas dentro produciría un R² espectacular y un modelo inútil.
FUGA_POR_OBJETIVO: dict[str, frozenset[str]] = {
    "precio_bolsa": frozenset({"precio_bolsa_ponderado", "precio_bolsa_tx1", "costo_marginal"}),
    "demanda_real": frozenset(
        {
            "demanda_comercial",
            "demanda_regulada",
            "demanda_no_regulada",
            "demanda_sin_diaria",
            "demanda_maxima_potencia",
            "perdidas_energia",
            "generacion_total",
        }
    ),
}


def construir_features(
    df: pd.DataFrame,
    *,
    objetivo: str = OBJETIVO_POR_DEFECTO,
    horizonte: int = 24,
    eliminar_nulos: bool = True,
) -> pd.DataFrame:
    """Construye la matriz de variables predictoras y el objetivo.

    Args:
        df: datos ya limpios (salida de `limpieza.limpiar`).
        objetivo: columna a predecir (`precio_bolsa` o `demanda_real`).
        horizonte: cuántas horas hacia adelante se predice. 24 = "el valor de
            esta hora, mañana"; 168 = una semana; 720 = un mes.
        eliminar_nulos: descarta las primeras filas, que no tienen histórico
            suficiente para calcular los rezagos más largos.

    Returns:
        `DataFrame` con las features, `fecha_hora` y la columna `objetivo`.
    """
    validar_objetivo(objetivo)

    if df.empty:
        return df
    if objetivo not in df.columns:
        raise ValueError(f"Falta la columna objetivo '{objetivo}'")

    df = df.sort_values(COLUMNA_TIEMPO).reset_index(drop=True).copy()

    df = _features_calendario(df)
    df = _features_rezago(df, objetivo)
    df = _features_exogenas(df, objetivo)

    # Objetivo: el valor `horizonte` horas en el futuro.
    df["objetivo"] = df[objetivo].shift(-horizonte)

    if eliminar_nulos:
        antes = len(df)
        # Se descarta por las columnas que REALMENTE entran al modelo, no por
        # todas. Un `dropna()` sin `subset` vaciaría el conjunto entero en
        # cuanto una sola columna del esquema viniera sin datos.
        obligatorias = [*columnas_features(df, objetivo), "objetivo"]
        df = df.dropna(subset=obligatorias).reset_index(drop=True)
        log.info(
            "Features (%s, h=%d): %d filas -> %d tras descartar bordes",
            objetivo,
            horizonte,
            antes,
            len(df),
        )

    return df


def validar_objetivo(objetivo: str) -> None:
    if objetivo not in OBJETIVOS:
        raise ValueError(
            f"Objetivo '{objetivo}' desconocido. Disponibles: {sorted(OBJETIVOS)}"
        )


def unidad_de(objetivo: str) -> str:
    """Unidad en la que se lee el objetivo. Se guarda junto a cada predicción."""
    validar_objetivo(objetivo)
    return OBJETIVOS[objetivo]


def columnas_features(
    df: pd.DataFrame, objetivo: str = OBJETIVO_POR_DEFECTO
) -> list[str]:
    """Devuelve las columnas que entran al modelo.

    Excluye la marca de tiempo, el objetivo, las no numéricas, las que fugarían
    información del instante que se quiere predecir y las enteramente vacías.

    El objetivo en crudo se excluye siempre: usar el valor del instante *t* para
    predecir *t + horizonte* sería legítimo, pero se prefiere que entre solo a
    través de los rezagos explícitos para que quede documentado en la matriz.
    """
    excluidas = EXCLUIDAS_SIEMPRE | {objetivo} | FUGA_POR_OBJETIVO.get(objetivo, frozenset())

    return [
        c
        for c in df.columns
        if c not in excluidas
        and pd.api.types.is_numeric_dtype(df[c])
        # Una columna totalmente vacía no aporta señal y, de colarse, el
        # `dropna` posterior vaciaría el conjunto entero.
        and df[c].notna().any()
    ]


def dividir_train_test(
    df: pd.DataFrame, proporcion_test: float = 0.2
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Partición **cronológica** (no aleatoria) del conjunto.

    Con series temporales, `train_test_split(shuffle=True)` mete futuro en el
    conjunto de entrenamiento y produce métricas optimistas que no se sostienen
    en producción. El corte es siempre por fecha.
    """
    if not 0 < proporcion_test < 1:
        raise ValueError("proporcion_test debe estar entre 0 y 1")

    df = df.sort_values(COLUMNA_TIEMPO).reset_index(drop=True)
    corte = int(len(df) * (1 - proporcion_test))
    train, test = df.iloc[:corte].copy(), df.iloc[corte:].copy()

    log.info(
        "Split cronológico: train=%d (%s -> %s) | test=%d (%s -> %s)",
        len(train),
        train[COLUMNA_TIEMPO].min(),
        train[COLUMNA_TIEMPO].max(),
        len(test),
        test[COLUMNA_TIEMPO].min(),
        test[COLUMNA_TIEMPO].max(),
    )
    return train, test


# ---------------------------------------------------------------------------
# Bloques de features
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _festivos(anio_inicio: int, anio_fin: int) -> frozenset:
    """Festivos colombianos del rango, cacheados.

    Se usa el paquete `holidays` en lugar de una lista fija porque Colombia
    aplica la **ley Emiliani**: buena parte de los festivos se traslada al lunes
    siguiente, y esa fecha cambia cada año. Una lista escrita a mano queda mal
    justo en los días que más desplazan la demanda.
    """
    calendario = holidays.country_holidays(
        "CO", years=list(range(anio_inicio, anio_fin + 1))
    )
    return frozenset(calendario.keys())


def _features_calendario(df: pd.DataFrame) -> pd.DataFrame:
    ts = df[COLUMNA_TIEMPO]

    df["hora"] = ts.dt.hour
    df["dia_semana"] = ts.dt.dayofweek
    df["dia_mes"] = ts.dt.day
    df["mes"] = ts.dt.month
    df["trimestre"] = ts.dt.quarter
    df["semana_anio"] = ts.dt.isocalendar().week.astype(int)
    df["dia_anio"] = ts.dt.dayofyear
    df["es_fin_semana"] = (df["dia_semana"] >= 5).astype(int)

    # Temporada seca en Colombia (diciembre–marzo): menos aportes, precio alto.
    df["es_temporada_seca"] = df["mes"].isin([12, 1, 2, 3]).astype(int)

    # Festivos y vísperas: el perfil horario de un festivo se parece al de un
    # domingo, y el de la víspera ya se desvía por la tarde.
    festivos = _festivos(int(ts.dt.year.min()), int(ts.dt.year.max()))
    fechas = ts.dt.date
    df["es_festivo"] = fechas.isin(festivos).astype(int)
    df["es_vispera_festivo"] = (
        (ts + pd.Timedelta(days=1)).dt.date.isin(festivos).astype(int)
    )
    df["es_dia_laboral"] = (
        (df["es_fin_semana"] == 0) & (df["es_festivo"] == 0)
    ).astype(int)

    # Codificación cíclica
    for columna, periodo in (
        ("hora", 24),
        ("dia_semana", 7),
        ("mes", 12),
        ("dia_anio", 365),
    ):
        df[f"{columna}_sin"] = np.sin(2 * np.pi * df[columna] / periodo)
        df[f"{columna}_cos"] = np.cos(2 * np.pi * df[columna] / periodo)

    return df


def _features_rezago(df: pd.DataFrame, objetivo: str) -> pd.DataFrame:
    """Rezagos y ventanas móviles del objetivo y de las exógenas clave."""
    for lag in LAGS_OBJETIVO:
        df[f"objetivo_lag_{lag}"] = df[objetivo].shift(lag)

    for columna in EXOGENAS_REZAGADAS:
        if columna == objetivo or not _tiene_datos(df, columna):
            continue
        for lag in LAGS_EXOGENAS:
            df[f"{columna}_lag_{lag}"] = df[columna].shift(lag)

    # Medias/desviaciones móviles sobre la serie YA desplazada una hora, para
    # que la ventana nunca incluya el instante actual.
    pasado = df[objetivo].shift(1)
    for ventana in VENTANAS:
        df[f"objetivo_media_{ventana}h"] = pasado.rolling(ventana, min_periods=2).mean()
        df[f"objetivo_std_{ventana}h"] = pasado.rolling(ventana, min_periods=2).std()

    df["objetivo_max_24h"] = pasado.rolling(24, min_periods=2).max()
    df["objetivo_min_24h"] = pasado.rolling(24, min_periods=2).min()

    # Media de la misma hora en los últimos 7 días: el perfil horario típico
    # reciente. Es la variable que captura "a esta hora, últimamente, pasa esto"
    # sin arrastrar el nivel de otras horas del día. Se calcula promediando los
    # rezagos de 24, 48... 168 h en lugar de con `rolling().apply()`, que sobre
    # decenas de miles de filas ejecutaría una llamada Python por ventana.
    mismas_horas = pd.concat([df[objetivo].shift(24 * k) for k in range(1, 8)], axis=1)
    df["objetivo_media_misma_hora_7d"] = mismas_horas.mean(axis=1)

    # Variación relativa respecto a hace 24 h y 168 h: tendencia reciente y
    # comparación con la misma hora de la semana pasada.
    df["objetivo_var_24h"] = (
        df["objetivo_lag_1"] - df["objetivo_lag_24"]
    ) / df["objetivo_lag_24"].replace(0, np.nan)
    df["objetivo_var_168h"] = (
        df["objetivo_lag_24"] - df["objetivo_lag_168"]
    ) / df["objetivo_lag_168"].replace(0, np.nan)

    return df


def _tiene_datos(df: pd.DataFrame, columna: str) -> bool:
    """¿Existe la columna y contiene al menos un valor real?

    Distinguir «la columna no existe» de «existe pero está vacía» es lo que
    evita construir variables derivadas a partir de nada: una columna
    enteramente NaN generaría una derivada también NaN que después haría
    desaparecer todas las filas en el `dropna` final.
    """
    return columna in df.columns and df[columna].notna().any()


def _features_exogenas(df: pd.DataFrame, objetivo: str) -> pd.DataFrame:
    """Variables de mercado, hidrología y clima con significado físico."""
    # --- Mezcla de generación ---------------------------------------------
    tecnologias = [
        c
        for c in (
            "generacion_hidraulica",
            "generacion_termica",
            "generacion_solar",
            "generacion_eolica",
            "generacion_cogeneracion",
        )
        if _tiene_datos(df, c)
    ]
    if tecnologias:
        total_tecnologias = df[tecnologias].sum(axis=1)
        denominador = total_tecnologias.where(total_tecnologias > 0)
        for columna in tecnologias:
            # `fraccion_hidraulica` es el driver estructural del precio en
            # Colombia: cuanto menos agua entra en la mezcla, más caro sale el
            # último MWh despachado.
            df[f"fraccion_{columna.removeprefix('generacion_')}"] = df[columna] / denominador
        if {"generacion_hidraulica", "generacion_termica"} <= set(tecnologias):
            df["ratio_hidro_termica"] = df["generacion_hidraulica"] / df[
                "generacion_termica"
            ].where(df["generacion_termica"] > 0)

    # --- Holgura del sistema ----------------------------------------------
    # Margen de reserva: cuánta holgura tiene el sistema. Se usa la
    # disponibilidad real si existe y, si no, la generación ideal, que es el
    # equivalente que sí publica la API de XM cuando falta aquella.
    holgura = next(
        (c for c in ("disponibilidad_real", "generacion_ideal") if _tiene_datos(df, c)), None
    )
    if holgura and _tiene_datos(df, "demanda_real"):
        df["margen_reserva"] = np.where(
            df["demanda_real"] > 0,
            (df[holgura] - df["demanda_real"]) / df["demanda_real"],
            np.nan,
        )

    # Brecha entre lo que el sistema pudo generar y lo que generó: mide cuánto
    # pesan las restricciones de red, que empujan el precio al alza.
    if _tiene_datos(df, "generacion_ideal") and _tiene_datos(df, "generacion_total"):
        df["brecha_generacion"] = np.where(
            df["generacion_ideal"] > 0,
            (df["generacion_ideal"] - df["generacion_total"]) / df["generacion_ideal"],
            np.nan,
        )

    # Coste de las restricciones por kWh demandado: normaliza el importe en COP
    # para que sea comparable entre horas de demanda muy distinta.
    if _tiene_datos(df, "restricciones_sin_alivio") and _tiene_datos(df, "demanda_real"):
        df["restricciones_por_kwh"] = np.where(
            df["demanda_real"] > 0,
            df["restricciones_sin_alivio"] / df["demanda_real"],
            np.nan,
        )

    # --- Hidrología --------------------------------------------------------
    # Distancia al precio de escasez: cuando el precio de bolsa se acerca al de
    # escasez, el sistema entra en estrés y cambia de régimen. Se usa el precio
    # rezagado una hora para no filtrar el instante actual.
    if _tiene_datos(df, "precio_escasez") and _tiene_datos(df, "precio_bolsa"):
        df["ratio_precio_escasez"] = np.where(
            df["precio_escasez"] > 0,
            df["precio_bolsa"].shift(1) / df["precio_escasez"],
            np.nan,
        )

    # Aportes respecto de su media histórica: el indicador hidrológico que
    # anticipa el precio con semanas de antelación.
    if _tiene_datos(df, "aportes_hidricos") and _tiene_datos(df, "aportes_media_historica"):
        df["ratio_aportes_media"] = np.where(
            df["aportes_media_historica"] > 0,
            df["aportes_hidricos"] / df["aportes_media_historica"],
            np.nan,
        )

    # Tendencia del embalse: un nivel del 60 % subiendo y uno del 60 % bajando
    # son dos situaciones de mercado opuestas, y el nivel por sí solo no las
    # distingue.
    if _tiene_datos(df, "volumen_util_embalse"):
        nivel_pasado = df["volumen_util_embalse"].shift(1)
        df["embalse_var_7d"] = nivel_pasado - nivel_pasado.shift(24 * 7)
        df["embalse_var_30d"] = nivel_pasado - nivel_pasado.shift(24 * 30)

    # --- Clima y ENSO ------------------------------------------------------
    if _tiene_datos(df, "indice_oni"):
        df["es_el_nino"] = (df["indice_oni"] >= 0.5).astype(int)
        df["es_la_nina"] = (df["indice_oni"] <= -0.5).astype(int)
    elif "fenomeno_climatico" in df.columns:
        df["es_el_nino"] = (df["fenomeno_climatico"] == "EL_NINO").astype(int)
        df["es_la_nina"] = (df["fenomeno_climatico"] == "LA_NINA").astype(int)

    # Precipitación acumulada: la lluvia de ayer llena el embalse de hoy.
    if _tiene_datos(df, "precipitacion"):
        lluvia_pasada = df["precipitacion"].shift(1)
        df["precipitacion_acum_24h"] = lluvia_pasada.rolling(24, min_periods=1).sum()
        df["precipitacion_acum_168h"] = lluvia_pasada.rolling(168, min_periods=1).sum()
        df["precipitacion_acum_720h"] = lluvia_pasada.rolling(720, min_periods=1).sum()

    # Grados-día de refrigeración: la demanda no crece con la temperatura, crece
    # con lo que la temperatura excede el umbral de confort. Por debajo de él, la
    # relación es plana, y una variable lineal no puede representar eso.
    if _tiene_datos(df, "temperatura") and objetivo == "demanda_real":
        df["grados_refrigeracion"] = (df["temperatura"] - 22).clip(lower=0)

    return df
