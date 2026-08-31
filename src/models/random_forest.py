"""Random Forest — modelo de conjunto basado en árboles.

Aporta al estudio dos cosas que la regresión lineal no tiene:

* Captura **no linealidades** e interacciones entre variables sin que haya que
  declararlas (por ejemplo: "El Niño *y* embalses bajos *y* hora pico").
* Es **robusto a atípicos**, porque cada árbol parte por umbrales, no por
  distancias.

No necesita escalado: los árboles solo comparan valores contra un umbral, así
que la unidad de medida es irrelevante.

`n_jobs=-1` usa todos los núcleos; con ~17 000 filas y ~50 variables entrena en
segundos en un portátil normal.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from src.models.base import ModeloPredictivo


class ModeloRandomForest(ModeloPredictivo):
    """Bosque aleatorio de regresión."""

    nombre = "random_forest"

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int | None = 18,
        min_samples_leaf: int = 2,
        max_features: str | float = "sqrt",
        random_state: int = 42,
        **kwargs,
    ) -> None:
        super().__init__(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            **kwargs,
        )
        self.regresor = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
            max_features=max_features,
            random_state=random_state,
            n_jobs=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloRandomForest:
        self.columnas_features = list(X.columns)
        self.regresor.fit(X, np.asarray(y, dtype=float))
        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        return self.regresor.predict(self._alinear_columnas(X))

    def importancia_features(self) -> pd.Series | None:
        """Importancia por reducción de impureza (Gini/MSE).

        Advertencia metodológica para la tesis: esta medida está sesgada hacia
        variables con muchos valores distintos. Para el informe final conviene
        contrastarla con *permutation importance*, que no tiene ese sesgo.
        """
        if not self.entrenado:
            return None
        return (
            pd.Series(self.regresor.feature_importances_, index=self.columnas_features)
            .sort_values(ascending=False)
        )
