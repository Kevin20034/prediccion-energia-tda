"""Métricas de error para comparar modelos.

Por qué se usan varias a la vez:

* **MAE** (error absoluto medio) — en la unidad del objetivo, directamente
  interpretable: "el modelo se equivoca en promedio X COP/kWh".
* **RMSE** (raíz del error cuadrático medio) — penaliza los errores grandes.
  Si RMSE >> MAE, el modelo falla mucho en los picos, que es precisamente
  cuando una predicción importa.
* **MAPE** (error porcentual absoluto medio) — adimensional, permite comparar
  entre periodos con niveles muy distintos. Su defecto conocido es que explota
  cuando el valor real se acerca a cero.
* **sMAPE** (MAPE simétrico) — corrige la asimetría del MAPE, que castiga más
  las sobreestimaciones que las subestimaciones del mismo tamaño relativo.
* **MASE** (error absoluto escalado) — el error del modelo dividido por el de
  un pronóstico ingenuo estacional. Es la única de todas que responde a la
  pregunta que de verdad importa: **¿esto es mejor que repetir lo que pasó
  ayer a la misma hora?** Un MASE ≥ 1 significa que no, por muy bonito que sea
  el R².

Se añade **R²** como referencia de bondad de ajuste.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

#: Estacionalidad por defecto de las series horarias del proyecto: 24 h.
ESTACIONALIDAD = 24


@dataclass(frozen=True, slots=True)
class Metricas:
    """Resultado de evaluar un modelo sobre un conjunto."""

    mae: float
    rmse: float
    mape: float
    r2: float
    smape: float = float("nan")
    mase: float = float("nan")

    def as_dict(self) -> dict[str, float]:
        return asdict(self)

    def __str__(self) -> str:
        return (
            f"MAE={self.mae:9.2f}  RMSE={self.rmse:9.2f}  "
            f"MAPE={self.mape:6.2f}%  R2={self.r2:6.3f}  MASE={self.mase:5.3f}"
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


def smape(y_real: np.ndarray, y_pred: np.ndarray, epsilon: float = 1e-8) -> float:
    """MAPE simétrico, en porcentaje y acotado en [0, 200].

    El MAPE clásico divide por el valor real, así que una sobreestimación del
    doble (error del 100 %) pesa mucho menos que una subestimación a la mitad
    (error del 50 %... del real, pero del 100 % del predicho). El sMAPE divide
    por la media de ambos y elimina esa asimetría, que en comparación de
    modelos favorece sistemáticamente a los que subestiman.
    """
    y_real = np.asarray(y_real, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    denominador = (np.abs(y_real) + np.abs(y_pred)) / 2
    validos = denominador > epsilon
    if not validos.any():
        return float("nan")

    return float(
        np.mean(np.abs(y_real[validos] - y_pred[validos]) / denominador[validos]) * 100
    )


def estacionalidad_para(horizonte: int, ciclo: int = ESTACIONALIDAD) -> int:
    """Desfase del pronóstico ingenuo con el que comparar un horizonte dado.

    Esto importa más de lo que parece. Si el MASE de un pronóstico a 720 h se
    escalara con el error del ingenuo **a 24 h**, se estaría dividiendo un
    problema difícil por uno fácil: el resultado saldría muy por encima de 1
    aunque el modelo fuese excelente, y la lectura "MASE < 1 gana al ingenuo"
    dejaría de ser cierta fuera del horizonte de un día.

    La referencia correcta es el ingenuo **al mismo horizonte**: para 24 h,
    "lo mismo que ayer a esta hora"; para 168 h, "lo mismo que este día de la
    semana pasada"; para 720 h, "lo mismo que hace treinta días". Se redondea
    al múltiplo del ciclo diario para que la comparación siempre caiga en la
    misma hora del día y no mezcle una hora punta con una de madrugada.
    """
    if horizonte <= 0:
        return ciclo
    return max(ciclo, ciclo * round(horizonte / ciclo) or ciclo)


def mase(
    y_real: np.ndarray,
    y_pred: np.ndarray,
    y_historico: np.ndarray | None = None,
    estacionalidad: int = ESTACIONALIDAD,
) -> float:
    """Error absoluto escalado por el del pronóstico ingenuo estacional.

    El denominador es el MAE de "predecir que dentro de `estacionalidad` horas
    pasará lo mismo que ahora", calculado sobre el histórico de entrenamiento
    si se proporciona y, si no, sobre la propia serie real evaluada.

    Interpretación: **MASE < 1 = el modelo le gana al pronóstico ingenuo** del
    mismo horizonte —ver `estacionalidad_para`, que es quien lo hace comparable.
    Es la métrica que evita el error clásico de celebrar un R² de 0,98 en una
    serie que simplemente es muy autocorrelacionada.
    """
    y_real = np.asarray(y_real, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    referencia = (
        np.asarray(y_historico, dtype=float).ravel() if y_historico is not None else y_real
    )

    if referencia.size <= estacionalidad:
        return float("nan")

    escala = float(np.mean(np.abs(referencia[estacionalidad:] - referencia[:-estacionalidad])))
    if escala <= 0:
        return float("nan")

    return float(np.mean(np.abs(y_real - y_pred)) / escala)


def evaluar(
    y_real: np.ndarray,
    y_pred: np.ndarray,
    y_historico: np.ndarray | None = None,
    estacionalidad: int = ESTACIONALIDAD,
) -> Metricas:
    """Calcula todas las métricas de una vez.

    Args:
        y_real: valores observados.
        y_pred: valores estimados por el modelo.
        y_historico: serie de entrenamiento, para escalar el MASE con el error
            del pronóstico ingenuo *fuera* del conjunto evaluado. Si no se
            pasa, se escala con la propia serie evaluada (menos riguroso, pero
            sigue siendo comparable entre modelos del mismo experimento).
        estacionalidad: periodo del pronóstico ingenuo, en pasos. 24 para series
            horarias con ciclo diario.
    """
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
        smape=smape(y_real, y_pred),
        mase=mase(y_real, y_pred, y_historico, estacionalidad),
    )
