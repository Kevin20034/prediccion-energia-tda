"""Pruebas del módulo de procesamiento.

La prueba más importante del archivo es `test_no_hay_fuga_de_informacion`: es la
que verifica la validez metodológica del trabajo. Si los rezagos filtraran datos
del futuro, las métricas de todos los modelos serían falsas y las conclusiones
del trabajo de grado, inválidas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.processing.features import (
    columnas_features,
    construir_features,
    dividir_train_test,
)
from src.processing.limpieza import limpiar, unir_fuentes


class TestLimpieza:
    def test_elimina_duplicados_de_marca_temporal(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        assert not limpio["fecha_hora"].duplicated().any()

    def test_no_quedan_nulos_en_columnas_numericas(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        numericas = limpio.select_dtypes(include=[np.number])
        assert numericas.isna().sum().sum() == 0

    def test_recorta_atipicos_extremos(self, datos_crudos):
        limpio = limpiar(datos_crudos, tratar_atipicos=True)
        # El valor sembrado era 99 999; debe quedar recortado muy por debajo.
        assert limpio["precio_bolsa"].max() < 10_000

    def test_conserva_los_atipicos_si_se_desactiva(self, datos_crudos):
        limpio = limpiar(datos_crudos, tratar_atipicos=False)
        assert limpio["precio_bolsa"].max() > 10_000

    def test_serie_queda_ordenada_cronologicamente(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        assert limpio["fecha_hora"].is_monotonic_increasing

    def test_rejilla_horaria_sin_huecos(self, datos_crudos):
        limpio = limpiar(datos_crudos, rellenar_huecos=True)
        diferencias = limpio["fecha_hora"].diff().dropna().unique()
        assert list(diferencias) == [pd.Timedelta(hours=1)]

    def test_rellena_horas_faltantes(self, datos_crudos):
        con_huecos = datos_crudos.drop(index=range(200, 220))
        limpio = limpiar(con_huecos, rellenar_huecos=True)
        esperado = pd.date_range(
            limpio["fecha_hora"].min(), limpio["fecha_hora"].max(), freq="h"
        )
        assert len(limpio) == len(esperado)

    def test_dataframe_vacio_no_revienta(self):
        assert limpiar(pd.DataFrame()).empty

    def test_falta_columna_objetivo(self):
        df = pd.DataFrame({"fecha_hora": pd.date_range("2025-01-01", periods=5, freq="h")})
        with pytest.raises(ValueError, match="precio_bolsa"):
            limpiar(df)

    def test_unir_fuentes_conserva_todas_las_filas(self):
        base = pd.DataFrame(
            {
                "fecha_hora": pd.date_range("2025-01-01", periods=10, freq="h"),
                "precio_bolsa": range(10),
            }
        )
        clima = pd.DataFrame(
            {
                "fecha_hora": pd.date_range("2025-01-01", periods=5, freq="h"),
                "temperatura": range(5),
            }
        )
        unido = unir_fuentes(base, clima)
        # Outer join: no se pierden las 5 horas sin clima.
        assert len(unido) == 10
        assert unido["temperatura"].isna().sum() == 5


class TestFeatures:
    def test_genera_rezagos_y_calendario(self, datos_crudos):
        features = construir_features(limpiar(datos_crudos), horizonte=24)
        for esperada in ("precio_lag_24", "precio_lag_168", "hora_sin", "hora_cos"):
            assert esperada in features.columns

    def test_codificacion_ciclica_es_continua(self, datos_crudos):
        """La hora 23 y la hora 0 deben quedar contiguas en el círculo."""
        features = construir_features(limpiar(datos_crudos))
        h23 = features.loc[features["hora"] == 23, ["hora_sin", "hora_cos"]].iloc[0]
        h0 = features.loc[features["hora"] == 0, ["hora_sin", "hora_cos"]].iloc[0]
        distancia = np.hypot(h23["hora_sin"] - h0["hora_sin"], h23["hora_cos"] - h0["hora_cos"])
        assert distancia < 0.3

    def test_objetivo_es_el_precio_futuro(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        horizonte = 24
        features = construir_features(limpio, horizonte=horizonte, eliminar_nulos=False)

        fila = 300
        fecha_actual = features.loc[fila, "fecha_hora"]
        objetivo = features.loc[fila, "objetivo"]
        precio_futuro = limpio.loc[
            limpio["fecha_hora"] == fecha_actual + pd.Timedelta(hours=horizonte),
            "precio_bolsa",
        ].iloc[0]

        assert objetivo == pytest.approx(precio_futuro)

    def test_no_hay_fuga_de_informacion(self, datos_crudos):
        """`precio_lag_k` en el instante t debe ser el precio de t-k. Ni más ni menos."""
        limpio = limpiar(datos_crudos)
        features = construir_features(limpio, eliminar_nulos=False)

        fila = 400
        fecha = features.loc[fila, "fecha_hora"]

        for lag in (1, 24, 168):
            valor_lag = features.loc[fila, f"precio_lag_{lag}"]
            valor_real = limpio.loc[
                limpio["fecha_hora"] == fecha - pd.Timedelta(hours=lag), "precio_bolsa"
            ].iloc[0]
            assert valor_lag == pytest.approx(valor_real), f"fuga detectada en lag {lag}"

    def test_medias_moviles_no_incluyen_el_instante_actual(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        features = construir_features(limpio, eliminar_nulos=False)

        fila = 400
        media = features.loc[fila, "precio_media_24h"]
        ventana_correcta = limpio["precio_bolsa"].iloc[fila - 24 : fila].mean()
        assert media == pytest.approx(ventana_correcta, rel=1e-6)

    def test_columnas_features_excluye_objetivo_y_fecha(self, datos_crudos):
        features = construir_features(limpiar(datos_crudos))
        columnas = columnas_features(features)
        assert "objetivo" not in columnas
        assert "fecha_hora" not in columnas
        assert "precio_bolsa" not in columnas
        assert len(columnas) > 20

    def test_todas_las_features_son_numericas(self, datos_crudos):
        features = construir_features(limpiar(datos_crudos))
        subconjunto = features[columnas_features(features)]
        assert all(pd.api.types.is_numeric_dtype(subconjunto[c]) for c in subconjunto.columns)


class TestSplit:
    def test_es_cronologico_no_aleatorio(self, datos_crudos):
        features = construir_features(limpiar(datos_crudos))
        train, test = dividir_train_test(features, 0.2)
        # Ninguna fecha de entrenamiento puede ser posterior a las de prueba.
        assert train["fecha_hora"].max() < test["fecha_hora"].min()

    def test_respeta_la_proporcion(self, datos_crudos):
        features = construir_features(limpiar(datos_crudos))
        train, test = dividir_train_test(features, 0.25)
        assert len(test) / len(features) == pytest.approx(0.25, abs=0.01)
        assert len(train) + len(test) == len(features)

    @pytest.mark.parametrize("proporcion", [0, 1, -0.1, 1.5])
    def test_proporcion_invalida(self, datos_crudos, proporcion):
        features = construir_features(limpiar(datos_crudos))
        with pytest.raises(ValueError):
            dividir_train_test(features, proporcion)
