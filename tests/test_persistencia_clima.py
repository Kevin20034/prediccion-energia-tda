"""Escritura del clima por departamento.

Es idempotente como el resto de la ingesta, y por el mismo motivo: reejecutar un
rango ya descargado es lo normal —una ingesta que se cortó, o el planificador
repitiendo su ventana— y tiene que actualizar, no duplicar ni reventar.
"""

from __future__ import annotations

import pandas as pd

from src.database.models import ClimaDepartamento
from src.database.persistencia import guardar_clima_departamento


def _muestra(temperatura: float = 22.5) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "fecha_hora": pd.Timestamp("2026-01-15 12:00", tz="UTC"),
                "codigo_dane": "05",
                "departamento": "Antioquia",
                "temperatura": temperatura,
                "precipitacion": 0.0,
                "humedad_relativa": 70.0,
            }
        ]
    )


def test_guardar_inserta(db):
    assert guardar_clima_departamento(db, _muestra()) == (1, 0)


def test_reejecutar_actualiza_en_vez_de_duplicar(db):
    """Open-Meteo también corrige el reanálisis de los días recientes."""
    guardar_clima_departamento(db, _muestra(22.5))

    insertados, actualizados = guardar_clima_departamento(db, _muestra(23.9))

    assert (insertados, actualizados) == (0, 1)
    assert db.query(ClimaDepartamento).count() == 1
    assert db.query(ClimaDepartamento).one().temperatura == 23.9


def test_vacio_no_escribe_nada(db):
    assert guardar_clima_departamento(db, pd.DataFrame()) == (0, 0)


def test_dos_departamentos_en_la_misma_hora_conviven(db):
    """La clave es (hora, departamento): la misma hora existe 33 veces."""
    dos = pd.concat(
        [_muestra(), _muestra().assign(codigo_dane="08", departamento="Atlántico")],
        ignore_index=True,
    )

    assert guardar_clima_departamento(db, dos) == (2, 0)
