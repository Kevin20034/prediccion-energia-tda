"""Entrena y compara todos los modelos desde la línea de comandos.

Uso:
    python -m scripts.entrenar                       # precio, 24 h
    python -m scripts.entrenar --todos-los-horizontes
    python -m scripts.entrenar --objetivo demanda_real --horizonte 168
    python -m scripts.entrenar --modelos baseline_estacional xgboost lightgbm
    python -m scripts.entrenar --pliegues 3          # validación walk-forward

`--todos-los-horizontes` entrena la matriz completa que consume la interfaz:
cada objetivo pedido en cada uno de los tres horizontes (24 h, 7 d y 30 d). Es
lo que hay que ejecutar para que el frontend tenga las tres pestañas de
pronóstico operativas.
"""

from __future__ import annotations

import argparse

import pandas as pd

from src.api.routers.entrenar import _cargar_datos
from src.core.logging import get_logger
from src.database.session import SessionLocal
from src.models import MODELOS_DISPONIBLES
from src.models.entrenamiento import HORIZONTES, ResultadoEntrenamiento, entrenar_todos
from src.processing.features import OBJETIVOS

log = get_logger(__name__)

ANCHO = 96


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modelos",
        nargs="+",
        choices=sorted(MODELOS_DISPONIBLES),
        help="Subconjunto a entrenar (por defecto, todos)",
    )
    parser.add_argument(
        "--objetivo",
        nargs="+",
        choices=sorted(OBJETIVOS),
        default=["precio_bolsa"],
        help="Variables a pronosticar",
    )
    parser.add_argument("--horizonte", type=int, default=24, help="Horas a futuro")
    parser.add_argument(
        "--todos-los-horizontes",
        action="store_true",
        help=f"Entrena los tres horizontes de la interfaz: {', '.join(HORIZONTES)}",
    )
    parser.add_argument("--test", type=float, default=0.2, help="Proporción de prueba")
    parser.add_argument(
        "--criterio",
        choices=["rmse", "mae", "mape", "smape", "mase"],
        default="rmse",
        help="Métrica de selección",
    )
    parser.add_argument(
        "--pliegues",
        type=int,
        default=0,
        help="Pliegues de validación walk-forward (0 = desactivada)",
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Entrena desde un CSV en vez de la base de datos (útil sin conexión)",
    )
    args = parser.parse_args()

    horizontes = list(HORIZONTES.values()) if args.todos_los_horizontes else [args.horizonte]

    if args.csv:
        df = pd.read_csv(args.csv, parse_dates=["fecha_hora"])
        log.info("Datos cargados desde %s (%d filas)", args.csv, len(df))
        contexto = None
        db = None
    else:
        contexto = SessionLocal()
        db = contexto
        df = _cargar_datos(db)
        log.info("Datos cargados desde la base de datos (%d filas)", len(df))

    resultados: list[ResultadoEntrenamiento] = []
    try:
        if df.empty:
            print("[ERROR] No hay datos. Ejecuta primero: python -m scripts.ingestar_datos")
            raise SystemExit(1)

        for objetivo in args.objetivo:
            for horizonte in horizontes:
                print(f"\n>>> {objetivo} · horizonte {horizonte} h")
                resultados.append(
                    entrenar_todos(
                        df,
                        db=db,
                        modelos=args.modelos,
                        objetivo=objetivo,
                        horizonte=horizonte,
                        proporcion_test=args.test,
                        criterio=args.criterio,
                        pliegues_validacion=args.pliegues,
                    )
                )
    finally:
        if contexto is not None:
            contexto.close()

    for resultado in resultados:
        _informe(resultado, args.criterio)

    if len(resultados) > 1:
        _resumen_global(resultados, args.criterio)


def _informe(resultado: ResultadoEntrenamiento, criterio: str) -> None:
    tabla = resultado.tabla_comparativa()

    print("\n" + "=" * ANCHO)
    print(
        f"COMPARACIÓN — {resultado.objetivo} — horizonte {resultado.horizonte} h — "
        f"train={resultado.n_train:,}  test={resultado.n_test:,}"
    )
    print("=" * ANCHO)
    print(tabla.to_string(index=False))
    print("=" * ANCHO)

    assert resultado.mejor is not None
    print(f"\nMejor modelo por {criterio.upper()}: {resultado.mejor.nombre}")
    print(f"  {resultado.mejor.metricas}")
    print(f"  Artefacto: {resultado.ruta_artefacto}")

    # El MASE es la lectura que de verdad importa: por debajo de 1 el modelo
    # aporta sobre repetir el pasado; por encima, no.
    mase = resultado.mejor.metricas.mase if resultado.mejor.metricas else float("nan")
    if mase == mase:  # descarta NaN
        veredicto = (
            "supera al pronóstico ingenuo del mismo horizonte"
            if mase < 1
            else "NO supera al pronóstico ingenuo del mismo horizonte"
        )
        print(f"  MASE = {mase:.3f}: {veredicto}")

    fallidos = [r for r in resultado.resultados if not r.ok]
    if fallidos:
        print("\nModelos que fallaron:")
        for r in fallidos:
            print(f"  - {r.nombre}: {r.error}")

    if resultado.mejor.importancia:
        print("\nTop 15 variables (importancia por permutación):")
        for nombre, valor in list(resultado.mejor.importancia.items())[:15]:
            print(f"  {nombre:<34} {valor:>12.4f}")


def _resumen_global(resultados: list[ResultadoEntrenamiento], criterio: str) -> None:
    print("\n" + "=" * ANCHO)
    print("RESUMEN: MEJOR MODELO POR OBJETIVO Y HORIZONTE")
    print("=" * ANCHO)
    filas = [
        {
            "objetivo": r.objetivo,
            "horizonte": f"{r.horizonte} h",
            "mejor": r.mejor.nombre if r.mejor else "-",
            criterio.upper(): (
                round(getattr(r.mejor.metricas, criterio), 3) if r.mejor and r.mejor.metricas else None
            ),
            "MASE": round(r.mejor.metricas.mase, 3) if r.mejor and r.mejor.metricas else None,
        }
        for r in resultados
    ]
    print(pd.DataFrame(filas).to_string(index=False))
    print("=" * ANCHO)


if __name__ == "__main__":
    main()
