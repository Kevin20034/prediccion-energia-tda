"""Métricas de error para comparar modelos.

Las tres del trabajo de grado, y por qué se usan las tres a la vez:

* **MAE** (error absoluto medio) — en COP/kWh, directamente interpretable:
  "el modelo se equivoca en promedio X pesos por kilovatio-hora".
* **RMSE** (raíz del error cuadrático medio) — penaliza los errores grandes.
  Si RMSE >> MAE, el modelo falla mucho en los picos de precio, que es
  precisamente cuando una predicción importa.
* **MAPE** (error porcentual absoluto medio) — adimensional, permite comparar
  entre periodos con niveles de precio muy distintos.

Se añade **R²** como referencia de bondad de ajuste.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Metricas:
    """Resultado de evaluar un modelo sobre un conjunto."""

    mae: float
    rmse: float
    mape: float
    r2: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"MAE={self.mae:9.2f}  RMSE={self.rmse:9.2f}  "
            f"MAPE={self.mape:6.2f}%  R2={self.r2:6.3f}"
        )


def mae(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_real - y_pred)))


def rmse(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((y_real - y_pred) ** 2)))


def mape(y_real: np.ndarray, y_pred: np.ndarray, epsilon: float = 1e-8) -> float:
    """MAPE en porcentaje.

    Se excluyen los reales cercanos a cero: dividir por ellos dispara el MAPE
    a valores absurdos y haría incomparables los modelos. Es la limitación
    conocida de esta métrica y conviene declararla en la tesis.
    """
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    validos = np.abs(y_real) > epsilon
    if not validos.any():
        return float("nan")

    return float(
        np.mean(np.abs((y_real[validos] - y_pred[validos]) / y_real[validos])) * 100
    )


def r2(y_real: np.ndarray, y_pred: np.ndarray) -> float:
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    ss_res = float(np.sum((y_real - y_pred) ** 2))
    ss_tot = float(np.sum((y_real - np.mean(y_real)) ** 2))
    if ss_tot == 0:
        return float("nan")
    return 1 - ss_res / ss_tot


def evaluar(y_real: np.ndarray, y_pred: np.ndarray) -> Metricas:
    """Calcula las cuatro métricas de una vez."""
    y_real = np.asarray(y_real, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()

    if y_real.shape != y_pred.shape:
        raise ValueError(
            f"Dimensiones incompatibles: y_real={y_real.shape}, y_pred={y_pred.shape}"
        )
    if y_real.size == 0:
        raise ValueError("No hay datos que evaluar")

    return Metricas(
        mae=mae(y_real, y_pred),
        rmse=rmse(y_real, y_pred),
        mape=mape(y_real, y_pred),
        r2=r2(y_real, y_pred),
    )
