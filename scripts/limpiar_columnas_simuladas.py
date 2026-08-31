"""Vacía las columnas que quedaron con valores SIMULADOS en la base de datos.

Contexto del problema
---------------------
La primera ingesta del proyecto usó el CSV de respaldo (datos sintéticos) porque
la API de XM no respondió. Ese CSV sí trae `generacion_hidraulica`,
`generacion_termica` y `disponibilidad_real`.

Cuando después se ingirieron los datos reales de XM, esas columnas **no se
sobrescribieron**: la API pública de XM no publica el desglose de generación por
tecnología, así que no viajan en el DataFrame entrante y el `ON CONFLICT DO
UPDATE` solo actualiza las columnas presentes.

Resultado: filas marcadas como `fuente='XM'` que mezclaban precio real con
generación inventada. Y como la imputación interpola en ambas direcciones, esos
valores sintéticos se propagaban además a los años vecinos.

Este script deja esas columnas en NULL. Con los arreglos de `limpieza.py` y
`features.py`, las variables derivadas de ellas simplemente no se construyen.

Uso:
    python -m scripts.limpiar_columnas_simuladas            # informa
    python -m scripts.limpiar_columnas_simuladas --aplicar  # ejecuta
"""

from __future__ import annotations

import argparse

from sqlalchemy import func, select, update

from src.database.models import DatoHistorico
from src.database.session import SessionLocal

#: Columnas que solo existen en el conjunto simulado.
COLUMNAS_SIMULADAS = (
    DatoHistorico.generacion_hidraulica,
    DatoHistorico.generacion_termica,
    DatoHistorico.disponibilidad_real,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aplicar", action="store_true", help="Ejecuta el borrado")
    args = parser.parse_args()

    with SessionLocal() as db:
        print("Filas con valor en columnas de origen simulado, por fuente:\n")
        for columna in COLUMNAS_SIMULADAS:
            filas = db.execute(
                select(DatoHistorico.fuente, func.count())
                .where(columna.isnot(None))
                .group_by(DatoHistorico.fuente)
            ).all()
            detalle = ", ".join(f"{f}={n:,}" for f, n in filas) or "ninguna"
            print(f"  {columna.key:<24} {detalle}")

        afectadas = db.execute(
            select(func.count(DatoHistorico.id)).where(
                DatoHistorico.fuente == "XM",
                DatoHistorico.generacion_hidraulica.isnot(None),
            )
        ).scalar_one()

        print(
            f"\n{afectadas:,} filas marcadas como 'XM' llevan generación SIMULADA."
            "\nEs contaminación: precio real mezclado con generación inventada."
        )

        if not args.aplicar:
            print("\nModo informe. Añade --aplicar para vaciar esas columnas.")
            return

        db.execute(
            update(DatoHistorico).values(
                generacion_hidraulica=None,
                generacion_termica=None,
                disponibilidad_real=None,
            )
        )
        db.commit()
        print("\n[OK] Columnas vaciadas. Reentrena para que el modelo deje de usarlas:")
        print("     python -m scripts.entrenar")


if __name__ == "__main__":
    main()
