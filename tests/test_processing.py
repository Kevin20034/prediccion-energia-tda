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
        for esperada in (
            "objetivo_lag_24",
            "objetivo_lag_168",
            "hora_sin",
            "hora_cos",
            "es_festivo",
            "es_dia_laboral",
        ):
            assert esperada in features.columns

    def test_marca_los_festivos_colombianos(self, datos_crudos):
        """El 1 de enero es festivo y el 2 de enero de 2025 no lo es.

        Importa porque un festivo tiene el perfil de demanda de un domingo. Se
        comprueba también un día laborable contiguo para que la prueba falle si
        alguien marcara todo el calendario como festivo.
        """
        features = construir_features(limpiar(datos_crudos), eliminar_nulos=False)
        por_dia = features.set_index("fecha_hora")["es_festivo"]

        assert por_dia["2025-01-01 10:00"] == 1
        assert por_dia["2025-01-02 10:00"] == 0
        # 6 de enero: Reyes, trasladado al lunes por la ley Emiliani. En 2025 el
        # 6 cae en lunes, así que ese mismo día es festivo.
        assert por_dia["2025-01-06 10:00"] == 1

    def test_objetivo_demanda_excluye_las_columnas_que_la_filtran(self, datos_crudos):
        """Al predecir demanda, la demanda comercial no puede entrar como predictora.

        Es prácticamente la misma serie: si se colara, el modelo tendría un R²
        casi perfecto y ningún valor.
        """
        limpio = limpiar(datos_crudos, objetivo="demanda_real")
        features = construir_features(limpio, objetivo="demanda_real", eliminar_nulos=False)
        columnas = columnas_features(features, "demanda_real")

        assert "demanda_real" not in columnas
        for filtrada in ("demanda_comercial", "generacion_total", "perdidas_energia"):
            assert filtrada not in columnas

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

    def test_anula_la_demanda_publicada_a_medias(self, datos_crudos):
        """XM publica la demanda parcial de los últimos días sin marcarla.

        Es el caso peligroso: no es un nulo, es una cifra plausible pero
        equivocada —un tercio de la real— que pasa todos los filtros y llega al
        pronóstico como punto de partida del sistema.
        """
        crudo = datos_crudos.copy()
        # La cola se elige por fecha y no por posición: el conjunto de prueba
        # incluye a propósito una fila duplicada a mitad de serie, y las últimas
        # posiciones no son las últimas horas.
        corte = crudo["fecha_hora"].max() - pd.Timedelta(hours=30)
        cola = crudo["fecha_hora"] > corte
        # La generación se mantiene; solo la demanda llega incompleta.
        crudo.loc[cola, "demanda_real"] = crudo.loc[cola, "generacion_total"] * 0.3

        limpio = limpiar(crudo, imputar=False)
        afectadas = limpio["fecha_hora"] > corte

        assert limpio.loc[afectadas, "demanda_real"].isna().all()
        # Las horas anteriores quedan intactas. No se exige que estén todas
        # llenas: el conjunto de prueba trae una hora ausente a propósito, y sin
        # imputación esa sigue vacía por otro motivo.
        anteriores = limpio.loc[~afectadas, "demanda_real"]
        assert anteriores.notna().mean() > 0.99

    def test_el_relleno_de_bordes_usa_el_dia_anterior(self, datos_crudos):
        """Un hueco al final se completa con la misma hora del día anterior.

        Propagar hacia adelante el último valor conocido dejaría una recta plana
        en el tramo que alimenta el pronóstico, borrando el ciclo diario justo
        donde más importa.
        """
        crudo = datos_crudos.copy().sort_values("fecha_hora").reset_index(drop=True)
        hueco = crudo.index[-10:]
        crudo.loc[hueco, "temperatura"] = np.nan

        limpio = limpiar(crudo)
        serie = limpio.set_index("fecha_hora")["temperatura"]

        for instante in limpio["fecha_hora"].iloc[-10:]:
            esperado = serie.get(instante - pd.Timedelta(hours=24))
            assert serie[instante] == pytest.approx(esperado)

    def test_sin_imputar_conserva_los_nulos(self, datos_crudos):
        crudo = datos_crudos.copy()
        crudo.loc[crudo.index[-5:], "temperatura"] = np.nan

        assert limpiar(crudo, imputar=False)["temperatura"].isna().any()
        assert limpiar(crudo, imputar=True)["temperatura"].notna().all()

    def test_no_hay_fuga_de_informacion(self, datos_crudos):
        """`objetivo_lag_k` en el instante t debe ser el valor de t-k. Ni más ni menos."""
        limpio = limpiar(datos_crudos)
        features = construir_features(limpio, eliminar_nulos=False)

        fila = 400
        fecha = features.loc[fila, "fecha_hora"]

        for lag in (1, 24, 168):
            valor_lag = features.loc[fila, f"objetivo_lag_{lag}"]
            valor_real = limpio.loc[
                limpio["fecha_hora"] == fecha - pd.Timedelta(hours=lag), "precio_bolsa"
            ].iloc[0]
            assert valor_lag == pytest.approx(valor_real), f"fuga detectada en lag {lag}"

    def test_medias_moviles_no_incluyen_el_instante_actual(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        features = construir_features(limpio, eliminar_nulos=False)

        fila = 400
        media = features.loc[fila, "objetivo_media_24h"]
        ventana_correcta = limpio["precio_bolsa"].iloc[fila - 24 : fila].mean()
        assert media == pytest.approx(ventana_correcta, rel=1e-6)

    def test_media_misma_hora_promedia_los_siete_dias_anteriores(self, datos_crudos):
        limpio = limpiar(datos_crudos)
        features = construir_features(limpio, eliminar_nulos=False)

        fila = 400
        esperado = sum(limpio["precio_bolsa"].iloc[fila - 24 * k] for k in range(1, 8)) / 7
        assert features.loc[fila, "objetivo_media_misma_hora_7d"] == pytest.approx(esperado)

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
