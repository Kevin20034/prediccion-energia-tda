"""Ingeniería de variables (*feature engineering*) para la predicción de precio.

Tres familias de variables:

* **Calendario cíclico** — la hora 23 y la hora 0 son adyacentes, pero
  numéricamente distan 23. Codificarlas con seno/coseno le da al modelo esa
  continuidad; sin ello, los modelos lineales aprenden una relación falsa.
* **Rezagos (*lags*) y ventanas móviles** — el precio de la energía tiene
  fuerte autocorrelación. `precio_lag_24` (mismo hora del día anterior) y
  `precio_lag_168` (misma hora de la semana anterior) suelen ser las variables
  más predictivas del conjunto.
* **Exógenas** — demanda, hidrología, clima y fenómeno ENSO.

.. warning::
   **Fuga de información (*data leakage*).** Todos los rezagos usan `shift()`
   hacia el pasado y todas las medias móviles se calculan sobre valores ya
   desplazados. Nunca se usa información del instante *t* (ni futura) para
   predecir *t*. Por el mismo motivo el *split* train/test es **cronológico**,
   nunca aleatorio.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)

COLUMNA_TIEMPO = "fecha_hora"
COLUMNA_OBJETIVO = "precio_bolsa"

#: Rezagos en horas: última hora, medio día, día anterior, semana anterior.
LAGS_PRECIO = (1, 2, 3, 6, 12, 24, 48, 168)
LAGS_DEMANDA = (1, 24, 168)
#: Ventanas móviles en horas: día, semana, mes.
VENTANAS = (24, 168, 720)


def construir_features(
    df: pd.DataFrame,
    *,
    horizonte: int = 24,
    eliminar_nulos: bool = True,
) -> pd.DataFrame:
    """Construye la matriz de variables predictoras y el objetivo.

    Args:
        df: datos ya limpios (salida de `limpieza.limpiar`).
        horizonte: cuántas horas hacia adelante se predice. 24 = "el precio de
            esta hora, mañana", que es el caso de uso del trabajo de grado.
        eliminar_nulos: descarta las primeras filas, que no tienen histórico
            suficiente para calcular los rezagos más largos.

    Returns:
        `DataFrame` con las features, `fecha_hora` y la columna `objetivo`.
    """
    if df.empty:
        return df
    if COLUMNA_OBJETIVO not in df.columns:
        raise ValueError(f"Falta la columna objetivo '{COLUMNA_OBJETIVO}'")

    df = df.sort_values(COLUMNA_TIEMPO).reset_index(drop=True).copy()

    df = _features_calendario(df)
    df = _features_rezago(df)
    df = _features_exogenas(df)

    # Objetivo: el precio `horizonte` horas en el futuro.
    df["objetivo"] = df[COLUMNA_OBJETIVO].shift(-horizonte)

    if eliminar_nulos:
        antes = len(df)
        # Se descarta por las columnas que REALMENTE entran al modelo, no por
        # todas. Un `dropna()` sin `subset` vaciaría el conjunto entero en
        # cuanto una sola columna del esquema viniera sin datos —por ejemplo el
        # desglose de generación por tecnología, que la API pública de XM no
        # publica y que por tanto llega siempre vacío.
        obligatorias = [*columnas_features(df), "objetivo"]
        df = df.dropna(subset=obligatorias).reset_index(drop=True)
        log.info(
            "Features: %d filas -> %d tras descartar bordes (lags/horizonte)", antes, len(df)
        )

    return df


def columnas_features(df: pd.DataFrame) -> list[str]:
    """Devuelve las columnas que entran al modelo.

    Excluye la marca de tiempo, el objetivo y cualquier columna no numérica.
    Excluye también `precio_bolsa` en crudo: usar el precio del instante *t*
    para predecir *t + horizonte* sería legítimo, pero se prefiere que entre
    solo a través de los rezagos explícitos para que quede documentado.
    """
    excluidas = {COLUMNA_TIEMPO, "objetivo", COLUMNA_OBJETIVO, "fuente", "fenomeno_climatico", "id"}
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


def _features_calendario(df: pd.DataFrame) -> pd.DataFrame:
    ts = df[COLUMNA_TIEMPO]

    df["hora"] = ts.dt.hour
    df["dia_semana"] = ts.dt.dayofweek
    df["dia_mes"] = ts.dt.day
    df["mes"] = ts.dt.month
    df["trimestre"] = ts.dt.quarter
    df["semana_anio"] = ts.dt.isocalendar().week.astype(int)
    df["es_fin_semana"] = (df["dia_semana"] >= 5).astype(int)

    # Temporada seca en Colombia (diciembre–marzo): menos aportes, precio alto.
    df["es_temporada_seca"] = df["mes"].isin([12, 1, 2, 3]).astype(int)

    # Codificación cíclica
    for columna, periodo in (("hora", 24), ("dia_semana", 7), ("mes", 12)):
        df[f"{columna}_sin"] = np.sin(2 * np.pi * df[columna] / periodo)
        df[f"{columna}_cos"] = np.cos(2 * np.pi * df[columna] / periodo)

    return df


def _features_rezago(df: pd.DataFrame) -> pd.DataFrame:
    for lag in LAGS_PRECIO:
        df[f"precio_lag_{lag}"] = df[COLUMNA_OBJETIVO].shift(lag)

    if "demanda_real" in df.columns:
        for lag in LAGS_DEMANDA:
            df[f"demanda_lag_{lag}"] = df["demanda_real"].shift(lag)

    # Medias/desviaciones móviles sobre la serie YA desplazada una hora, para
    # que la ventana nunca incluya el instante actual.
    precio_pasado = df[COLUMNA_OBJETIVO].shift(1)
    for ventana in VENTANAS:
        df[f"precio_media_{ventana}h"] = precio_pasado.rolling(ventana, min_periods=2).mean()
        df[f"precio_std_{ventana}h"] = precio_pasado.rolling(ventana, min_periods=2).std()

    df["precio_max_24h"] = precio_pasado.rolling(24, min_periods=2).max()
    df["precio_min_24h"] = precio_pasado.rolling(24, min_periods=2).min()

    # Variación relativa respecto a hace 24 h: captura la tendencia reciente.
    df["precio_var_24h"] = (
        (df["precio_lag_1"] - df["precio_lag_24"]) / df["precio_lag_24"].replace(0, np.nan)
    )

    return df


def _tiene_datos(df: pd.DataFrame, columna: str) -> bool:
    """¿Existe la columna y contiene al menos un valor real?

    Distinguir «la columna no existe» de «existe pero está vacía» es lo que
    evita construir variables derivadas a partir de nada. La API pública de XM
    no publica el desglose de generación por tecnología, así que ese caso es
    la norma y no la excepción.
    """
    return columna in df.columns and df[columna].notna().any()


def _features_exogenas(df: pd.DataFrame) -> pd.DataFrame:
    hidro = "generacion_hidraulica"
    termica = "generacion_termica"

    # Participación hidráulica: el driver estructural del precio en Colombia.
    # `_tiene_datos` es imprescindible: la API pública de XM no publica el
    # desglose por tecnología, así que estas columnas suelen venir vacías. Sin
    # esta guarda se generaría una variable enteramente NaN que después haría
    # desaparecer todas las filas en el `dropna` final.
    if _tiene_datos(df, hidro) and _tiene_datos(df, termica):
        total = df[hidro] + df[termica]
        df["fraccion_hidraulica"] = np.where(total > 0, df[hidro] / total, np.nan)

    # Margen de reserva: cuánta holgura tiene el sistema. Se usa la
    # disponibilidad si existe y, si no, la generación ideal, que es el
    # equivalente que sí publica la API de XM.
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

    # Distancia al precio de escasez: cuando el precio de bolsa se acerca al de
    # escasez, el sistema está en estrés y el comportamiento cambia de régimen.
    if _tiene_datos(df, "precio_escasez"):
        df["ratio_precio_escasez"] = np.where(
            df["precio_escasez"] > 0,
            df[COLUMNA_OBJETIVO].shift(1) / df["precio_escasez"],
            np.nan,
        )

    # Fenómeno ENSO como variables indicadoras (one-hot sin colinealidad total).
    if "indice_oni" in df.columns:
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

    return df
