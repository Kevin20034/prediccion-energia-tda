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
from src.data_collection.clima_client import clasificar_fenomeno
from src.data_collection.xm_client import COLUMNAS_XM

log = get_logger(__name__)

COLUMNA_TIEMPO = "fecha_hora"
COLUMNA_OBJETIVO = "precio_bolsa"

#: Columnas climáticas, que no vienen de XM.
COLUMNAS_CLIMA = ("temperatura", "precipitacion", "humedad_relativa", "indice_oni")

#: Columnas numéricas que esperamos del pipeline completo.
#:
#: Se derivan del catálogo del cliente de XM en vez de repetirse a mano: cuando
#: se añade una métrica nueva basta con declararla en `xm_client` y la limpieza
#: la trata sin que nadie tenga que acordarse de tocar también esta lista.
COLUMNAS_NUMERICAS: list[str] = [*COLUMNAS_XM, *COLUMNAS_CLIMA]


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
    objetivo: str = COLUMNA_OBJETIVO,
    rellenar_huecos: bool = True,
    tratar_atipicos: bool = True,
    imputar: bool = True,
    umbral_iqr: float = 3.0,
) -> pd.DataFrame:
    """Aplica el pipeline completo de limpieza.

    Args:
        df: datos crudos con al menos `fecha_hora` y la columna objetivo.
        objetivo: columna sin la cual una fila no sirve para entrenar. Por
            defecto el precio de bolsa; con `demanda_real` se limpia el mismo
            conjunto para el otro objetivo del sistema.
        rellenar_huecos: reconstruye la rejilla horaria completa.
        imputar: rellena los nulos restantes. Debe ir a `False` **al guardar en
            base de datos**: lo que se almacena tiene que ser lo que la fuente
            publicó, no una estimación con la etiqueta `fuente = "XM"` puesta
            encima. La imputación es una decisión de modelado y su sitio es el
            camino de entrenamiento, que la aplica sobre lo leído.
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
    if objetivo not in df.columns:
        raise ValueError(f"Falta la columna objetivo '{objetivo}'")

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

    # 3. Demanda publicada a medias por XM
    df = _anular_demanda_preliminar(df)

    # 4. Sin el valor objetivo no hay nada que aprender
    sin_objetivo = int(df[objetivo].isna().sum())
    if sin_objetivo:
        log.info("Descartando %d filas sin '%s'", sin_objetivo, objetivo)
        df = df.dropna(subset=[objetivo])

    if df.empty:
        log.warning("No quedaron filas tras descartar las que no tienen '%s'", objetivo)
        return df

    # 5. Rejilla horaria completa
    if rellenar_huecos:
        df = _reindexar_horario(df)

    # 6. Atípicos
    if tratar_atipicos:
        df = _recortar_atipicos(df, umbral_iqr)

    # 7. Imputación
    if imputar:
        df = _imputar(df)

    # 8. La etiqueta del fenómeno se recalcula al final, siempre
    df = _reclasificar_fenomeno(df)

    df = df.reset_index(drop=True)
    log.info("Limpieza: %d filas de entrada -> %d de salida", filas_inicio, len(df))
    return df


# ---------------------------------------------------------------------------
# Pasos internos
# ---------------------------------------------------------------------------


#: Columnas de demanda que XM completa con retraso y que hay que anular juntas.
COLUMNAS_DEMANDA = (
    "demanda_real",
    "demanda_comercial",
    "demanda_regulada",
    "demanda_no_regulada",
)

#: Cociente mínimo demanda/generación por debajo del cual la demanda se
#: considera publicada a medias.
#:
#: En el SIN el cociente ronda 0,98 —la diferencia son exportaciones y
#: pérdidas— y es notablemente estable. El corte en 0,6 está muy por debajo de
#: cualquier variación real del sistema, así que solo captura el caso que
#: pretende capturar y no descarta días legítimamente atípicos.
RATIO_DEMANDA_MINIMO = 0.6

#: Periodo del ciclo diario y cuántos días atrás se busca para rellenar un
#: hueco en los extremos de la serie.
HORAS_DIA = 24
DIAS_RELLENO_ESTACIONAL = 3


def _reclasificar_fenomeno(df: pd.DataFrame) -> pd.DataFrame:
    """Vuelve a derivar `fenomeno_climatico` del `indice_oni` de la misma fila.

    El fenómeno es una **función del ONI**, no un dato independiente, y aquí es
    el último sitio donde el ONI puede cambiar. El cliente de clima lo clasifica
    al descargar, antes de que la limpieza toque nada; si después el ONI se
    rellena o se corrige, la etiqueta se queda con el valor viejo.

    Eso ya pasó: la base llegó a tener horas marcadas `NEUTRO` con un ONI de
    1,39, que es El Niño de manual. No era un error cosmético — la sección del
    fenómeno agrupa por esta columna, así que esas horas entraban en la media
    equivocada y contaminaban la comparación entre fases.

    Recalcular aquí cuesta una pasada y cierra la puerta a que el número y su
    etiqueta vuelvan a separarse.
    """
    if "indice_oni" not in df.columns:
        return df

    df = df.copy()
    df["fenomeno_climatico"] = df["indice_oni"].apply(clasificar_fenomeno)
    return df


def _anular_demanda_preliminar(df: pd.DataFrame) -> pd.DataFrame:
    """Anula la demanda de las horas que XM aún no ha publicado completa.

    XM publica la demanda por agente y la consolida a lo largo de varios días.
    Mientras tanto devuelve la suma parcial de los agentes que ya reportaron,
    sin marcarla de ninguna forma: en los últimos días del histórico aparece una
    demanda nacional plana en torno a un tercio de la real.

    Es un dato equivocado, no un dato faltante, y esa es la diferencia que lo
    hace peligroso: pasa todos los filtros de nulos, sobrevive al recorte de
    atípicos —porque no es extremo, es *bajo*— y llega hasta el pronóstico,
    donde el modelo lo toma como el punto de partida real del sistema.

    Se detecta comparándola con la generación total, que sí llega completa: si
    la demanda no alcanza ni el 60 % de lo que el país generó esa hora, es que
    faltan agentes por reportar. Se anula en lugar de borrar la fila para no
    perder el precio y la hidrología de esas horas, que sí son correctos.
    """
    if "generacion_total" not in df.columns or "demanda_real" not in df.columns:
        return df

    generacion = pd.to_numeric(df["generacion_total"], errors="coerce")
    demanda = pd.to_numeric(df["demanda_real"], errors="coerce")

    incompleta = (
        generacion.notna()
        & (generacion > 0)
        & demanda.notna()
        & (demanda / generacion < RATIO_DEMANDA_MINIMO)
    )

    afectadas = int(incompleta.sum())
    if not afectadas:
        return df

    log.warning(
        "Demanda publicada a medias en %d horas (%s -> %s): se anula",
        afectadas,
        df.loc[incompleta, COLUMNA_TIEMPO].min(),
        df.loc[incompleta, COLUMNA_TIEMPO].max(),
    )

    for columna in COLUMNAS_DEMANDA:
        if columna in df.columns:
            df.loc[incompleta, columna] = pd.NA

    return df


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

    Tres pasadas, en este orden y por este motivo:

    1. **Interpolación temporal solo hacia dentro** (`limit_area="inside"`).
       Para un hueco de una o dos horas rodeado de datos buenos, la recta entre
       los vecinos es el mejor estimador que hay. Se limita a los huecos
       interiores para que la interpolación no se convierta en extrapolación en
       los extremos de la serie.
    2. **Relleno estacional**: lo que queda —los huecos del principio y del
       final— se completa con el valor de la misma hora del día anterior,
       repitiendo hasta tres días. En una serie con un ciclo diario tan marcado
       como esta, "lo que pasó ayer a esta hora" es incomparablemente mejor que
       "lo último que se supo": propagar hacia adelante el último valor conocido
       deja una recta plana que borra el ciclo justo en el tramo que alimenta el
       pronóstico. Es el caso real de la demanda, que XM publica completa con
       dos días de retraso.
    3. **`ffill`/`bfill`** como último recurso, para series sin ciclo diario o
       con huecos más largos de tres días.
    """
    numericas = [c for c in COLUMNAS_NUMERICAS if c in df.columns]

    df = df.set_index(COLUMNA_TIEMPO)

    bloque = df[numericas].interpolate(method="time", limit_area="inside")

    for _ in range(DIAS_RELLENO_ESTACIONAL):
        if not bloque.isna().any().any():
            break
        bloque = bloque.fillna(bloque.shift(HORAS_DIA))

    df[numericas] = bloque.ffill().bfill()
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
