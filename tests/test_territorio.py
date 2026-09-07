"""Pruebas del módulo territorial: reparto por departamento y aplanado de XM.

La prueba central es `test_el_reparto_conserva_la_energia`. El mapa reparte la
demanda de 29 mercados de comercialización sobre 28 departamentos, y ese reparto
solo es defendible si redistribuye sin crear ni destruir energía. Un error de
pesos ahí no se vería en el mapa —los colores seguirían pareciendo razonables—
pero invalidaría cualquier cifra territorial del trabajo de grado.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from src.data_collection import xm_api
from src.data_collection.departamentos import (
    DEPARTAMENTOS,
    POR_CODIGO,
    departamentos_de,
    es_estimado,
    validar_reparto,
)
from src.data_collection.xm_departamentos import repartir, verificar_conservacion


class TestCatalogo:
    def test_la_tabla_de_reparto_es_coherente(self):
        assert validar_reparto() == []

    def test_todos_los_departamentos_dane_estan(self):
        assert len(DEPARTAMENTOS) == 33
        # Códigos DANE de los cinco departamentos que no están en el SIN.
        zni = {d.codigo for d in DEPARTAMENTOS if not d.interconectado}
        assert zni == {"88", "91", "94", "97", "99"}


class TestVigencias:
    """XM reorganiza mercados, y el histórico no puede reescribirse por ello.

    El 1 de septiembre de 2026 XM sacó CESAR como mercado propio: Caribe Mar cayó
    unos 4,5 GWh/día y Cesar subió 4,2, con la suma intacta. Aplicar los pesos
    nuevos a los tres años anteriores dejaría a Cesar casi en cero en todo el
    histórico; seguir con los viejos le atribuiría el doble desde septiembre.
    """

    CORTE = date(2026, 9, 1)

    def test_cesar_es_mercado_propio(self):
        assert departamentos_de("CESAR", self.CORTE) == (("20", 1.0),)

    def test_antes_del_corte_caribe_mar_incluye_cesar(self):
        pesos = dict(departamentos_de("CARIBE MAR", self.CORTE - timedelta(days=1)))
        assert pesos["20"] == pytest.approx(0.21)

    def test_desde_el_corte_caribe_mar_ya_no_incluye_cesar(self):
        pesos = dict(departamentos_de("CARIBE MAR", self.CORTE))
        assert "20" not in pesos
        assert sum(pesos.values()) == pytest.approx(1.0)

    def test_sin_fecha_se_usa_el_reparto_base(self):
        """Compatibilidad: quien no pase fecha sigue obteniendo la tabla original."""
        pesos = dict(departamentos_de("CARIBE MAR"))
        assert pesos["20"] == pytest.approx(0.21)

    def test_el_reparto_conserva_la_energia_a_ambos_lados_del_corte(self):
        """La conservación no puede depender de en qué era caiga la hora."""
        for momento in (self.CORTE - timedelta(days=1), self.CORTE):
            crudo = pd.DataFrame(
                [
                    {"fecha_hora": pd.Timestamp(momento), "mercado": "CARIBE MAR", "demanda_kwh": 1_000.0},
                    {"fecha_hora": pd.Timestamp(momento), "mercado": "CESAR", "demanda_kwh": 250.0},
                ]
            )
            conserva, error = verificar_conservacion(crudo, repartir(crudo))
            assert conserva, f"{momento}: error relativo {error:.2e}"


class TestCoordenadas:
    """Sin coordenada no hay clima: Open-Meteo se consulta por latitud/longitud."""

    def test_todos_tienen_coordenada(self):
        for d in DEPARTAMENTOS:
            assert d.latitud, f"{d.nombre} sin latitud"
            assert d.longitud, f"{d.nombre} sin longitud"

    def test_las_coordenadas_caen_dentro_de_colombia(self):
        """Una latitud y una longitud intercambiadas al teclear caen fuera y se ven aquí.

        El rectángulo va de Leticia (−4,2 S) a San Andrés (12,6 N / 81,7 O), que
        son los extremos sur y noroeste del país.
        """
        for d in DEPARTAMENTOS:
            assert -4.3 <= d.latitud <= 13.5, f"{d.nombre}: latitud {d.latitud} fuera de Colombia"
            assert -82.0 <= d.longitud <= -66.8, (
                f"{d.nombre}: longitud {d.longitud} fuera de Colombia"
            )

    def test_no_hay_coordenadas_repetidas(self):
        """Dos departamentos con el mismo punto significan una fila copiada y no corregida."""
        puntos = [(d.latitud, d.longitud) for d in DEPARTAMENTOS]
        assert len(set(puntos)) == len(puntos)

    def test_los_mercados_multidepartamentales_se_marcan_estimados(self):
        assert es_estimado("CARIBE MAR")
        assert es_estimado("BOGOTA - CUNDINAMARCA")
        assert not es_estimado("ANTIOQUIA")

    def test_mercado_desconocido_no_revienta(self):
        assert departamentos_de("MERCADO QUE NO EXISTE") == ()


class TestReparto:
    @pytest.fixture
    def por_mercado(self) -> pd.DataFrame:
        horas = pd.date_range("2025-06-01", periods=3, freq="h")
        filas = []
        for hora in horas:
            for mercado, valor in (
                ("ANTIOQUIA", 1_000_000.0),
                ("CARIBE MAR", 800_000.0),
                ("BOGOTA - CUNDINAMARCA", 1_500_000.0),
            ):
                filas.append({"fecha_hora": hora, "mercado": mercado, "demanda_kwh": valor})
        return pd.DataFrame(filas)

    def test_el_reparto_conserva_la_energia(self, por_mercado):
        repartido = repartir(por_mercado)
        conserva, error = verificar_conservacion(por_mercado, repartido)
        assert conserva, f"el reparto perdió energía (error relativo {error})"

    def test_un_mercado_multiple_produce_varios_departamentos(self, por_mercado):
        repartido = repartir(por_mercado)
        una_hora = repartido[repartido["fecha_hora"] == por_mercado["fecha_hora"].min()]

        # Antioquia (1) + Caribe Mar (4) + Bogotá-Cundinamarca (2) = 7 departamentos.
        assert len(una_hora) == 7
        assert set(una_hora["codigo_dane"]) == {"05", "13", "23", "20", "70", "11", "25"}

    def test_marca_estimado_solo_donde_hubo_reparto(self, por_mercado):
        repartido = repartir(por_mercado)
        por_codigo = repartido.set_index("codigo_dane")["estimado"].groupby(level=0).first()

        assert not por_codigo["05"]  # Antioquia: atribución directa
        assert por_codigo["13"]  # Bolívar: viene de repartir Caribe Mar
        assert por_codigo["11"]  # Bogotá: viene de repartir con Cundinamarca

    def test_los_mercados_no_catalogados_se_descartan(self, por_mercado):
        con_intruso = pd.concat(
            [
                por_mercado,
                pd.DataFrame(
                    [
                        {
                            "fecha_hora": por_mercado["fecha_hora"].min(),
                            "mercado": "MERCADO INVENTADO",
                            "demanda_kwh": 999.0,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        repartido = repartir(con_intruso)
        # La conservación se mide solo sobre los mercados conocidos, así que
        # descartar uno desconocido no debe contarse como pérdida.
        conserva, _ = verificar_conservacion(con_intruso, repartido)
        assert conserva

    def test_nombres_de_departamento_resueltos(self, por_mercado):
        repartido = repartir(por_mercado)
        assert POR_CODIGO["05"].nombre == "Antioquia"
        assert "Antioquia" in set(repartido["departamento"])

    def test_dataframe_vacio(self):
        assert repartir(pd.DataFrame()).empty


class TestAplanado:
    def test_hora01_es_la_medianoche(self):
        """XM numera las horas 1..24; `Hour01` es el bloque que empieza a las 00:00."""
        payload = {
            "Items": [
                {
                    "Date": "2025-06-01",
                    "HourlyEntities": [
                        {"Values": {"code": "Sistema", "Hour01": "10", "Hour24": "20"}}
                    ],
                }
            ]
        }
        df = xm_api.aplanar_horaria(payload, "valor")

        assert len(df) == 2
        assert df.iloc[0]["fecha_hora"] == pd.Timestamp("2025-06-01 00:00")
        assert df.iloc[1]["fecha_hora"] == pd.Timestamp("2025-06-01 23:00")

    def test_conserva_la_entidad_cuando_se_pide(self):
        payload = {
            "Items": [
                {
                    "Date": "2025-06-01",
                    "HourlyEntities": [
                        {"Values": {"code": "ANTIOQUIA", "Hour01": "10"}},
                        {"Values": {"code": "BOYACA", "Hour01": "5"}},
                    ],
                }
            ]
        }
        df = xm_api.aplanar_horaria(payload, "valor", por_entidad=True)
        assert set(df["entidad"]) == {"ANTIOQUIA", "BOYACA"}

    def test_ignora_las_claves_que_no_son_horas(self):
        payload = {
            "Items": [
                {
                    "Date": "2025-06-01",
                    "HourlyEntities": [{"Values": {"code": "Sistema", "Hour01": "10"}}],
                }
            ]
        }
        # `code` no debe convertirse en una hora número cero.
        assert len(xm_api.aplanar_horaria(payload, "valor")) == 1

    def test_valores_vacios_quedan_nulos(self):
        payload = {
            "Items": [
                {
                    "Date": "2025-06-01",
                    "HourlyEntities": [{"Values": {"code": "Sistema", "Hour01": ""}}],
                }
            ]
        }
        df = xm_api.aplanar_horaria(payload, "valor")
        assert df["valor"].isna().all()

    def test_partir_rango_respeta_el_limite(self):
        import datetime as dt

        tramos = xm_api.partir_rango(dt.date(2025, 1, 1), dt.date(2025, 3, 15), 31)
        assert tramos[0] == (dt.date(2025, 1, 1), dt.date(2025, 1, 31))
        assert tramos[-1][1] == dt.date(2025, 3, 15)
        # Sin solapes ni huecos entre tramos consecutivos.
        for anterior, siguiente in zip(tramos, tramos[1:], strict=False):
            assert siguiente[0] == anterior[1] + dt.timedelta(days=1)
