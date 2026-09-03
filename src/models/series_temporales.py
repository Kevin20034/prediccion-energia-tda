"""Modelos clásicos de series de tiempo: SARIMAX y Holt-Winters.

Qué aportan frente a los modelos de aprendizaje automático
----------------------------------------------------------

Los modelos de árboles y la regresión ven cada fila como una observación
independiente: la estructura temporal solo les llega a través de los rezagos que
se les construyen a mano en `processing.features`. SARIMAX y Holt-Winters, en
cambio, **modelan la dependencia temporal de forma explícita**: el primero con
términos autorregresivos y de media móvil (más su versión estacional), el
segundo descomponiendo la serie en nivel, tendencia y estacionalidad.

Que un enfoque le gane al otro es un resultado del trabajo de grado, no un
detalle de implementación:

* Si ganan los clásicos, la serie es esencialmente estacionaria alrededor de un
  patrón estacional estable y no hacía falta más maquinaria.
* Si ganan los de ML, lo que manda son las exógenas y sus interacciones
  no lineales —hidrología, restricciones, ENSO—, que un ARIMA solo puede
  incorporar linealmente.

Cómo se hace justa la comparación
---------------------------------

Un SARIMA "a secas" pronosticaría el conjunto de prueba entero por extrapolación
pura y perdería contra cualquier modelo con exógenas, pero por una razón
tramposa: no por ser peor, sino por recibir menos información. Por eso aquí
SARIMAX recibe **las mismas variables exógenas** que los demás modelos (una
selección de las más correlacionadas con el objetivo, ya que el ajuste por
máxima verosimilitud no admite cien regresores) y las usa también al pronosticar.

Coste computacional
-------------------

El ajuste por máxima verosimilitud escala mal: con decenas de miles de horas y
estacionalidad 24 no termina en un tiempo razonable. Ambos modelos se ajustan
sobre la **cola** de la serie de entrenamiento (`max_muestras`), que es además
la parte más informativa para pronosticar lo que viene justo después. Es una
limitación real y se documenta como tal, no se esconde.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from src.core.logging import get_logger
from src.models.base import ModeloPredictivo

log = get_logger(__name__)


class _ModeloSerieTemporal(ModeloPredictivo):
    """Base común: ajusta sobre la cola de la serie y pronostica hacia adelante.

    El contrato de `predict` es distinto al de los modelos tabulares y conviene
    tenerlo claro: **no** predice fila a fila de forma independiente, sino que
    produce un pronóstico de `len(X)` pasos consecutivos a partir del final del
    entrenamiento. Con el *split* cronológico del proyecto eso es exactamente lo
    que se quiere —el conjunto de prueba es el tramo inmediatamente posterior—,
    pero significa que llamar a `predict` sobre filas sueltas y desordenadas no
    tendría sentido.
    """

    def __init__(self, max_muestras: int = 3000, **kwargs) -> None:
        super().__init__(max_muestras=max_muestras, **kwargs)
        self.max_muestras = max_muestras
        self.resultado = None
        self.media_entrenamiento: float = 0.0

    def _cola(self, X: pd.DataFrame, y: np.ndarray) -> tuple[pd.DataFrame, np.ndarray]:
        if len(y) <= self.max_muestras:
            return X, y
        log.info(
            "%s: se ajusta sobre las últimas %d de %d muestras",
            self.nombre,
            self.max_muestras,
            len(y),
        )
        return X.iloc[-self.max_muestras :], y[-self.max_muestras :]

    def _pronostico_plano(self, n: int) -> np.ndarray:
        """Salida de emergencia si el ajuste no converge."""
        return np.full(n, self.media_entrenamiento)


class ModeloSARIMAX(_ModeloSerieTemporal):
    """SARIMAX estacional con variables exógenas."""

    nombre = "sarimax"

    def __init__(
        self,
        orden: tuple[int, int, int] = (2, 0, 1),
        orden_estacional: tuple[int, int, int, int] = (1, 0, 1, 24),
        max_exogenas: int = 8,
        max_muestras: int = 3000,
        max_iteraciones: int = 60,
        **kwargs,
    ) -> None:
        super().__init__(
            max_muestras=max_muestras,
            orden=orden,
            orden_estacional=orden_estacional,
            max_exogenas=max_exogenas,
            **kwargs,
        )
        self.orden = orden
        self.orden_estacional = orden_estacional
        self.max_exogenas = max_exogenas
        self.max_iteraciones = max_iteraciones
        self.exogenas: list[str] = []
        self.escalador: StandardScaler | None = None
        self.limite_inferior = -np.inf
        self.limite_superior = np.inf

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloSARIMAX:
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float)
        self.media_entrenamiento = float(np.mean(y))
        # Rango plausible para el saneado de la salida (ver `predict`).
        margen = (np.max(y) - np.min(y)) or abs(self.media_entrenamiento) or 1.0
        self.limite_inferior = float(np.min(y) - margen)
        self.limite_superior = float(np.max(y) + margen)

        X_cola, y_cola = self._cola(X, y)
        self.exogenas = _seleccionar_exogenas(X_cola, y_cola, self.max_exogenas)

        exog = None
        if self.exogenas:
            # Las exógenas se estandarizan. Sin escalar, conviven variables de
            # orden 1 (fracciones, indicadores) con otras de orden 10⁷ (energía
            # en kWh), y la máxima verosimilitud tiene que buscar coeficientes
            # que difieren en siete órdenes de magnitud: el optimizador no
            # converge y devuelve un modelo cuyo pronóstico diverge.
            self.escalador = StandardScaler().fit(X_cola[self.exogenas])
            exog = self.escalador.transform(X_cola[self.exogenas])

        modelo = SARIMAX(
            y_cola,
            exog=exog,
            order=self.orden,
            seasonal_order=self.orden_estacional,
            # Estacionariedad **exigida**, a diferencia de la primera versión.
            # Relajarla dejaba que las raíces del polinomio autorregresivo
            # cayeran fuera del círculo unidad; el ajuste no fallaba, pero al
            # pronosticar miles de pasos la serie crecía exponencialmente y el
            # MAPE resultante llegaba a 10²⁸. Un modelo que puede divergir así
            # no es comparable con los demás: es ruido en la tabla.
            enforce_stationarity=True,
            enforce_invertibility=True,
        )

        with warnings.catch_warnings():
            # La optimización avisa de convergencia en casi todas las series
            # reales; el aviso no aporta nada sobre el resultado y ensucia el log.
            warnings.simplefilter("ignore")
            self.resultado = modelo.fit(disp=False, maxiter=self.max_iteraciones)

        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()
        X = self._alinear_columnas(X)

        if self.resultado is None:
            return self._pronostico_plano(len(X))

        exog = None
        if self.exogenas:
            exog = X[self.exogenas]
            exog = self.escalador.transform(exog) if self.escalador else exog.to_numpy(float)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pronostico = np.asarray(
                    self.resultado.forecast(steps=len(X), exog=exog), dtype=float
                )
        except (ValueError, np.linalg.LinAlgError) as exc:
            log.warning("SARIMAX no pudo pronosticar (%s); se devuelve la media", exc)
            return self._pronostico_plano(len(X))

        pronostico = np.where(np.isfinite(pronostico), pronostico, self.media_entrenamiento)
        # Recorte al rango históricamente plausible. Es un cinturón de seguridad
        # además de la estacionariedad: si aun así el modelo se desbocara, la
        # tabla comparativa mostraría un error grande —que es la verdad— en vez
        # de un número astronómico que rompe las escalas de todas las gráficas.
        return np.clip(pronostico, self.limite_inferior, self.limite_superior)

    def importancia_features(self) -> pd.Series | None:
        """Magnitud de los coeficientes de las exógenas.

        Solo cubre las variables que entraron al modelo: SARIMAX no puntúa las
        que se dejaron fuera por el límite de `max_exogenas`.
        """
        if not self.entrenado or self.resultado is None or not self.exogenas:
            return None
        parametros = self.resultado.params[: len(self.exogenas)]
        return pd.Series(np.abs(parametros), index=self.exogenas).sort_values(ascending=False)


class ModeloHoltWinters(_ModeloSerieTemporal):
    """Suavizado exponencial triple (nivel + tendencia + estacionalidad diaria).

    Es el más simple de los modelos de serie temporal y no admite exógenas: solo
    descompone la propia serie. Su papel es marcar cuánto se puede conseguir con
    la estructura temporal a secas, sin ninguna variable de mercado.
    """

    nombre = "holt_winters"

    def __init__(
        self,
        periodos_estacionales: int = 24,
        tendencia: str | None = "add",
        estacionalidad: str | None = "add",
        amortiguar: bool = True,
        max_muestras: int = 2000,
        **kwargs,
    ) -> None:
        super().__init__(
            max_muestras=max_muestras,
            periodos_estacionales=periodos_estacionales,
            tendencia=tendencia,
            estacionalidad=estacionalidad,
            amortiguar=amortiguar,
            **kwargs,
        )
        self.periodos_estacionales = periodos_estacionales
        self.tendencia = tendencia
        self.estacionalidad = estacionalidad
        # La tendencia amortiguada evita que una pendiente ajustada sobre unos
        # pocos miles de horas se extrapole indefinidamente y el pronóstico a un
        # mes se dispare a valores imposibles.
        self.amortiguar = amortiguar

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloHoltWinters:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing

        self.columnas_features = list(X.columns)
        y = np.asarray(y, dtype=float)
        self.media_entrenamiento = float(np.mean(y))

        _, y_cola = self._cola(X, y)

        if len(y_cola) < 2 * self.periodos_estacionales:
            raise ValueError(
                f"Holt-Winters necesita al menos {2 * self.periodos_estacionales} "
                f"muestras; se recibieron {len(y_cola)}"
            )

        modelo = ExponentialSmoothing(
            y_cola,
            trend=self.tendencia,
            seasonal=self.estacionalidad,
            seasonal_periods=self.periodos_estacionales,
            damped_trend=self.amortiguar and self.tendencia is not None,
            initialization_method="estimated",
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.resultado = modelo.fit(optimized=True)

        self.entrenado = True
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        self._verificar_entrenado()

        if self.resultado is None:
            return self._pronostico_plano(len(X))

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pronostico = np.asarray(self.resultado.forecast(len(X)), dtype=float)
        except (ValueError, np.linalg.LinAlgError) as exc:
            log.warning("Holt-Winters no pudo pronosticar (%s); se devuelve la media", exc)
            return self._pronostico_plano(len(X))

        return np.where(np.isfinite(pronostico), pronostico, self.media_entrenamiento)


# ---------------------------------------------------------------------------


def _seleccionar_exogenas(X: pd.DataFrame, y: np.ndarray, maximo: int) -> list[str]:
    """Elige las exógenas más correlacionadas con el objetivo, sin redundancias.

    Dos filtros, en este orden:

    1. **Correlación con el objetivo** — se ordenan por |r| de Pearson.
    2. **Descarte de casi duplicadas** — se rechaza una candidata si su
       correlación con alguna ya elegida supera 0,95. Los rezagos consecutivos
       (`objetivo_lag_1`, `objetivo_lag_2`...) son casi idénticos entre sí:
       meterlos todos gastaría el presupuesto de regresores en la misma
       información y haría singular la matriz del ajuste.
    """
    if maximo <= 0 or X.empty:
        return []

    numericas = X.select_dtypes(include="number")
    if numericas.empty:
        return []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        correlaciones = (
            numericas.corrwith(pd.Series(y, index=numericas.index)).abs().dropna()
        )

    candidatas = correlaciones.sort_values(ascending=False).index.tolist()
    elegidas: list[str] = []

    for candidata in candidatas:
        if len(elegidas) >= maximo:
            break
        if any(
            abs(numericas[candidata].corr(numericas[elegida])) > 0.95 for elegida in elegidas
        ):
            continue
        # Una columna constante no aporta y hace singular la matriz de diseño.
        if numericas[candidata].nunique() <= 1:
            continue
        elegidas.append(candidata)

    log.debug("SARIMAX: exógenas seleccionadas -> %s", elegidas)
    return elegidas
