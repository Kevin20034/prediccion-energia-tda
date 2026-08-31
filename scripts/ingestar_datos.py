"""Descarga datos de XM y clima, y los guarda en la base de datos.

Uso:
    python -m scripts.ingestar_datos --inicio 2024-01-01 --fin 2025-12-31
    python -m scripts.ingestar_datos --dias 730          # últimos 2 años
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.api.routers.datos import _guardar
from src.core.logging import get_logger
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient
from src.database.session import SessionLocal
from src.processing.limpieza import limpiar, unir_fuentes

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicio", type=str, help="Fecha inicial AAAA-MM-DD")
    parser.add_argument("--fin", type=str, help="Fecha final AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--dias", type=int, help="Alternativa: últimos N días")
    parser.add_argument(
        "--sin-clima", action="store_true", help="Omite la descarga de variables climáticas"
    )
    args = parser.parse_args()

    fecha_fin = date.fromisoformat(args.fin) if args.fin else date.today()
    if args.inicio:
        fecha_inicio = date.fromisoformat(args.inicio)
    elif args.dias:
        fecha_inicio = fecha_fin - timedelta(days=args.dias)
    else:
        fecha_inicio = fecha_fin - timedelta(days=730)

    log.info("Ingesta de %s a %s", fecha_inicio, fecha_fin)

    df_xm = XMClient().obtener(fecha_inicio, fecha_fin)
    df_clima = None if args.sin_clima else ClimaClient().obtener(fecha_inicio, fecha_fin)
    df = limpiar(unir_fuentes(df_xm, df_clima))

    if df.empty:
        print("[ERROR] No se obtuvo ningún dato.")
        raise SystemExit(1)

    with SessionLocal() as db:
        insertados, actualizados = _guardar(db, df)

    print(f"\n[OK] {len(df):,} registros procesados")
    print(f"     Insertados:   {insertados:,}")
    print(f"     Actualizados: {actualizados:,}")
    print(f"     Rango:        {df['fecha_hora'].min()} -> {df['fecha_hora'].max()}")
    print(f"     Fuente:       {df['fuente'].unique().tolist()}")


if __name__ == "__main__":
    main()
