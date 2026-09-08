"""Clima por departamento y anomalía de temperatura.

La anomalía es el número que colorea el mapa del fenómeno del Niño, y tiene dos
formas fáciles de estar mal:

1. Comparar contra la media de todo el año en vez de contra la del mismo mes.
   Entonces cualquier enero sale "frío" y cualquier julio "cálido", y el mapa
   muestra el calendario en lugar del fenómeno.
2. Comparar todos los departamentos contra una media común. 26 °C es normal en
   Barranquilla y altísimo en Bogotá; una media nacional pinta la costa en rojo
   permanente y no dice nada.

Ambas se prueban explícitamente porque el mapa resultante parecería razonable en
los dos casos: colores plausibles, conclusiones falsas.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.data_collection.clima_departamentos import anomalia_mensual


def _fila(fecha: str, codigo: str, temperatura: float) -> dict:
    return {
        "fecha_hora": pd.Timestamp(fecha, tz="UTC"),
        "codigo_dane": codigo,
        "temperatura": temperatura,
    }


class TestAnomalia:
    def test_compara_contra_el_mismo_mes_del_ano(self):
        """Un enero caliente se mide contra los eneros, no contra la media anual.

        La normal es la media del propio periodo, así que la observación evaluada
        entra en ella: cuatro eneros de 20, 20, 20 y 22 dan una normal de 20,5 y
        una anomalía de +1,5. Con datos reales eso es irrelevante —cada hora pesa
        una entre más de dos mil de su mes-departamento— pero aquí hay cuatro
        puntos y se nota.

        Lo que la prueba fija es el criterio, no el decimal: contra la media
        anual (22,86) esta misma hora daría −0,86. Signo contrario, conclusión
        contraria.
        """
        filas = []
        for anio in (2023, 2024, 2025):
            filas.append(_fila(f"{anio}-01-15 12:00", "05", 20.0))
            filas.append(_fila(f"{anio}-07-15 12:00", "05", 26.0))
        filas.append(_fila("2026-01-15 12:00", "05", 22.0))

        r = anomalia_mensual(pd.DataFrame(filas))
        ultimo = r[r["fecha_hora"] == pd.Timestamp("2026-01-15 12:00", tz="UTC")].iloc[0]

        assert ultimo["anomalia"] == pytest.approx(1.5)
        assert ultimo["anomalia"] > 0, "un enero por encima de los eneros no puede salir frío"

    def test_cada_departamento_contra_su_propia_normal(self):
        """26 °C es normal en Barranquilla y altísimo en Bogotá."""
        filas = [
            _fila("2025-01-15 12:00", "08", 28.0),
            _fila("2026-01-15 12:00", "08", 28.0),
            _fila("2025-01-15 12:00", "11", 14.0),
            _fila("2026-01-15 12:00", "11", 16.0),
        ]
        r = anomalia_mensual(pd.DataFrame(filas))

        caribe = r[(r["codigo_dane"] == "08") & (r["fecha_hora"].dt.year == 2026)].iloc[0]
        andes = r[(r["codigo_dane"] == "11") & (r["fecha_hora"].dt.year == 2026)].iloc[0]

        assert caribe["anomalia"] == pytest.approx(0.0)
        assert andes["anomalia"] == pytest.approx(1.0)

    def test_conserva_las_columnas_de_origen(self):
        """La anomalía se añade; no sustituye a la temperatura medida."""
        r = anomalia_mensual(pd.DataFrame([_fila("2025-01-15 12:00", "05", 21.0)]))

        assert {"fecha_hora", "codigo_dane", "temperatura", "media_mensual", "anomalia"} <= set(
            r.columns
        )
        assert r.iloc[0]["temperatura"] == 21.0

    def test_dataframe_vacio_no_revienta(self):
        """Un departamento sin clima descargado no puede tumbar el mapa entero."""
        assert anomalia_mensual(pd.DataFrame()).empty
