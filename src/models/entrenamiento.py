"""Orquestador de entrenamiento: entrena todos los modelos y elige el mejor.

Flujo
-----

1. Limpia los datos y construye las variables predictoras para el **objetivo** y
   el **horizonte** pedidos.
2. Parte el conjunto **cronológicamente** en entrenamiento y prueba.
3. Entrena cada modelo del catálogo y lo evalúa sobre el conjunto de prueba.
4. Opcionalmente valida cada modelo con *walk-forward* (`TimeSeriesSplit`), que
   mide si el modelo es estable o solo funciona en un tramo concreto.
5. Calcula la **banda de predicción** del ganador a partir de los cuantiles de
   sus residuos.
6. Registra las métricas de todos en `ejecuciones_entrenamiento`.
7. Serializa el ganador en un artefacto por (objetivo, horizonte).

Un artefacto por horizonte, y por qué
-------------------------------------

Pronosticar a 24 h, a una semana y a un mes **no** es el mismo problema resuelto
tres veces con más pasos. La estrategia aquí es *direct multi-step*: se entrena
un modelo distinto para cada horizonte, cada uno con su propio objetivo
desplazado. La alternativa —predecir una hora y realimentar la predicción 720
veces— acumula el error de cada paso sobre el siguiente y a un mes vista produce
cifras sin ningún valor.

Criterio de selección
---------------------

Por defecto el **RMSE**, no el MAE: penaliza más los errores grandes, y en un
mercado energético equivocarse mucho en un pico de precio cuesta bastante más
que equivocarse un poco muchas veces. El **MASE** se registra siempre, porque es
lo único que responde a si el modelo aporta algo sobre repetir el pasado.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance
from sklearn.model_selection import TimeSeriesSplit
from sqlalchemy.orm import Session

from src.core.logging import get_logger
from src.database.models import EjecucionEntrenamiento
from src.models import FAMILIAS, MODELOS_DISPONIBLES, MODELOS_PRODUCCION
from src.models.base import RUTA_ARTEFACTOS, ModeloPredictivo
from src.models.metricas import Metricas, estacionalidad_para
from src.processing.features import (
    OBJETIVO_POR_DEFECTO,
    columnas_features,
    construir_features,
    dividir_train_test,
    unidad_de,
    validar_objetivo,
)
from src.processing.limpieza import limpiar

log = get_logger(__name__)

METRICAS_VALIDAS = {"rmse", "mae", "mape", "smape", "mase"}

#: Horizontes que la interfaz ofrece, en horas.
HORIZONTES: dict[str, int] = {"24h": 24, "7d": 168, "30d": 720}

#: Cuantiles de los residuos que definen la banda de predicción. El 80 % central
#: es un compromiso habitual: una banda del 95 % en un mercado con picos de
#: escasez sale tan ancha que deja de informar.
CUANTILES_BANDA = (0.10, 0.90)

#: Repeticiones y tamaño de muestra de la importancia por permutación. Es una
#: técnica cara —una predicción completa por variable y repetición—, así que se
#: acota; con 2.000 filas el ranking ya es estable.
PERMUTACION_REPETICIONES = 3
PERMUTACION_MUESTRAS = 2000


def ruta_artefacto(objetivo: str, horizonte: int) -> Path:
    """Ruta del modelo ganador para una combinación objetivo/horizonte."""
    return RUTA_ARTEFACTOS / f"mejor__{objetivo}__{horizonte}h.joblib"


@dataclass
class ArtefactoPronostico:
    """Lo que se serializa a disco: el modelo y todo lo necesario para usarlo.

    Guardar solo el modelo no basta. Sin saber para qué objetivo y horizonte se
    entrenó, ni con qué dispersión de residuos, el artefacto se puede aplicar
    por error a otra cosa y devolver números plausibles y equivocados —el fallo
    más caro y más silencioso que puede tener un sistema predictivo.
    """

    modelo: ModeloPredictivo
    objetivo: str
    horizonte: int
    unidad: str
    residuo_inferior: float
    residuo_superior: float
    metricas: dict[str, float]
    columnas: list[str]
    entrenado_en: datetime = field(default_factory=lambda: datetime.now(UTC))

    def banda(self, estimaciones: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Aplica la banda de predicción empírica a un vector de estimaciones."""
        return estimaciones + self.residuo_inferior, estimaciones + self.residuo_superior


@dataclass
class ResultadoModelo:
    """Resultado del entrenamiento de un modelo concreto."""

    nombre: str
    modelo: ModeloPredictivo | None
    metricas: Metricas | None
    duracion_segundos: float
    error: str | None = None
    rmse_validacion: float | None = None
    desviacion_validacion: float | None = None
    n_pliegues: int = 0
    importancia: dict[str, float] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.error is None and self.metricas is not None

    @property
    def familia(self) -> str:
        return FAMILIAS.get(self.nombre, "otro")


@dataclass
class ResultadoEntrenamiento:
    """Resultado global de una ejecución de entrenamiento."""

    resultados: list[ResultadoModelo]
    mejor: ResultadoModelo | None
    ruta_artefacto: Path | None
    objetivo: str
    horizonte: int
    criterio: str
    n_train: int
    n_test: int

    def tabla_comparativa(self) -> pd.DataFrame:
        """Tabla lista para pegar en el documento del trabajo de grado."""
        filas = [
            {
                "modelo": r.nombre,
                "familia": r.familia,
                "MAE": round(r.metricas.mae, 2),
                "RMSE": round(r.metricas.rmse, 2),
                "MAPE (%)": round(r.metricas.mape, 2),
                "sMAPE (%)": round(r.metricas.smape, 2),
                "MASE": round(r.metricas.mase, 3),
                "R2": round(r.metricas.r2, 4),
                "segundos": round(r.duracion_segundos, 1),
                "mejor": r is self.mejor,
            }
            for r in self.resultados
            if r.ok
        ]
        if not filas:
            return pd.DataFrame()
        return pd.DataFrame(filas).sort_values("RMSE").reset_index(drop=True)


def entrenar_todos(
    df: pd.DataFrame,
    *,
    db: Session | None = None,
    modelos: list[str] | None = None,
    objetivo: str = OBJETIVO_POR_DEFECTO,
    horizonte: int = 24,
    proporcion_test: float = 0.2,
    criterio: str = "rmse",
    pliegues_validacion: int = 0,
    guardar_mejor: bool = True,
) -> ResultadoEntrenamiento:
    """Entrena y compara todos los modelos sobre los datos dados.

    Args:
        df: datos históricos crudos (con `fecha_hora` y la columna objetivo).
        db: sesión opcional; si se pasa, se registran las métricas en la BD.
        modelos: subconjunto de nombres a entrenar. Por defecto, los de
            producción (`MODELOS_PRODUCCION`); pasar `list(MODELOS_DISPONIBLES)`
            para la comparación completa entre familias.
        objetivo: `precio_bolsa` o `demanda_real`.
        horizonte: horas hacia adelante a predecir (24, 168 o 720 en la interfaz).
        proporcion_test: tamaño del conjunto de prueba (corte cronológico).
        criterio: métrica de selección del mejor modelo.
        pliegues_validacion: pliegues de la validación *walk-forward*. `0` la
            desactiva, que es lo razonable cuando el entrenamiento se dispara
            desde una petición HTTP síncrona: multiplica el tiempo por el número
            de pliegues.
        guardar_mejor: si se serializa el ganador a disco.
    """
    if criterio not in METRICAS_VALIDAS:
        raise ValueError(f"criterio debe ser uno de {sorted(METRICAS_VALIDAS)}")
    validar_objetivo(objetivo)

    nombres = modelos or list(MODELOS_PRODUCCION)
    desconocidos = set(nombres) - set(MODELOS_DISPONIBLES)
    if desconocidos:
        raise ValueError(
            f"Modelos desconocidos: {sorted(desconocidos)}. "
            f"Disponibles: {sorted(MODELOS_DISPONIBLES)}"
        )

    # --- Preparación de datos ---------------------------------------------
    log.info(
        "Preparando datos (%d registros crudos) · objetivo=%s · horizonte=%dh",
        len(df),
        objetivo,
        horizonte,
    )
    datos = construir_features(
        limpiar(df, objetivo=objetivo), objetivo=objetivo, horizonte=horizonte
    )
    if datos.empty:
        raise ValueError("No quedaron datos tras la limpieza y el feature engineering")

    features = columnas_features(datos, objetivo)
    train, test = dividir_train_test(datos, proporcion_test)

    if train.empty or test.empty:
        raise ValueError(
            f"Datos insuficientes para el split: train={len(train)}, test={len(test)}"
        )

    X_train, y_train = train[features], train["objetivo"]
    X_test, y_test = test[features], test["objetivo"]
    historico = y_train.to_numpy(dtype=float)
    # El MASE se escala con el ingenuo del MISMO horizonte; si no, comparar el
    # MASE de 24 h con el de 720 h no significaría nada.
    estacionalidad = estacionalidad_para(horizonte)

    log.info(
        "Entrenando %d modelos | %d features | train=%d | test=%d",
        len(nombres),
        len(features),
        len(train),
        len(test),
    )

    # --- Entrenamiento -----------------------------------------------------
    resultados: list[ResultadoModelo] = []

    for nombre in nombres:
        log.info("--- %s ---", nombre)
        inicio = time.perf_counter()
        try:
            modelo = MODELOS_DISPONIBLES[nombre]()
            modelo.fit(X_train, y_train)
            metricas = modelo.evaluar(X_test, y_test, historico, estacionalidad)
            duracion = time.perf_counter() - inicio

            # Un modelo cuyo error no es finito no "quedó el último": no
            # produjo un pronóstico. Dejarlo en la tabla con un MAPE de 10²⁸
            # rompe la escala de las gráficas y sugiere que compitió.
            if not _metricas_finitas(metricas):
                raise ValueError(
                    "el modelo divergió: las métricas de error no son finitas "
                    f"(RMSE={metricas.rmse}, MAPE={metricas.mape})"
                )

            log.info("%s  %s  (%.1fs)", nombre, metricas, duracion)
            resultado = ResultadoModelo(nombre, modelo, metricas, duracion)
            if pliegues_validacion > 1:
                _validar_walk_forward(resultado, X_train, y_train, pliegues_validacion)
            resultados.append(resultado)
        except Exception as exc:  # noqa: BLE001 - un modelo caído no debe tumbar el resto
            duracion = time.perf_counter() - inicio
            log.exception("El modelo '%s' falló: %s", nombre, exc)
            resultados.append(
                ResultadoModelo(nombre, None, None, duracion, error=f"{type(exc).__name__}: {exc}")
            )

    exitosos = [r for r in resultados if r.ok]
    if not exitosos:
        raise RuntimeError("Ningún modelo se entrenó correctamente")

    mejor = min(exitosos, key=lambda r: getattr(r.metricas, criterio))
    log.info("Mejor modelo por %s: %s (%s)", criterio.upper(), mejor.nombre, mejor.metricas)

    _anotar_importancias(exitosos, mejor, X_test, y_test)

    # --- Persistencia ------------------------------------------------------
    ruta: Path | None = None
    if guardar_mejor and mejor.modelo is not None:
        ruta = _guardar_artefacto(mejor, objetivo, horizonte, X_test, y_test, features)

    if db is not None:
        _registrar_en_bd(
            db, resultados, mejor, ruta, objetivo, horizonte, len(train), len(test)
        )

    return ResultadoEntrenamiento(
        resultados=resultados,
        mejor=mejor,
        ruta_artefacto=ruta,
        objetivo=objetivo,
        horizonte=horizonte,
        criterio=criterio,
        n_train=len(train),
        n_test=len(test),
    )


def cargar_artefacto(
    objetivo: str = OBJETIVO_POR_DEFECTO, horizonte: int = 24
) -> ArtefactoPronostico:
    """Carga el artefacto del ganador para un objetivo y horizonte.

    El resultado se cachea en memoria por (ruta, fecha de modificación): un
    bosque aleatorio serializado ocupa cientos de megabytes y leerlo del disco
    en cada petición de pronóstico añadiría segundos a cada respuesta. La fecha
    de modificación forma parte de la clave, así que reentrenar invalida la
    caché sola, sin reiniciar la API.
    """
    ruta = ruta_artefacto(objetivo, horizonte)
    if not ruta.exists():
        raise FileNotFoundError(
            f"No hay modelo entrenado para {objetivo} a {horizonte}h ({ruta.name}). "
            "Entrena primero: python -m scripts.entrenar (o POST /entrenar)"
        )

    return _cargar_cacheado(str(ruta), ruta.stat().st_mtime_ns)


#: Artefactos que se mantienen en memoria a la vez.
#:
#: Es un tope de memoria, no de rendimiento. Un bosque aleatorio deserializado
#: ocupa bastante más que su archivo, y con la caché sin acotar bastaba con
#: visitar los seis pares objetivo/horizonte para que el proceso se quedara sin
#: memoria y el servidor cerrara la conexión a mitad de respuesta. Cuatro cubre
#: los tres horizontes de un objetivo más el que se estaba mirando antes, que
#: es el patrón real de navegación.
ARTEFACTOS_EN_MEMORIA = 4


@lru_cache(maxsize=ARTEFACTOS_EN_MEMORIA)
def _cargar_cacheado(ruta: str, _marca_tiempo: int) -> ArtefactoPronostico:
    import joblib

    artefacto = joblib.load(ruta)
    if not isinstance(artefacto, ArtefactoPronostico):
        raise TypeError(f"{ruta} no contiene un ArtefactoPronostico")
    log.info("Artefacto cargado en memoria: %s", Path(ruta).name)
    return artefacto


def artefactos_disponibles() -> list[ArtefactoPronostico]:
    """Todos los artefactos entrenados que hay en disco, sin fallar por uno malo.

    Pasa por la misma caché que `cargar_artefacto`, así que recorrer el listado
    deja los modelos calientes en memoria: es lo que aprovecha la precarga del
    arranque de la API.
    """
    encontrados: list[ArtefactoPronostico] = []
    for ruta in sorted(RUTA_ARTEFACTOS.glob("mejor__*.joblib")):
        try:
            artefacto = _cargar_cacheado(str(ruta), ruta.stat().st_mtime_ns)
        except Exception as exc:  # noqa: BLE001 - un artefacto viejo no debe romper el listado
            log.warning("No se pudo cargar %s: %s", ruta.name, exc)
            continue
        encontrados.append(artefacto)
    return encontrados


# ---------------------------------------------------------------------------
# Pasos internos
# ---------------------------------------------------------------------------


def _validar_walk_forward(
    resultado: ResultadoModelo,
    X: pd.DataFrame,
    y: pd.Series,
    pliegues: int,
) -> None:
    """Validación *walk-forward* sobre el conjunto de entrenamiento.

    `TimeSeriesSplit` entrena siempre con el pasado y valida con el futuro
    inmediato, repitiéndolo en varios cortes. Lo que mide no es solo el error
    medio sino su **dispersión**: un modelo con RMSE medio bueno y desviación
    alta funciona bien en unos tramos y mal en otros, y en producción eso es
    peor que un modelo algo peor pero estable.

    Un fallo aquí no invalida el modelo: ya tiene su métrica sobre el conjunto
    de prueba. Se registra y se sigue.
    """
    partidor = TimeSeriesSplit(n_splits=pliegues)
    errores: list[float] = []
    clase = MODELOS_DISPONIBLES[resultado.nombre]

    for indices_train, indices_val in partidor.split(X):
        try:
            modelo = clase()
            modelo.fit(X.iloc[indices_train], y.iloc[indices_train])
            metricas = modelo.evaluar(X.iloc[indices_val], y.iloc[indices_val])
            errores.append(metricas.rmse)
        except Exception as exc:  # noqa: BLE001
            log.warning("%s: un pliegue de validación falló (%s)", resultado.nombre, exc)

    if not errores:
        return

    resultado.rmse_validacion = float(np.mean(errores))
    resultado.desviacion_validacion = float(np.std(errores))
    resultado.n_pliegues = len(errores)
    log.info(
        "%s  walk-forward: RMSE=%.2f ± %.2f (%d pliegues)",
        resultado.nombre,
        resultado.rmse_validacion,
        resultado.desviacion_validacion,
        len(errores),
    )


def _anotar_importancias(
    exitosos: list[ResultadoModelo],
    mejor: ResultadoModelo,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> None:
    """Rellena `importancia` en cada resultado.

    Al ganador se le calcula **importancia por permutación**, que mide cuánto
    empeora el error real al barajar cada variable. Es cara pero no tiene el
    sesgo hacia variables de alta cardinalidad que arrastran las importancias
    internas de los árboles, y es la que se muestra en la interfaz. Al resto se
    les toma la importancia que cada uno expone, que sale gratis.
    """
    for resultado in exitosos:
        if resultado is mejor or resultado.modelo is None:
            continue
        propia = resultado.modelo.importancia_features()
        if propia is not None and not propia.empty:
            resultado.importancia = {k: float(v) for k, v in propia.head(25).items()}

    if mejor.modelo is None:
        return

    muestras = min(PERMUTACION_MUESTRAS, len(X_test))
    X_muestra = X_test.tail(muestras)
    y_muestra = y_test.tail(muestras)

    try:
        calculo = permutation_importance(
            _AdaptadorSklearn(mejor.modelo),
            X_muestra,
            y_muestra,
            n_repeats=PERMUTACION_REPETICIONES,
            random_state=42,
            scoring="neg_root_mean_squared_error",
        )
        serie = pd.Series(calculo.importances_mean, index=list(X_muestra.columns))
        mejor.importancia = {
            k: float(v) for k, v in serie.sort_values(ascending=False).head(25).items()
        }
        log.info("Importancia por permutación calculada para '%s'", mejor.nombre)
    except Exception as exc:  # noqa: BLE001 - es un extra, no debe tumbar el entrenamiento
        log.warning("No se pudo calcular la importancia por permutación: %s", exc)
        propia = mejor.modelo.importancia_features()
        if propia is not None and not propia.empty:
            mejor.importancia = {k: float(v) for k, v in propia.head(25).items()}


class _AdaptadorSklearn:
    """Envuelve un `ModeloPredictivo` con la interfaz mínima que pide sklearn.

    `permutation_importance` espera un estimador con `predict` y con los
    atributos de un estimador ya ajustado. Los modelos del proyecto tienen
    `predict`, pero no heredan de `BaseEstimator`; este adaptador evita tener
    que forzar esa herencia solo para una función de diagnóstico.
    """

    _estimator_type = "regressor"

    def __init__(self, modelo: ModeloPredictivo) -> None:
        self.modelo = modelo

    def fit(self, X, y):  # pragma: no cover - sklearn no lo llama aquí
        return self

    def predict(self, X):
        return self.modelo.predict(X)

    def score(self, X, y):
        y_pred = self.predict(X)
        return -float(np.sqrt(np.mean((np.asarray(y, dtype=float) - y_pred) ** 2)))

    def get_params(self, deep: bool = True) -> dict:  # pragma: no cover
        return {"modelo": self.modelo}

    def __sklearn_tags__(self):
        """sklearn ≥1.6 consulta las etiquetas del estimador antes de usarlo."""
        from sklearn.utils import Tags, TargetTags

        return Tags(
            estimator_type="regressor",
            target_tags=TargetTags(required=False),
            transformer_tags=None,
            regressor_tags=None,
            classifier_tags=None,
        )


def _guardar_artefacto(
    mejor: ResultadoModelo,
    objetivo: str,
    horizonte: int,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    features: list[str],
) -> Path:
    """Serializa el ganador junto con su banda de predicción empírica.

    La banda se calcula sobre los residuos del **conjunto de prueba**, no del de
    entrenamiento: los residuos de entrenamiento están sistemáticamente
    subestimados —el modelo ya vio esos datos— y producirían una banda
    demasiado estrecha, que es la peor clase de error en un intervalo de
    confianza porque transmite una seguridad que no existe.
    """
    import joblib

    assert mejor.modelo is not None and mejor.metricas is not None

    residuos = np.asarray(y_test, dtype=float) - mejor.modelo.predict(X_test)
    inferior, superior = np.quantile(residuos, CUANTILES_BANDA)

    artefacto = ArtefactoPronostico(
        modelo=mejor.modelo,
        objetivo=objetivo,
        horizonte=horizonte,
        unidad=unidad_de(objetivo),
        residuo_inferior=float(inferior),
        residuo_superior=float(superior),
        metricas=mejor.metricas.as_dict(),
        columnas=list(features),
    )

    ruta = ruta_artefacto(objetivo, horizonte)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Compresión ligera: un bosque aleatorio sin comprimir ronda los 200 MB y
    # está lleno de umbrales repetidos, así que baja mucho. El nivel 3 es el
    # punto donde deja de compensar: más nivel apenas reduce y multiplica el
    # tiempo de escritura.
    joblib.dump(artefacto, ruta, compress=3)
    log.info(
        "Artefacto guardado en %s (banda %.2f / +%.2f %s)",
        ruta.name,
        inferior,
        superior,
        artefacto.unidad,
    )
    return ruta


def _registrar_en_bd(
    db: Session,
    resultados: list[ResultadoModelo],
    mejor: ResultadoModelo,
    ruta: Path | None,
    objetivo: str,
    horizonte: int,
    n_train: int,
    n_test: int,
) -> None:
    """Guarda las métricas de todos los modelos para dejar trazabilidad.

    Todas las filas comparten un mismo `lote`: es lo que después permite a la
    comparación quedarse con un conjunto de modelos entrenados en las mismas
    condiciones en lugar de mezclar ejecuciones de fechas distintas.
    """
    lote = uuid4().hex

    for resultado in resultados:
        if not resultado.ok:
            continue
        assert resultado.metricas is not None and resultado.modelo is not None

        db.add(
            EjecucionEntrenamiento(
                nombre_modelo=resultado.nombre,
                lote=lote,
                objetivo=objetivo,
                horizonte_horas=horizonte,
                mae=resultado.metricas.mae,
                rmse=resultado.metricas.rmse,
                mape=resultado.metricas.mape,
                smape=_finito(resultado.metricas.smape),
                mase=_finito(resultado.metricas.mase),
                r2=_finito(resultado.metricas.r2),
                rmse_validacion=resultado.rmse_validacion,
                desviacion_validacion=resultado.desviacion_validacion,
                n_pliegues=resultado.n_pliegues or None,
                n_muestras_entrenamiento=n_train,
                n_muestras_prueba=n_test,
                hiperparametros=json.dumps(resultado.modelo.hiperparametros, default=str),
                importancia_variables=(
                    json.dumps(resultado.importancia) if resultado.importancia else None
                ),
                ruta_artefacto=str(ruta) if resultado is mejor else None,
                es_mejor=resultado is mejor,
                duracion_segundos=resultado.duracion_segundos,
            )
        )
    db.commit()
    log.info("Métricas registradas en la base de datos")


def _metricas_finitas(metricas: Metricas) -> bool:
    """¿Las tres métricas obligatorias son números utilizables?

    El MASE y el sMAPE pueden salir `NaN` legítimamente (serie sin variación
    estacional, valores en cero), así que no entran en la comprobación.
    """
    return all(np.isfinite(v) for v in (metricas.mae, metricas.rmse, metricas.mape))


def _finito(valor: float | None) -> float | None:
    """`NaN`/`inf` no caben en una columna `float` de PostgreSQL sin ensuciarla.

    Un `NaN` almacenado se propaga a cualquier media o comparación posterior y
    convierte en `NaN` la tabla comparativa entera. Se guarda `NULL`, que las
    agregaciones sí saben ignorar.
    """
    if valor is None or not np.isfinite(valor):
        return None
    return float(valor)
