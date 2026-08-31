"""Regresión lineal regularizada — modelo de referencia (*baseline*).

Su papel en el trabajo de grado es servir de línea base: cualquier modelo más
complejo debe superarla de forma clara para justificar su coste computacional.
Si un Random Forest apenas mejora a una regresión lineal, la conclusión honesta
es que la relación es fundamentalmente lineal.

Se usa **Ridge** en lugar de `LinearRegression` pura porque las variables
predictoras están muy correlacionadas entre sí (los rezagos del precio lo están
por construcción). Con multicolinealidad, los mínimos cuadrados ordinarios dan
coeficientes inestables y de signo caprichoso; la penalización L2 los estabiliza.

El `StandardScaler` es obligatorio aquí: sin escalar, Ridge penalizaría más a
las variables de magnitud pequeña solo por su unidad de medida.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.models.base import ModeloPredictivo


class ModeloRegresionLineal(ModeloPredictivo):
    """Ridge + estandarización, encapsulados en un `Pipeline` de scikit-learn."""

    nombre = "regresion_lineal"

    def __init__(self, alpha: float = 1.0, **kwargs) -> None:
        super().__init__(alpha=alpha, **kwargs)
        self.pipeline = Pipeline(
            [
                ("escalador", StandardScaler()),
                ("regresor", Ridge(alpha=alpha, random_state=42)),
            ]
        )

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloRegresionLineal:
        self.columnas_features = list(X.columns)
        self.pipeline.fit(X, np.asarray(y, dtype=float))
        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        return self.pipeline.predict(self._alinear_columnas(X))

    def importancia_features(self) -> pd.Series | None:
        """Magnitud de los coeficientes sobre las variables ya estandarizadas.

        Al estar todas en la misma escala, los coeficientes sí son comparables
        entre sí como medida de influencia.
        """
        if not self.entrenado:
            return None
        coeficientes = self.pipeline.named_steps["regresor"].coef_
        return (
            pd.Series(np.abs(coeficientes), index=self.columnas_features)
            .sort_values(ascending=False)
        )
