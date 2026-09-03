"""Motor de analítica predictiva: modelos, métricas y entrenamiento."""

from src.models.base import ModeloPredictivo
from src.models.baseline import ModeloBaselineEstacional
from src.models.elastic_net import ModeloElasticNet
from src.models.lightgbm_model import ModeloLightGBM
from src.models.lstm_model import ModeloLSTM
from src.models.metricas import Metricas, evaluar
from src.models.random_forest import ModeloRandomForest
from src.models.regresion_lineal import ModeloRegresionLineal
from src.models.series_temporales import ModeloHoltWinters, ModeloSARIMAX
from src.models.xgboost_model import ModeloXGBoost

#: Catálogo de modelos disponibles. Añadir uno nuevo aquí basta para que entre
#: automáticamente en la comparación del script de entrenamiento.
#:
#: El orden importa para la lectura de la tabla comparativa: primero la
#: referencia ingenua, después los lineales, luego los de árboles, y al final
#: los que modelan la secuencia (series temporales clásicas y la red neuronal).
MODELOS_DISPONIBLES: dict[str, type[ModeloPredictivo]] = {
    ModeloBaselineEstacional.nombre: ModeloBaselineEstacional,
    ModeloRegresionLineal.nombre: ModeloRegresionLineal,
    ModeloElasticNet.nombre: ModeloElasticNet,
    ModeloRandomForest.nombre: ModeloRandomForest,
    ModeloXGBoost.nombre: ModeloXGBoost,
    ModeloLightGBM.nombre: ModeloLightGBM,
    ModeloHoltWinters.nombre: ModeloHoltWinters,
    ModeloSARIMAX.nombre: ModeloSARIMAX,
    ModeloLSTM.nombre: ModeloLSTM,
}

#: Familia a la que pertenece cada modelo. La interfaz agrupa la comparación por
#: familias porque la pregunta interesante del trabajo de grado no es qué modelo
#: concreto gana, sino qué **enfoque** gana.
FAMILIAS: dict[str, str] = {
    ModeloBaselineEstacional.nombre: "referencia",
    ModeloRegresionLineal.nombre: "lineal",
    ModeloElasticNet.nombre: "lineal",
    ModeloRandomForest.nombre: "arboles",
    ModeloXGBoost.nombre: "arboles",
    ModeloLightGBM.nombre: "arboles",
    ModeloHoltWinters.nombre: "serie_temporal",
    ModeloSARIMAX.nombre: "serie_temporal",
    ModeloLSTM.nombre: "red_neuronal",
}

__all__ = [
    "FAMILIAS",
    "MODELOS_DISPONIBLES",
    "Metricas",
    "ModeloBaselineEstacional",
    "ModeloElasticNet",
    "ModeloHoltWinters",
    "ModeloLSTM",
    "ModeloLightGBM",
    "ModeloPredictivo",
    "ModeloRandomForest",
    "ModeloRegresionLineal",
    "ModeloSARIMAX",
    "ModeloXGBoost",
    "evaluar",
]
