"""Limpieza y normalización de las series recolectadas.

El orden de las operaciones importa y no es arbitrario:

1. **Unir** las fuentes (XM + clima) por marca de tiempo.
2. **Tipar y ordenar** — sin un índice temporal ordenado, los `lag` posteriores
   producirían basura silenciosamente.
3. **Deduplicar** — XM puede devolver la misma hora en dos lotes solapados.
4. **Rellenar huecos horarios** — una serie con horas faltantes rompe los
   `lag`: el "precio de hace 24 h" dejaría de estar 24 h atrás.
5. **Tratar atípicos** — *después* de rellenar, para que los estadísticos se
   calculen sobre la rejilla completa.
6. **Imputar nulos** — al final, cuando ya sabemos qué falta de verdad.
"""

from __future__ import annotations

import pandas as pd

from src.core.logging import get_logger

log = get_logger(__name__)

COLUMNA_TIEMPO = "fecha_hora"
COLUMNA_OBJETIVO = "precio_bolsa"

#: Columnas numéricas que esperamos del pipeline completo.
COLUMNAS_NUMERICAS = [
    "precio_bolsa",
    "demanda_real",
    "demanda_comercial",
    "generacion_total",
    "generacion_ideal",
    "generacion_hidraulica",
    "generacion_termica",
    "disponibilidad_real",
    "aportes_hidricos",
    "volumen_util_energia",
    "capacidad_util_energia",
    "volumen_util_embalse",
    "precio_escasez",
    "temperatura",
    "precipitacion",
    "humedad_relativa",
    "indice_oni",
]


def unir_fuentes(*dataframes: pd.DataFrame) -> pd.DataFrame:
    """Une varias fuentes por `fecha_hora` con un *outer join*.

    Se usa *outer* y no *inner* a propósito: si el clima cubre un rango más
    corto que XM no queremos perder registros de precio, que es la variable
    objetivo. Los huecos se imputan más adelante.
    """
    dataframes = tuple(df for df in dataframes if df is not None and not df.empty)
    if not dataframes:
        return pd.DataFrame()

    resultado = dataframes[0].copy()
    for siguiente in dataframes[1:]:
        columnas_nuevas = [
            c for c in siguiente.columns if c not in resultado.columns or c == COLUMNA_TIEMPO
        ]
        resultado = resultado.merge(
            siguiente[columnas_nuevas], on=COLUMNA_TIEMPO, how="outer"
        )

    return resultado.sort_values(COLUMNA_TIEMPO).reset_index(drop=True)


def limpiar(
    df: pd.DataFrame,
    *,
    rellenar_huecos: bool = True,
    tratar_atipicos: bool = True,
    umbral_iqr: float = 3.0,
) -> pd.DataFrame:
    """Aplica el pipeline completo de limpieza.

    Args:
        df: datos crudos con al menos `fecha_hora` y `precio_bolsa`.
        rellenar_huecos: reconstruye la rejilla horaria completa.
        tratar_atipicos: recorta valores extremos por IQR (*winsorizing*).
        umbral_iqr: multiplicador del rango intercuartílico. Se usa 3.0 y no el
            1.5 clásico porque en el mercado energético los picos de escasez son
            reales, no errores de medición: recortarlos con 1.5 destruiría
            justo la señal que el modelo debe aprender.

    Returns:
        `DataFrame` limpio, ordenado y sin nulos en las columnas numéricas.
    """
    if df.empty:
        log.warning("limpiar() recibió un DataFrame vacío")
        return df

    if COLUMNA_TIEMPO not in df.columns:
        raise ValueError(f"Falta la columna obligatoria '{COLUMNA_TIEMPO}'")
    if COLUMNA_OBJETIVO not in df.columns:
        raise ValueError(f"Falta la columna objetivo '{COLUMNA_OBJETIVO}'")

    filas_inicio = len(df)
    df = df.copy()

    # 1. Tipado y orden
    df[COLUMNA_TIEMPO] = pd.to_datetime(df[COLUMNA_TIEMPO], errors="coerce", utc=False)
    df = df.dropna(subset=[COLUMNA_TIEMPO])
    if hasattr(df[COLUMNA_TIEMPO].dtype, "tz") and df[COLUMNA_TIEMPO].dt.tz is not None:
        df[COLUMNA_TIEMPO] = df[COLUMNA_TIEMPO].dt.tz_localize(None)
    df = df.sort_values(COLUMNA_TIEMPO)

    for columna in COLUMNAS_NUMERICAS:
        if columna in df.columns:
            df[columna] = pd.to_numeric(df[columna], errors="coerce")

    # 2. Duplicados de marca temporal (lotes solapados de XM)
    duplicados = int(df.duplicated(subset=[COLUMNA_TIEMPO]).sum())
    if duplicados:
        log.info("Eliminando %d marcas de tiempo duplicadas", duplicados)
        df = df.drop_duplicates(subset=[COLUMNA_TIEMPO], keep="last")

    # 3. Sin precio no hay nada que aprender
    sin_objetivo = int(df[COLUMNA_OBJETIVO].isna().sum())
    if sin_objetivo:
        log.info("Descartando %d filas sin precio de bolsa", sin_objetivo)
        df = df.dropna(subset=[COLUMNA_OBJETIVO])

    if df.empty:
        log.warning("No quedaron filas tras descartar las que no tienen precio")
        return df

    # 4. Rejilla horaria completa
    if rellenar_huecos:
        df = _reindexar_horario(df)

    # 5. Atípicos
    if tratar_atipicos:
        df = _recortar_atipicos(df, umbral_iqr)

    # 6. Imputación
    df = _imputar(df)

    df = df.reset_index(drop=True)
    log.info("Limpieza: %d filas de entrada -> %d de salida", filas_inicio, len(df))
    return df


# ---------------------------------------------------------------------------
# Pasos internos
# ---------------------------------------------------------------------------


def _reindexar_horario(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstruye la rejilla horaria completa entre el mínimo y el máximo."""
    rejilla = pd.date_range(
        df[COLUMNA_TIEMPO].min(), df[COLUMNA_TIEMPO].max(), freq="h"
    )
    faltantes = len(rejilla) - len(df)
    if faltantes > 0:
        log.info("Rellenando %d horas ausentes en la serie", faltantes)

    df = (
        df.set_index(COLUMNA_TIEMPO)
        .reindex(rejilla)
        .rename_axis(COLUMNA_TIEMPO)
        .reset_index()
    )
    return df


def _recortar_atipicos(df: pd.DataFrame, umbral: float) -> pd.DataFrame:
    """*Winsoriza* por IQR: recorta a los límites en vez de eliminar la fila.

    Eliminar filas abriría huecos en la serie temporal (y volveríamos al
    problema de los `lag` desalineados). Recortar conserva la rejilla.
    """
    for columna in COLUMNAS_NUMERICAS:
        if columna not in df.columns or df[columna].notna().sum() < 10:
            continue

        q1 = df[columna].quantile(0.25)
        q3 = df[columna].quantile(0.75)
        iqr = q3 - q1
        if iqr <= 0:
            continue

        inferior, superior = q1 - umbral * iqr, q3 + umbral * iqr
        n_atipicos = int(((df[columna] < inferior) | (df[columna] > superior)).sum())
        if n_atipicos:
            log.debug("%s: recortando %d valores atípicos", columna, n_atipicos)
            df[columna] = df[columna].clip(inferior, superior)

    return df


def _imputar(df: pd.DataFrame) -> pd.DataFrame:
    """Imputa nulos respetando la naturaleza temporal de los datos.

    Se usa interpolación temporal + `ffill`/`bfill` en lugar de la media: en una
    serie horaria, el vecino temporal es muchísimo mejor estimador que el
    promedio global, que aplanaría la estacionalidad.
    """
    numericas = [c for c in COLUMNAS_NUMERICAS if c in df.columns]

    df = df.set_index(COLUMNA_TIEMPO)
    df[numericas] = (
        df[numericas]
        .interpolate(method="time", limit_direction="both")
        .ffill()
        .bfill()
    )
    df = df.reset_index()

    # Categóricas y metadatos
    if "fenomeno_climatico" in df.columns:
        df["fenomeno_climatico"] = df["fenomeno_climatico"].ffill().bfill().fillna("NEUTRO")
    if "fuente" in df.columns:
        df["fuente"] = df["fuente"].ffill().bfill().fillna("DESCONOCIDA")

    # Una columna ENTERAMENTE vacía no se puede imputar: no hay vecino del que
    # aprender. Rellenarla con 0 fabricaría datos —y peor, las variables
    # derivadas de ella (ratios, fracciones) parecerían válidas siendo ficción.
    # Se dejan como NaN a propósito para que `columnas_features` las excluya.
    vacias = [c for c in numericas if df[c].isna().all()]
    if vacias:
        log.warning(
            "Columnas sin ningún dato, se dejan vacías y quedarán fuera del modelo: %s",
            ", ".join(vacias),
        )

    parciales = [c for c in numericas if c not in vacias]
    restantes = int(df[parciales].isna().sum().sum())
    if restantes:
        log.warning("Quedan %d nulos aislados tras la imputación; se rellenan con 0", restantes)
        df[parciales] = df[parciales].fillna(0)

    return df
