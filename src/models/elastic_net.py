"""ElasticNet — regresión lineal con penalización L1 + L2.

Complementa a Ridge en la comparación con una diferencia concreta: la parte L1
lleva coeficientes exactamente a cero, así que el modelo **selecciona
variables** por sí mismo. Con más de cien predictoras, muchas de ellas rezagos
casi idénticos entre sí, saber cuáles sobreviven a la penalización es un
resultado interpretable por derecho propio, y no solo un número de error.

Ridge, en cambio, reparte el peso entre las variables correlacionadas sin
eliminar ninguna. Tener ambos permite decir en el informe si la señal está
concentrada en unas pocas variables (gana ElasticNet, coeficientes dispersos) o
repartida (gana Ridge).

`l1_ratio=0.5` reparte a partes iguales entre ambas penalizaciones; el
`StandardScaler` es obligatorio, porque si no la penalización castigaría a cada
variable según su unidad de medida y no según su aportación.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.models.base import ModeloPredictivo


class ModeloElasticNet(ModeloPredictivo):
    """ElasticNet + estandarización, encapsulados en un `Pipeline`."""

    nombre = "elastic_net"

    def __init__(
        self,
        alpha: float = 0.05,
        l1_ratio: float = 0.5,
        max_iter: int = 5000,
        random_state: int = 42,
        **kwargs,
    ) -> None:
        super().__init__(
            alpha=alpha,
            l1_ratio=l1_ratio,
            max_iter=max_iter,
            random_state=random_state,
            **kwargs,
        )
        self.pipeline = Pipeline(
            [
                ("escalador", StandardScaler()),
                (
                    "regresor",
                    ElasticNet(
                        alpha=alpha,
                        l1_ratio=l1_ratio,
                        max_iter=max_iter,
                        random_state=random_state,
                    ),
                ),
            ]
        )

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloElasticNet:
        self.columnas_features = list(X.columns)
        self.pipeline.fit(X, np.asarray(y, dtype=float))
        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        return self.pipeline.predict(self._alinear_columnas(X))

    def variables_seleccionadas(self) -> list[str]:
        """Variables con coeficiente distinto de cero tras la penalización."""
        if not self.entrenado:
            return []
        coeficientes = self.pipeline.named_steps["regresor"].coef_
        return [c for c, w in zip(self.columnas_features, coeficientes, strict=True) if w != 0]

    def importancia_features(self) -> pd.Series | None:
        """Magnitud de los coeficientes sobre las variables ya estandarizadas."""
        if not self.entrenado:
            return None
        coeficientes = self.pipeline.named_steps["regresor"].coef_
        return pd.Series(np.abs(coeficientes), index=self.columnas_features).sort_values(
            ascending=False
        )
