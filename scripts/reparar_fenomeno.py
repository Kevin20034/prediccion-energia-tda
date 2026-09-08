"""Recalcula `fenomeno_climatico` a partir del `indice_oni` ya guardado.

Por qué hizo falta
------------------

El fenómeno es una función del ONI, pero se clasificaba **al descargar el clima**,
antes de que la limpieza tocara nada. Cuando el ONI se rellenaba o NOAA lo
corregía después —y lo corrige, porque es una media móvil de tres meses que se
revisa al publicarse cada mes nuevo—, el número cambiaba y la etiqueta se quedaba
con el valor viejo.

El resultado en la base era horas marcadas ``NEUTRO`` con un ONI de 1,39, que es
El Niño de manual. No era cosmético: la sección del fenómeno agrupa por esta
columna, así que esas horas entraban en la media equivocada y contaminaban
justamente la comparación entre fases que la sección existe para mostrar.

`limpieza.limpiar` ya recalcula la etiqueta al final de cada ingesta, así que esto
no volverá a pasar. Este script arregla lo que quedó escrito antes.

Uso:
    python -m scripts.reparar_fenomeno
    python -m scripts.reparar_fenomeno --simular
"""

from __future__ import annotations

import argparse

from sqlalchemy import select, update

from src.core.logging import get_logger
from src.data_collection.clima_client import clasificar_fenomeno
from src.database.models import DatoHistorico
from src.database.session import SessionLocal

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--simular", action="store_true", help="Solo informa; no escribe nada"
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        filas = db.execute(
            select(DatoHistorico.id, DatoHistorico.indice_oni, DatoHistorico.fenomeno_climatico)
        ).all()

        incoherentes = [
            (id_, oni, guardado, clasificar_fenomeno(oni))
            for id_, oni, guardado in filas
            if clasificar_fenomeno(oni) != guardado
        ]

        print(f"Filas revisadas:    {len(filas):,}")
        print(f"Filas incoherentes: {len(incoherentes):,}")

        if not incoherentes:
            print("\n[OK] La etiqueta ya coincide con el índice en todas las filas.")
            return

        resumen: dict[tuple[str, str], int] = {}
        for _, _, guardado, correcto in incoherentes:
            resumen[(guardado, correcto)] = resumen.get((guardado, correcto), 0) + 1

        print("\nCambios por corregir:")
        for (guardado, correcto), n in sorted(resumen.items(), key=lambda x: -x[1]):
            print(f"  {guardado:<9} -> {correcto:<9} {n:>7,} filas")

        if args.simular:
            print("\n[SIMULACIÓN] No se escribió nada.")
            return

        # Se agrupa por valor destino para no lanzar una sentencia por fila.
        for correcto in {c for *_, c in incoherentes}:
            ids = [id_ for id_, _, _, c in incoherentes if c == correcto]
            for i in range(0, len(ids), 1000):
                db.execute(
                    update(DatoHistorico)
                    .where(DatoHistorico.id.in_(ids[i : i + 1000]))
                    .values(fenomeno_climatico=correcto)
                )
        db.commit()

        print(f"\n[OK] {len(incoherentes):,} filas corregidas.")


if __name__ == "__main__":
    main()
