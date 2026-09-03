"""Pronóstico ingenuo estacional — la vara de medir de todo el estudio.

Predice que el valor de dentro de *h* horas será el mismo que tuvo la serie a la
misma hora del día más reciente que se conoce. No aprende nada: repite el
pasado. Por eso es exactamente la referencia que hace falta.

Por qué es imprescindible en el trabajo de grado
------------------------------------------------

Las series horarias de energía están tan autocorrelacionadas que casi cualquier
modelo alcanza un R² alto. Ese número, solo, no dice nada: repetir el dato de
ayer a la misma hora también da un R² alto. La pregunta relevante no es "¿el
modelo se ajusta?", sino "¿el modelo aporta algo por encima de no hacer nada?".

Este baseline responde a esa pregunta y es el denominador del **MASE**: un
modelo con MASE ≥ 1 no le gana a repetir el pasado y, por tanto, no justifica su
complejidad por bueno que sea su R².

Cómo obtiene el valor
---------------------

La matriz de variables no contiene el valor del instante actual —se excluye a
propósito para documentar que todo entra por rezagos explícitos—, así que el
baseline toma la primera columna disponible de esta lista de preferencia:

1. ``objetivo_lag_24`` — misma hora del día anterior. Es el candidato natural.
2. ``objetivo_media_misma_hora_7d`` — promedio de esa hora en la última semana;
   suaviza el ruido de un día atípico.
3. ``objetivo_lag_1`` — la hora anterior, como último recurso.

Si no hay ninguna, cae a la media del entrenamiento, que es el pronóstico más
tonto posible y deja constancia de que faltaban los rezagos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.models.base import ModeloPredictivo

log = get_logger(__name__)

#: Columnas candidatas, en orden de preferencia.
COLUMNAS_CANDIDATAS = (
    "objetivo_lag_24",
    "objetivo_media_misma_hora_7d",
    "objetivo_lag_1",
)


class ModeloBaselineEstacional(ModeloPredictivo):
    """Repite el valor de la misma hora del ciclo anterior."""

    nombre = "baseline_estacional"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.columna_referencia: str | None = None
        self.media_entrenamiento: float = 0.0
        #: Ajuste de nivel: la media de la diferencia entre lo que hay que
        #: predecir y la columna de referencia. Sin él, a horizontes largos el
        #: baseline arrastraría un sesgo sistemático (la serie crece o decrece)
        #: y el MASE saldría artificialmente favorable a los demás modelos.
        self.desplazamiento: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloBaselineEstacional:
        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float)
        self.media_entrenamiento = float(np.mean(y))

        self.columna_referencia = next(
            (c for c in COLUMNAS_CANDIDATAS if c in X.columns), None
        )

        if self.columna_referencia is None:
            log.warning(
                "Baseline: ninguna columna de rezago disponible; se usará la media"
            )
            self.desplazamiento = 0.0
        else:
            referencia = X[self.columna_referencia].to_numpy(dtype=float)
            self.desplazamiento = float(np.nanmean(y - referencia))

        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        X = self._alinear_columnas(X)

        if self.columna_referencia is None:
            return np.full(len(X), self.media_entrenamiento)

        valores = X[self.columna_referencia].to_numpy(dtype=float) + self.desplazamiento
        # Un NaN en la referencia (borde de la serie) se sustituye por la media:
        # devolver NaN rompería el cálculo de métricas de todos los modelos.
        return np.where(np.isnan(valores), self.media_entrenamiento, valores)
