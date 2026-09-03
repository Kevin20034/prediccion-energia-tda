"""Pruebas del motor predictivo: métricas, contrato común y entrenamiento."""

from __future__ import annotations

import numpy as np
import pytest

from src.models import MODELOS_DISPONIBLES
from src.models.base import ModeloPredictivo
from src.models.metricas import (
    estacionalidad_para,
    evaluar,
    mae,
    mape,
    mase,
    rmse,
    smape,
)
from src.models.regresion_lineal import ModeloRegresionLineal
from src.processing.features import columnas_features, construir_features
from src.processing.limpieza import limpiar


class TestMetricas:
    def test_prediccion_perfecta_da_error_cero(self):
        y = np.array([100.0, 200.0, 300.0])
        m = evaluar(y, y)
        assert m.mae == 0 and m.rmse == 0 and m.mape == 0
        assert m.r2 == pytest.approx(1.0)

    def test_valores_conocidos(self):
        y_real = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 180.0])
        assert mae(y_real, y_pred) == pytest.approx(15.0)
        assert rmse(y_real, y_pred) == pytest.approx(np.sqrt((100 + 400) / 2))
        assert mape(y_real, y_pred) == pytest.approx(10.0)

    def test_rmse_penaliza_mas_que_mae(self):
        """Con un error concentrado en un punto, RMSE debe superar claramente a MAE."""
        y_real = np.zeros(10)
        y_pred = np.zeros(10)
        y_pred[0] = 100
        assert rmse(y_real, y_pred) > mae(y_real, y_pred) * 2

    def test_mape_ignora_reales_cercanos_a_cero(self):
        y_real = np.array([0.0, 100.0])
        y_pred = np.array([50.0, 110.0])
        # Solo cuenta el segundo par: 10 %.
        assert mape(y_real, y_pred) == pytest.approx(10.0)

    def test_dimensiones_incompatibles(self):
        with pytest.raises(ValueError, match="Dimensiones"):
            evaluar(np.array([1.0, 2.0]), np.array([1.0]))

    def test_sin_datos(self):
        with pytest.raises(ValueError, match="No hay datos"):
            evaluar(np.array([]), np.array([]))

    def test_smape_es_simetrico(self):
        """Sobreestimar y subestimar en la misma proporción debe pesar igual.

        Es justo la asimetría que tiene el MAPE clásico y que hace que, al
        comparar modelos, favorezca sistemáticamente a los que subestiman.
        """
        real = np.array([100.0])
        assert smape(real, np.array([150.0])) == pytest.approx(smape(np.array([150.0]), real))

    def test_mase_compara_contra_el_ingenuo(self):
        """MASE < 1 significa ganarle a repetir el ciclo anterior; > 1, perder.

        La serie lleva ruido a propósito: con un ciclo perfectamente periódico
        el pronóstico ingenuo no se equivocaría nunca, el denominador sería cero
        y el MASE quedaría indefinido (que es lo que la función devuelve, y por
        eso el caso degenerado se prueba aparte).
        """
        rng = np.random.default_rng(3)
        ciclo = (
            np.tile(np.sin(np.linspace(0, 2 * np.pi, 24)), 12) * 100
            + 300
            + rng.normal(0, 12, 24 * 12)
        )
        real = ciclo[-48:]

        assert mase(real, real + 0.5, ciclo, 24) < 1
        assert mase(real, real + 200, ciclo, 24) > 1

    def test_mase_indefinido_si_el_ingenuo_es_perfecto(self):
        """Serie exactamente periódica: el ingenuo no falla y no hay con qué escalar."""
        ciclo = np.tile(np.arange(24, dtype=float), 5)
        assert np.isnan(mase(ciclo[-24:], ciclo[-24:] + 1, ciclo, 24))

    @pytest.mark.parametrize(
        ("horizonte", "esperado"), [(1, 24), (24, 24), (168, 168), (720, 720), (36, 48)]
    )
    def test_estacionalidad_sigue_al_horizonte(self, horizonte, esperado):
        """El ingenuo de referencia debe estar al mismo horizonte que el modelo.

        Sin esto, el MASE de un pronóstico a 30 días se dividiría por el error
        de un ingenuo a 24 h —un problema mucho más fácil— y saldría inflado.
        """
        assert estacionalidad_para(horizonte) == esperado


@pytest.fixture
def conjunto(datos_crudos):
    """Datos listos para entrenar: features + objetivo."""
    features = construir_features(limpiar(datos_crudos), horizonte=24)
    columnas = columnas_features(features)
    return features[columnas], features["objetivo"]


class TestContratoComun:
    @pytest.mark.parametrize("nombre", sorted(MODELOS_DISPONIBLES))
    def test_todos_implementan_la_interfaz(self, nombre):
        clase = MODELOS_DISPONIBLES[nombre]
        assert issubclass(clase, ModeloPredictivo)
        assert clase.nombre == nombre

    def test_predecir_sin_entrenar_falla(self, conjunto):
        X, _ = conjunto
        with pytest.raises(RuntimeError, match="no está entrenado"):
            ModeloRegresionLineal().predict(X)

    def test_detecta_columnas_faltantes(self, conjunto):
        X, y = conjunto
        modelo = ModeloRegresionLineal().fit(X, y)
        with pytest.raises(ValueError, match="Faltan columnas"):
            modelo.predict(X.drop(columns=[X.columns[0]]))

    def test_es_invariante_al_orden_de_columnas(self, conjunto):
        """Reordenar las columnas no debe cambiar la predicción."""
        X, y = conjunto
        modelo = ModeloRegresionLineal().fit(X, y)
        original = modelo.predict(X)
        desordenado = modelo.predict(X[list(reversed(X.columns))])
        np.testing.assert_allclose(original, desordenado, rtol=1e-9)


class TestEntrenamiento:
    def test_regresion_lineal_entrena_y_predice(self, conjunto):
        X, y = conjunto
        modelo = ModeloRegresionLineal().fit(X, y)
        assert modelo.entrenado
        predicciones = modelo.predict(X)
        assert len(predicciones) == len(X)
        assert np.isfinite(predicciones).all()

    def test_supera_a_predecir_la_media(self, conjunto):
        """Prueba de cordura: el modelo debe batir al predictor trivial."""
        X, y = conjunto
        modelo = ModeloRegresionLineal().fit(X, y)
        error_modelo = modelo.evaluar(X, y).rmse
        error_trivial = float(np.sqrt(np.mean((y - y.mean()) ** 2)))
        assert error_modelo < error_trivial

    def test_expone_importancia_de_variables(self, conjunto):
        X, y = conjunto
        importancias = ModeloRegresionLineal().fit(X, y).importancia_features()
        assert importancias is not None
        assert len(importancias) == len(X.columns)
        assert importancias.is_monotonic_decreasing

    def test_serializacion_de_ida_y_vuelta(self, conjunto, tmp_path):
        X, y = conjunto
        modelo = ModeloRegresionLineal().fit(X, y)
        ruta = modelo.guardar(tmp_path / "modelo.joblib")

        recuperado = ModeloPredictivo.cargar(ruta)
        np.testing.assert_allclose(modelo.predict(X), recuperado.predict(X), rtol=1e-9)

    def test_cargar_artefacto_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            ModeloPredictivo.cargar(tmp_path / "no-existe.joblib")


class TestComparacion:
    def test_entrena_y_elige_ganador(self, datos_crudos):
        """Prueba de integración del orquestador (sin LSTM, que es lenta)."""
        from src.models.entrenamiento import entrenar_todos

        resultado = entrenar_todos(
            datos_crudos,
            modelos=["baseline_estacional", "regresion_lineal", "random_forest"],
            guardar_mejor=False,
        )

        assert len(resultado.resultados) == 3
        assert all(r.ok for r in resultado.resultados)
        assert resultado.mejor is not None

        tabla = resultado.tabla_comparativa()
        assert len(tabla) == 3
        assert tabla["mejor"].sum() == 1
        # La tabla viene ordenada por RMSE ascendente.
        assert tabla["RMSE"].is_monotonic_increasing

    def test_guarda_artefacto_con_objetivo_horizonte_y_banda(self, datos_crudos, tmp_path, monkeypatch):
        """El artefacto tiene que llevar consigo para qué se entrenó.

        Guardar solo el modelo permitiría aplicarlo por error a otro objetivo u
        otro horizonte y obtener números plausibles y equivocados, que es el
        fallo más caro que puede tener un sistema predictivo.
        """
        from src.models import entrenamiento

        monkeypatch.setattr(entrenamiento, "RUTA_ARTEFACTOS", tmp_path)

        resultado = entrenamiento.entrenar_todos(
            datos_crudos,
            modelos=["regresion_lineal"],
            horizonte=24,
            guardar_mejor=True,
        )

        assert resultado.ruta_artefacto is not None
        artefacto = entrenamiento.cargar_artefacto("precio_bolsa", 24)
        assert artefacto.objetivo == "precio_bolsa"
        assert artefacto.horizonte == 24
        assert artefacto.unidad == "COP/kWh"
        assert artefacto.residuo_inferior < artefacto.residuo_superior
        assert artefacto.columnas

    def test_entrena_tambien_la_demanda(self, datos_crudos):
        from src.models.entrenamiento import entrenar_todos

        resultado = entrenar_todos(
            datos_crudos,
            modelos=["baseline_estacional", "regresion_lineal"],
            objetivo="demanda_real",
            guardar_mejor=False,
        )
        assert resultado.objetivo == "demanda_real"
        assert resultado.mejor is not None

    def test_objetivo_desconocido(self, datos_crudos):
        from src.models.entrenamiento import entrenar_todos

        with pytest.raises(ValueError, match="desconocido"):
            entrenar_todos(datos_crudos, objetivo="temperatura")

    def test_modelo_desconocido(self, datos_crudos):
        from src.models.entrenamiento import entrenar_todos

        with pytest.raises(ValueError, match="Modelos desconocidos"):
            entrenar_todos(datos_crudos, modelos=["inexistente"])

    def test_criterio_invalido(self, datos_crudos):
        from src.models.entrenamiento import entrenar_todos

        with pytest.raises(ValueError, match="criterio"):
            entrenar_todos(datos_crudos, criterio="r2")
