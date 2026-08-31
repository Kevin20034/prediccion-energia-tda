"""Entrena y compara todos los modelos desde la línea de comandos.

Uso:
    python -m scripts.entrenar
    python -m scripts.entrenar --modelos regresion_lineal random_forest xgboost
    python -m scripts.entrenar --horizonte 24 --criterio rmse
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.api.routers.entrenar import _cargar_datos
from src.core.logging import get_logger
from src.database.session import SessionLocal
from src.models import MODELOS_DISPONIBLES
from src.models.entrenamiento import entrenar_todos

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modelos",
        nargs="+",
        choices=sorted(MODELOS_DISPONIBLES),
        help="Subconjunto a entrenar (por defecto, todos)",
    )
    parser.add_argument("--horizonte", type=int, default=24, help="Horas a futuro")
    parser.add_argument("--test", type=float, default=0.2, help="Proporción de prueba")
    parser.add_argument(
        "--criterio", choices=["rmse", "mae", "mape"], default="rmse", help="Métrica de selección"
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Entrena desde un CSV en vez de la base de datos (útil sin conexión)",
    )
    args = parser.parse_args()

    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=["fecha_hora"])
        log.info("Datos cargados desde %s (%d filas)", args.csv, len(df))
        db = None
        contexto = None
    else:
        contexto = SessionLocal()
        db = contexto
        df = _cargar_datos(db)
        log.info("Datos cargados desde la base de datos (%d filas)", len(df))

    try:
        if df.empty:
            print("[ERROR] No hay datos. Ejecuta primero: python -m scripts.ingestar_datos")
            raise SystemExit(1)

        resultado = entrenar_todos(
            df,
            db=db,
            modelos=args.modelos,
            horizonte=args.horizonte,
            proporcion_test=args.test,
            criterio=args.criterio,
        )
    finally:
        if contexto is not None:
            contexto.close()

    tabla = resultado.tabla_comparativa()

    print("\n" + "=" * 78)
    print(f"COMPARACIÓN DE MODELOS  —  horizonte {args.horizonte} h  —  "
          f"train={resultado.n_train:,}  test={resultado.n_test:,}")
    print("=" * 78)
    print(tabla.to_string(index=False))
    print("=" * 78)

    assert resultado.mejor is not None
    print(f"\nMejor modelo por {args.criterio.upper()}: {resultado.mejor.nombre}")
    print(f"  {resultado.mejor.metricas}")
    print(f"  Artefacto: {resultado.ruta_artefacto}")

    fallidos = [r for r in resultado.resultados if not r.ok]
    if fallidos:
        print("\nModelos que fallaron:")
        for r in fallidos:
            print(f"  - {r.nombre}: {r.error}")

    # Variables más influyentes del ganador: material directo para la tesis.
    if resultado.mejor.modelo is not None:
        importancias = resultado.mejor.modelo.importancia_features()
        if importancias is not None:
            print("\nTop 15 variables más influyentes:")
            for nombre, valor in importancias.head(15).items():
                print(f"  {nombre:<28} {valor:.4f}")


if __name__ == "__main__":
    main()
