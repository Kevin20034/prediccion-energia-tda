"""Compara las predicciones ya emitidas contra el valor que realmente ocurrió.

Esta es la evaluación **honesta** del modelo: no mide el error sobre un conjunto
de prueba apartado durante el entrenamiento, sino sobre predicciones que se
emitieron a ciegas y cuyo valor real se conoció después.

El error de producción casi siempre es peor que el del conjunto de prueba, y
esa diferencia es un resultado que merece discutirse en el trabajo de grado:
mide cuánto se degrada el modelo cuando sale del laboratorio.

Además informa de la **cobertura de la banda de predicción**: qué porcentaje de
los valores reales cayó dentro del intervalo que el modelo declaró. Como la
banda se calibra al 80 %, una cobertura muy por debajo significa que el modelo
transmite más seguridad de la que tiene, y muy por encima que la banda es tan
ancha que no informa.

Uso:
    python -m scripts.evaluar_produccion
    python -m scripts.evaluar_produccion --objetivo demanda_real
    python -m scripts.evaluar_produccion --no-guardar   # solo informa
"""

from __future__ import annotations

import argparse
from collections import defaultdict

from sqlalchemy import select

from src.core.logging import get_logger
from src.database.models import DatoHistorico, Prediccion
from src.database.session import SessionLocal
from src.models.entrenamiento import CUANTILES_BANDA
from src.models.metricas import evaluar
from src.processing.features import OBJETIVOS

log = get_logger(__name__)

COBERTURA_OBJETIVO = (CUANTILES_BANDA[1] - CUANTILES_BANDA[0]) * 100


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--objetivo",
        choices=sorted(OBJETIVOS),
        help="Evalúa solo un objetivo (por defecto, todos)",
    )
    parser.add_argument(
        "--no-guardar",
        action="store_true",
        help="No escribe `valor_real`; solo muestra el informe",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        consulta = select(Prediccion).order_by(Prediccion.fecha_objetivo)
        if args.objetivo:
            consulta = consulta.where(Prediccion.objetivo == args.objetivo)
        predicciones = db.execute(consulta).scalars().all()

        if not predicciones:
            print("No hay predicciones registradas todavía.")
            return

        # Se indexa el histórico por marca de tiempo para cruzarlo en memoria.
        historico = {
            d.fecha_hora: {"precio_bolsa": d.precio_bolsa, "demanda_real": d.demanda_real}
            for d in db.execute(select(DatoHistorico)).scalars().all()
        }

        emparejadas: list[tuple[Prediccion, float]] = []
        for p in predicciones:
            fila = historico.get(p.fecha_objetivo)
            real = fila.get(p.objetivo) if fila else None
            if real is None:
                continue
            if not args.no_guardar:
                p.valor_real = real
            emparejadas.append((p, float(real)))

        if not args.no_guardar:
            db.commit()

    if not emparejadas:
        print(
            f"Ninguna de las {len(predicciones)} predicciones tiene todavía su valor real.\n"
            "Vuelve a ejecutarlo cuando XM haya publicado esas fechas."
        )
        return

    # Un informe por combinación objetivo/horizonte: mezclar el error a 24 h con
    # el de 720 h daría una cifra que no describe a ninguno de los dos.
    grupos: dict[tuple[str, int], list[tuple[Prediccion, float]]] = defaultdict(list)
    for p, real in emparejadas:
        grupos[(p.objetivo, p.horizonte_horas)].append((p, real))

    for (objetivo, horizonte), pares in sorted(grupos.items()):
        _informe(objetivo, horizonte, pares)

    if not args.no_guardar:
        print(f"\n`valor_real` actualizado en {len(emparejadas)} registros.")


def _informe(objetivo: str, horizonte: int, pares: list[tuple[Prediccion, float]]) -> None:
    y_pred = [p.valor_estimado for p, _ in pares]
    y_real = [real for _, real in pares]
    metricas = evaluar(y_real, y_pred)
    unidad = pares[0][0].unidad

    print("\n" + "=" * 76)
    print(f"ERROR EN PRODUCCIÓN — {objetivo} a {horizonte} h")
    print("=" * 76)
    print(f"  Predicciones emparejadas : {len(pares)}")
    print(f"  Modelo                   : {pares[0][0].nombre_modelo}")
    print(
        f"  Rango                    : {pares[0][0].fecha_objetivo:%Y-%m-%d %H:%M} "
        f"-> {pares[-1][0].fecha_objetivo:%Y-%m-%d %H:%M}"
    )
    print("-" * 76)
    print(f"  {metricas}   [{unidad}]")

    cobertura = _cobertura(pares)
    if cobertura is not None:
        print(
            f"  Cobertura de la banda    : {cobertura:.1f} % "
            f"(calibrada al {COBERTURA_OBJETIVO:.0f} %)"
        )
    print("=" * 76)

    print("\n  Detalle (primeras 12):")
    print(f"  {'fecha objetivo':<20} {'estimado':>12} {'real':>12} {'error':>12}")
    print("  " + "-" * 60)
    for p, real in pares[:12]:
        print(
            f"  {p.fecha_objetivo:%Y-%m-%d %H:%M}     "
            f"{p.valor_estimado:>12.2f} {real:>12.2f} {p.valor_estimado - real:>+12.2f}"
        )


def _cobertura(pares: list[tuple[Prediccion, float]]) -> float | None:
    """Porcentaje de valores reales que cayeron dentro de la banda declarada."""
    con_banda = [
        (p, real)
        for p, real in pares
        if p.limite_inferior is not None and p.limite_superior is not None
    ]
    if not con_banda:
        return None

    dentro = sum(1 for p, real in con_banda if p.limite_inferior <= real <= p.limite_superior)
    return dentro / len(con_banda) * 100


if __name__ == "__main__":
    main()
