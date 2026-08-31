"""Interfaz común de los modelos predictivos.

Todos los modelos —desde una regresión lineal hasta una LSTM— exponen la misma
API: ``fit`` / ``predict`` / ``guardar`` / ``cargar``. Gracias a eso el script
de entrenamiento los recorre en un bucle sin conocer sus detalles internos, y
añadir un modelo nuevo (SARIMA, Prophet, LightGBM...) no obliga a tocar nada
más. Es el patrón *Strategy*.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.models.metricas import Metricas, evaluar

RUTA_ARTEFACTOS = Path(__file__).parent / "artifacts"


class ModeloPredictivo(ABC):
    """Contrato que cumple todo modelo del proyecto."""

    #: Nombre legible, se usa en la base de datos y en los informes.
    nombre: str = "base"

    def __init__(self, **hiperparametros: Any) -> None:
        self.hiperparametros = hiperparametros
        self.columnas_features: list[str] = []
        self.entrenado: bool = False

    # -- Métodos que cada modelo implementa ---------------------------------

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> ModeloPredictivo:
        """Entrena el modelo. Debe devolver `self` para permitir encadenar."""

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predice el precio para las filas de `X`."""

    # -- Comportamiento compartido ------------------------------------------

    def evaluar(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> Metricas:
        """Predice sobre `X` y devuelve las métricas frente a `y`."""
        self._verificar_entrenado()
        return evaluar(np.asarray(y, dtype=float), self.predict(X))

    def importancia_features(self) -> pd.Series | None:
        """Importancia de cada variable, si el modelo la expone.

        Devuelve `None` para modelos que no la ofrecen (por ejemplo, la LSTM).
        """
        return None

    def guardar(self, ruta: Path | str | None = None) -> Path:
        """Serializa el modelo completo con `joblib`."""
        self._verificar_entrenado()
        ruta = Path(ruta) if ruta else RUTA_ARTEFACTOS / f"{self.nombre}.joblib"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, ruta)
        return ruta

    @staticmethod
    def cargar(ruta: Path | str) -> ModeloPredictivo:
        """Carga un modelo previamente serializado."""
        ruta = Path(ruta)
        if not ruta.exists():
            raise FileNotFoundError(f"No existe el artefacto {ruta}")
        modelo = joblib.load(ruta)
        if not isinstance(modelo, ModeloPredictivo):
            raise TypeError(f"{ruta} no contiene un ModeloPredictivo")
        return modelo

    # -- Internos -----------------------------------------------------------

    def _verificar_entrenado(self) -> None:
        if not self.entrenado:
            raise RuntimeError(
                f"El modelo '{self.nombre}' no está entrenado. Llama a fit() primero."
            )

    def _alinear_columnas(self, X: pd.DataFrame) -> pd.DataFrame:
        """Reordena y valida las columnas de entrada.

        Protege del error más común y más silencioso en producción: llamar a
        `predict` con las columnas en otro orden que en `fit`. Sin esta
        comprobación el modelo devolvería números perfectamente plausibles y
        completamente equivocados.
        """
        faltantes = set(self.columnas_features) - set(X.columns)
        if faltantes:
            raise ValueError(f"Faltan columnas en la entrada: {sorted(faltantes)}")
        return X[self.columnas_features]

    def __repr__(self) -> str:  # pragma: no cover
        estado = "entrenado" if self.entrenado else "sin entrenar"
        return f"<{type(self).__name__} '{self.nombre}' ({estado})>"
