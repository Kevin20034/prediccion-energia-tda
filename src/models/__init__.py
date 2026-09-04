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

#: Modelos que se entrenan por defecto y que sirven la aplicación.
#:
#: Son los tres que ganan de forma consistente en las pruebas sobre datos reales
#: —los tres de la familia de árboles— más el pronóstico ingenuo, que no compite
#: sino que hace de vara de medir: sin él no hay forma de decir si los otros
#: aportan algo sobre repetir el ciclo anterior.
#:
#: Los cinco restantes siguen implementados y disponibles: la comparación entre
#: familias (lineal, serie temporal, red neuronal) es el objeto del trabajo de
#: grado y tiene que poder reproducirse. Se entrenan con
#: ``python -m scripts.entrenar --todos-los-modelos``. Lo que cambia aquí es el
#: valor por defecto, para que el día a día del sistema no cargue con cinco
#: modelos que ya se sabe que pierden y tardan minutos en entrenarse.
MODELOS_PRODUCCION: tuple[str, ...] = (
    ModeloBaselineEstacional.nombre,
    ModeloRandomForest.nombre,
    ModeloXGBoost.nombre,
    ModeloLightGBM.nombre,
)

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
    "MODELOS_PRODUCCION",
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
