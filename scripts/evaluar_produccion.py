"""Compara las predicciones ya emitidas contra el precio que realmente ocurrió.

Esta es la evaluación **honesta** del modelo: no mide el error sobre un conjunto
de prueba apartado durante el entrenamiento, sino sobre predicciones que se
emitieron a ciegas y cuyo valor real se conoció después.

El error de producción casi siempre es peor que el del conjunto de prueba, y
esa diferencia es un resultado que merece discutirse en el trabajo de grado:
mide cuánto se degrada el modelo cuando sale del laboratorio.

Uso:
    python -m scripts.evaluar_produccion
    python -m scripts.evaluar_produccion --no-guardar   # solo informa
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from src.core.logging import get_logger
from src.database.models import DatoHistorico, Prediccion
from src.database.session import SessionLocal
from src.models.metricas import evaluar

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-guardar",
        action="store_true",
        help="No escribe `precio_real`; solo muestra el informe",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        predicciones = (
            db.execute(select(Prediccion).order_by(Prediccion.fecha_objetivo)).scalars().all()
        )

        if not predicciones:
            print("No hay predicciones registradas todavía.")
            return

        # Se indexa el histórico por marca de tiempo para cruzarlo en memoria.
        reales = {
            d.fecha_hora: d.precio_bolsa
            for d in db.execute(select(DatoHistorico)).scalars().all()
        }

        emparejadas = []
        for p in predicciones:
            real = reales.get(p.fecha_objetivo)
            if real is None:
                continue
            if not args.no_guardar:
                p.precio_real = real
            emparejadas.append((p, real))

        if not args.no_guardar:
            db.commit()

    if not emparejadas:
        print(
            f"Ninguna de las {len(predicciones)} predicciones tiene todavía su valor real.\n"
            "Vuelve a ejecutarlo cuando XM haya publicado esas fechas."
        )
        return

    y_pred = [p.precio_estimado for p, _ in emparejadas]
    y_real = [real for _, real in emparejadas]
    metricas = evaluar(y_real, y_pred)

    print("\n" + "=" * 70)
    print("ERROR EN PRODUCCIÓN — predicciones emitidas frente al valor real")
    print("=" * 70)
    print(f"  Predicciones emparejadas : {len(emparejadas)} de {len(predicciones)}")
    print(f"  Modelo                   : {emparejadas[0][0].nombre_modelo}")
    print(f"  Rango                    : {emparejadas[0][0].fecha_objetivo:%Y-%m-%d %H:%M} "
          f"-> {emparejadas[-1][0].fecha_objetivo:%Y-%m-%d %H:%M}")
    print("-" * 70)
    print(f"  {metricas}")
    print("=" * 70)

    print("\n  Detalle (primeras 12):")
    print(f"  {'fecha objetivo':<20} {'estimado':>10} {'real':>10} {'error':>10}")
    print("  " + "-" * 54)
    for p, real in emparejadas[:12]:
        error = p.precio_estimado - real
        print(
            f"  {p.fecha_objetivo:%Y-%m-%d %H:%M}     "
            f"{p.precio_estimado:>10.2f} {real:>10.2f} {error:>+10.2f}"
        )

    if not args.no_guardar:
        print(f"\n  `precio_real` actualizado en {len(emparejadas)} registros.")


if __name__ == "__main__":
    main()
