"""Descarga datos de XM y clima, y los guarda en la base de datos.

Uso:
    python -m scripts.ingestar_datos --inicio 2023-01-01 --fin 2026-09-01
    python -m scripts.ingestar_datos --dias 730          # últimos 2 años
    python -m scripts.ingestar_datos --dias 30 --sin-tecnologias   # ingesta rápida

Rangos largos se trocean en bloques (``--bloque``, 90 días por defecto) y cada
bloque se guarda en cuanto se descarga. Así una descarga de tres años que se
corta a la mitad conserva todo lo que ya había traído, en vez de perderlo.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.core.logging import get_logger
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient
from src.database.persistencia import guardar_datos_historicos
from src.database.session import SessionLocal
from src.processing.limpieza import limpiar, unir_fuentes

log = get_logger(__name__)

DIAS_POR_BLOQUE = 90


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicio", type=str, help="Fecha inicial AAAA-MM-DD")
    parser.add_argument("--fin", type=str, help="Fecha final AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--dias", type=int, help="Alternativa: últimos N días")
    parser.add_argument(
        "--bloque", type=int, default=DIAS_POR_BLOQUE, help="Días por bloque de guardado"
    )
    parser.add_argument(
        "--sin-clima", action="store_true", help="Omite la descarga de variables climáticas"
    )
    parser.add_argument(
        "--sin-tecnologias",
        action="store_true",
        help="Omite el desglose de generación planta a planta (mucho más rápido)",
    )
    args = parser.parse_args()

    fecha_fin = date.fromisoformat(args.fin) if args.fin else date.today()
    if args.inicio:
        fecha_inicio = date.fromisoformat(args.inicio)
    elif args.dias:
        fecha_inicio = fecha_fin - timedelta(days=args.dias)
    else:
        fecha_inicio = fecha_fin - timedelta(days=730)

    cliente = XMClient(incluir_tecnologias=not args.sin_tecnologias)
    total_insertados = total_actualizados = total_filas = 0
    variables: set[str] = set()

    print(f"Ingesta de {fecha_inicio} a {fecha_fin} en bloques de {args.bloque} días\n")

    for bloque_inicio, bloque_fin in _bloques(fecha_inicio, fecha_fin, args.bloque):
        log.info("Bloque %s -> %s", bloque_inicio, bloque_fin)

        df_xm = cliente.obtener(bloque_inicio, bloque_fin)
        df_clima = None if args.sin_clima else ClimaClient().obtener(bloque_inicio, bloque_fin)
        df = limpiar(unir_fuentes(df_xm, df_clima))

        if df.empty:
            print(f"  {bloque_inicio} -> {bloque_fin}: sin datos")
            continue

        with SessionLocal() as db:
            insertados, actualizados = guardar_datos_historicos(db, df)

        total_filas += len(df)
        total_insertados += insertados
        total_actualizados += actualizados
        variables |= {c for c in df.columns if df[c].notna().any()}

        print(
            f"  {bloque_inicio} -> {bloque_fin}: {len(df):>5,} filas "
            f"({insertados:>5,} nuevas, {actualizados:>5,} actualizadas)"
        )

    if total_filas == 0:
        print("\n[ERROR] No se obtuvo ningún dato.")
        raise SystemExit(1)

    print(f"\n[OK] {total_filas:,} registros procesados")
    print(f"     Insertados:   {total_insertados:,}")
    print(f"     Actualizados: {total_actualizados:,}")
    print(f"     Variables:    {len(variables)}")


def _bloques(inicio: date, fin: date, dias: int) -> list[tuple[date, date]]:
    tramos: list[tuple[date, date]] = []
    actual = inicio
    while actual <= fin:
        tramo_fin = min(actual + timedelta(days=dias - 1), fin)
        tramos.append((actual, tramo_fin))
        actual = tramo_fin + timedelta(days=1)
    return tramos


if __name__ == "__main__":
    main()
