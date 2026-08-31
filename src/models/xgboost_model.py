"""XGBoost — *gradient boosting* sobre árboles.

Suele ser el mejor modelo en datos tabulares como estos. Frente a Random
Forest, que promedia árboles independientes, el *boosting* construye cada árbol
para corregir el error del anterior: aprende patrones más finos, a cambio de
ser más sensible al sobreajuste.

Controles de sobreajuste aplicados:

* ``learning_rate`` bajo (0.05) con muchos árboles — converge más despacio pero
  generaliza mejor.
* ``subsample`` y ``colsample_bytree`` a 0.8 — cada árbol ve el 80 % de las
  filas y de las columnas, lo que introduce aleatoriedad y reduce la varianza.
* **Parada temprana** contra un conjunto de validación cronológico: deja de
  entrenar cuando el error de validación deja de bajar. Es la salvaguarda más
  efectiva y evita tener que adivinar `n_estimators`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import xgboost as xgb

from src.core.logging import get_logger
from src.models.base import ModeloPredictivo

log = get_logger(__name__)


class ModeloXGBoost(ModeloPredictivo):
    """Regresor de *gradient boosting*."""

    nombre = "xgboost"

    def __init__(
        self,
        n_estimators: int = 800,
        learning_rate: float = 0.05,
        max_depth: int = 7,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_weight: int = 3,
        reg_lambda: float = 1.5,
        random_state: int = 42,
        proporcion_validacion: float = 0.1,
        **kwargs,
    ) -> None:
        super().__init__(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            min_child_weight=min_child_weight,
            reg_lambda=reg_lambda,
            random_state=random_state,
            **kwargs,
        )
        self.proporcion_validacion = proporcion_validacion
        self.regresor = xgb.XGBRegressor(
            n_estimators=n_estimators,
            learning_rate=learning_rate,
            max_depth=max_depth,
            subsample=subsample,
            colsample_bytree=colsample_bytree,
            min_child_weight=min_child_weight,
            reg_lambda=reg_lambda,
            random_state=random_state,
            objective="reg:squarederror",
            eval_metric="rmse",
            early_stopping_rounds=50,
            n_jobs=-1,
            tree_method="hist",
        )

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloXGBoost:
        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float)

        # Validación CRONOLÓGICA (el último tramo), nunca aleatoria: con series
        # temporales, validar con datos del pasado mezclados sería fuga.
        corte = int(len(X) * (1 - self.proporcion_validacion))
        if corte < 10 or len(X) - corte < 10:
            # Conjunto demasiado pequeño para parada temprana (caso de tests).
            log.debug("Datos insuficientes para parada temprana; se entrena sin ella")
            self.regresor.set_params(early_stopping_rounds=None)
            self.regresor.fit(X, y, verbose=False)
        else:
            self.regresor.fit(
                X.iloc[:corte],
                y[:corte],
                eval_set=[(X.iloc[corte:], y[corte:])],
                verbose=False,
            )
            mejor = getattr(self.regresor, "best_iteration", None)
            if mejor is not None:
                log.info("XGBoost: parada temprana en la iteración %d", mejor)

        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        return self.regresor.predict(self._alinear_columnas(X))

    def importancia_features(self) -> pd.Series | None:
        if not self.entrenado:
            return None
        return (
            pd.Series(self.regresor.feature_importances_, index=self.columnas_features)
            .sort_values(ascending=False)
        )
