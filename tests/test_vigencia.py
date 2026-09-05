"""Vigencia de un pronóstico guardado.

Un pronóstico deja de servir por dos motivos distintos, y confundirlos tiene
consecuencias visibles: el sistema llegó a mostrar durante horas el resultado de
un modelo que un reentrenamiento ya había sustituido, con el nombre del modelo
viejo al lado, porque sus fechas objetivo seguían estando en el futuro.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.api.routers.predicciones import esta_vigente
from src.database.models import Prediccion
from src.models.entrenamiento import ArtefactoPronostico


class ModeloFalso:
    nombre = "falso"


def artefacto(entrenado_en: datetime) -> ArtefactoPronostico:
    return ArtefactoPronostico(
        modelo=ModeloFalso(),
        objetivo="precio_bolsa",
        horizonte=24,
        unidad="COP/kWh",
        residuo_inferior=-10.0,
        residuo_superior=10.0,
        metricas={"rmse": 100.0},
        columnas=["a"],
        entrenado_en=entrenado_en,
    )


def prediccion(fecha_objetivo: datetime, generado_en: datetime) -> Prediccion:
    return Prediccion(
        fecha_objetivo=fecha_objetivo,
        objetivo="precio_bolsa",
        horizonte_horas=24,
        unidad="COP/kWh",
        valor_estimado=1000.0,
        nombre_modelo="falso",
        generado_en=generado_en,
    )


AHORA = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class TestVigencia:
    def test_vigente_si_mira_al_futuro_y_es_del_modelo_actual(self):
        p = prediccion(AHORA + timedelta(hours=5), AHORA)
        assert esta_vigente(p, artefacto(AHORA - timedelta(days=1)), AHORA)

    def test_caducado_si_los_datos_ya_lo_alcanzaron(self):
        """Ya se sabe qué pasó en esa hora: eso es historial, no pronóstico."""
        p = prediccion(AHORA - timedelta(hours=1), AHORA - timedelta(days=1))
        assert not esta_vigente(p, artefacto(AHORA - timedelta(days=2)), AHORA)

    def test_caducado_si_el_modelo_se_reentreno_despues(self):
        """El caso que se escapaba: fecha futura, pero modelo ya sustituido."""
        p = prediccion(AHORA + timedelta(hours=5), AHORA - timedelta(hours=3))
        reentrenado = artefacto(AHORA - timedelta(hours=1))
        assert not esta_vigente(p, reentrenado, AHORA)

    def test_vigente_si_se_emitio_justo_tras_entrenar(self):
        entrenado = AHORA - timedelta(hours=2)
        p = prediccion(AHORA + timedelta(hours=5), entrenado)
        assert esta_vigente(p, artefacto(entrenado), AHORA)

    def test_tolera_marcas_de_tiempo_sin_zona(self):
        """La base devuelve con zona y el artefacto la crea en UTC.

        Si alguna llegara ingenua, compararlas lanzaría `TypeError` en mitad de
        una petición en lugar de decidir sobre la vigencia.
        """
        p = prediccion(AHORA + timedelta(hours=5), AHORA.replace(tzinfo=None))
        assert esta_vigente(p, artefacto(AHORA - timedelta(days=1)), AHORA)

    def test_sin_fecha_de_emision_no_se_da_por_bueno(self):
        p = prediccion(AHORA + timedelta(hours=5), None)
        assert not esta_vigente(p, artefacto(AHORA - timedelta(days=1)), AHORA)

    @pytest.mark.parametrize("ultimo_dato", [None])
    def test_sin_historico_solo_decide_el_modelo(self, ultimo_dato):
        p = prediccion(AHORA + timedelta(hours=5), AHORA)
        assert esta_vigente(p, artefacto(AHORA - timedelta(days=1)), ultimo_dato)
