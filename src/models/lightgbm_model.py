"""LightGBM — *gradient boosting* con crecimiento por hojas.

Comparte familia con XGBoost, pero difiere en algo que aquí importa: XGBoost
hace crecer los árboles **por niveles** (todas las ramas a la misma profundidad)
y LightGBM **por hojas** (expande siempre la hoja que más reduce el error). El
resultado son árboles asimétricos que capturan mejor las interacciones raras
—picos de escasez, festivos, horas punta— con menos nodos.

Tenerlos a los dos en la comparación no es redundante: si LightGBM gana con
claridad, la conclusión es que la señal está en esos casos poco frecuentes; si
empatan, que la relación es suave y bien cubierta por ambos. Esa distinción es
material para el análisis del trabajo de grado.

Controles de sobreajuste: `num_leaves` acotado —el parámetro crítico del
crecimiento por hojas—, submuestreo de filas y columnas, y parada temprana
contra un conjunto de validación **cronológico**.
"""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from src.core.logging import get_logger
from src.models.base import ModeloPredictivo

log = get_logger(__name__)


def _conjunto_validacion(X: pd.DataFrame, y: np.ndarray) -> dict:
    """Argumentos del conjunto de validación, según la versión de LightGBM.

    LightGBM 4.7 deprecó `eval_set=[(X, y)]` en favor de `eval_X`/`eval_y` y
    emite un aviso en cada entrenamiento. Se elige la forma que acepte la
    versión instalada en lugar de fijar una: el proyecto tiene que seguir
    funcionando tanto en el equipo del jurado como en el de desarrollo, y sus
    versiones no tienen por qué coincidir.
    """
    import inspect

    parametros = inspect.signature(lgb.LGBMRegressor.fit).parameters
    if "eval_X" in parametros:
        return {"eval_X": X, "eval_y": y}
    return {"eval_set": [(X, y)]}


class ModeloLightGBM(ModeloPredictivo):
    """Regresor de *gradient boosting* con crecimiento por hojas."""

    nombre = "lightgbm"

    def __init__(
        self,
        n_estimators: int = 1200,
        learning_rate: float = 0.05,
        num_leaves: int = 63,
        max_depth: int = -1,
        min_child_samples: int = 20,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_lambda: float = 1.5,
        random_state: int = 42,
        proporcion_validacion: float = 0.1,
        **kwargs,
    ) -> None:
        super().__init__(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            max_depth=max_depth,
            min_child_samples=min_child_samples,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            reg_lambda=reg_lambda,
            random_state=random_state,
            **kwargs,
        )
        self.proporcion_validacion = proporcion_validacion
        self.regresor = lgb.LGBMRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            num_leaves=num_leaves,
            max_depth=max_depth,
            min_child_samples=min_child_samples,
            subsample=subsample,
            # `subsample` solo actúa si se fija la frecuencia de remuestreo.
            subsample_freq=1,
            colsample_bytree=colsample_bytree,
            reg_lambda=reg_lambda,
            random_state=random_state,
            objective="regression",
            n_jobs=-1,
            verbose=-1,
        )

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloLightGBM:
        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float)

        # Validación CRONOLÓGICA (el último tramo), nunca aleatoria.
        corte = int(len(X) * (1 - self.proporcion_validacion))
        if corte < 10 or len(X) - corte < 10:
            log.debug("Datos insuficientes para parada temprana; se entrena sin ella")
            self.regresor.fit(X, y)
        else:
            self.regresor.fit(
                X.iloc[:corte],
                y[:corte],
                eval_metric="rmse",
                callbacks=[lgb.early_stopping(50, verbose=False)],
                **_conjunto_validacion(X.iloc[corte:], y[corte:]),
            )
            mejor = getattr(self.regresor, "best_iteration_", None)
            if mejor:
                log.info("LightGBM: parada temprana en la iteración %d", mejor)

        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        return self.regresor.predict(self._alinear_columnas(X))

    def importancia_features(self) -> pd.Series | None:
        """Importancia por ganancia acumulada.

        Se pide explícitamente `importance_type="gain"` en lugar del `"split"`
        que LightGBM usa por defecto: contar cuántas veces se parte por una
        variable premia a las de muchos valores distintos, mientras que la
        ganancia mide cuánto error eliminó de verdad cada partición.
        """
        if not self.entrenado:
            return None
        importancias = self.regresor.booster_.feature_importance(importance_type="gain")
        return pd.Series(importancias, index=self.columnas_features).sort_values(
            ascending=False
        )
