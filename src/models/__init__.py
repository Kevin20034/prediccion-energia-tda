"""Motor de analítica predictiva: modelos, métricas y entrenamiento."""

from src.models.base import ModeloPredictivo
from src.models.lstm_model import ModeloLSTM
from src.models.metricas import Metricas, evaluar
from src.models.random_forest import ModeloRandomForest
from src.models.regresion_lineal import ModeloRegresionLineal
from src.models.xgboost_model import ModeloXGBoost

#: Catálogo de modelos disponibles. Añadir uno nuevo aquí basta para que entre
#: automáticamente en la comparación del script de entrenamiento.
MODELOS_DISPONIBLES: dict[str, type[ModeloPredictivo]] = {
    ModeloRegresionLineal.nombre: ModeloRegresionLineal,
    ModeloRandomForest.nombre: ModeloRandomForest,
    ModeloXGBoost.nombre: ModeloXGBoost,
    ModeloLSTM.nombre: ModeloLSTM,
}

__all__ = [
    "ModeloPredictivo",
    "ModeloRegresionLineal",
    "ModeloRandomForest",
    "ModeloXGBoost",
    "ModeloLSTM",
    "Metricas",
    "evaluar",
    "MODELOS_DISPONIBLES",
]
