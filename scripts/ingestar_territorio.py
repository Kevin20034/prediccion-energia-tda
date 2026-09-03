"""Ingesta territorial: demanda por departamento y escenarios de la UPME.

Uso:
    python -m scripts.ingestar_territorio --inicio 2024-01-01
    python -m scripts.ingestar_territorio --dias 365 --sin-upme

La demanda por departamento sale de repartir ``DemaCome`` por mercado de
comercialización según la tabla documentada en `data_collection.departamentos`.
Al terminar se comprueba que el reparto **conserva la energía**: la suma de los
departamentos debe reproducir el total de los mercados de origen.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.core.logging import get_logger
from src.data_collection.departamentos import validar_reparto
from src.data_collection.xm_departamentos import (
    XMDepartamentosClient,
    repartir,
    verificar_conservacion,
)
from src.data_collection.xm_upme import UPMEClient
from src.database.persistencia import guardar_demanda_departamento, guardar_proyeccion_upme
from src.database.session import SessionLocal

log = get_logger(__name__)

DIAS_POR_BLOQUE = 90


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicio", type=str, help="Fecha inicial AAAA-MM-DD")
    parser.add_argument("--fin", type=str, help="Fecha final AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--dias", type=int, help="Alternativa: últimos N días")
    parser.add_argument("--bloque", type=int, default=DIAS_POR_BLOQUE)
    parser.add_argument("--sin-upme", action="store_true", help="Omite los escenarios UPME")
    args = parser.parse_args()

    problemas = validar_reparto()
    if problemas:
        print("[ERROR] La tabla de reparto es incoherente:")
        for problema in problemas:
            print(f"  - {problema}")
        raise SystemExit(1)

    fecha_fin = date.fromisoformat(args.fin) if args.fin else date.today()
    if args.inicio:
        fecha_inicio = date.fromisoformat(args.inicio)
    elif args.dias:
        fecha_inicio = fecha_fin - timedelta(days=args.dias)
    else:
        fecha_inicio = fecha_fin - timedelta(days=365)

    cliente = XMDepartamentosClient()
    total_filas = total_insertados = total_actualizados = 0
    peor_error = 0.0
    departamentos: set[str] = set()

    print(f"Demanda por departamento de {fecha_inicio} a {fecha_fin}\n")

    for bloque_inicio, bloque_fin in _bloques(fecha_inicio, fecha_fin, args.bloque):
        por_mercado = cliente.obtener_por_mercado(bloque_inicio, bloque_fin)
        if por_mercado.empty:
            print(f"  {bloque_inicio} -> {bloque_fin}: sin datos")
            continue

        por_departamento = repartir(por_mercado)
        conserva, error = verificar_conservacion(por_mercado, por_departamento)
        peor_error = max(peor_error, error)

        with SessionLocal() as db:
            insertados, actualizados = guardar_demanda_departamento(db, por_departamento)

        total_filas += len(por_departamento)
        total_insertados += insertados
        total_actualizados += actualizados
        departamentos |= set(por_departamento["codigo_dane"])

        marca = "ok" if conserva else f"DESCUADRE {error:.2e}"
        print(
            f"  {bloque_inicio} -> {bloque_fin}: {len(por_departamento):>6,} filas "
            f"({insertados:>6,} nuevas)  [{marca}]"
        )

    if total_filas == 0:
        print("\n[ERROR] No se obtuvo ningún dato territorial.")
        raise SystemExit(1)

    print(f"\n[OK] {total_filas:,} registros por departamento")
    print(f"     Insertados:    {total_insertados:,}")
    print(f"     Actualizados:  {total_actualizados:,}")
    print(f"     Departamentos: {len(departamentos)}")
    print(f"     Error máximo de conservación: {peor_error:.2e}")

    if not args.sin_upme:
        _ingestar_upme(fecha_inicio, fecha_fin)


def _ingestar_upme(fecha_inicio: date, fecha_fin: date) -> None:
    # Los escenarios de la UPME son proyecciones: interesa el futuro, así que se
    # pide un margen amplio hacia adelante además del rango histórico.
    df = UPMEClient().obtener(fecha_inicio, fecha_fin + timedelta(days=365 * 3))
    if df.empty:
        print("\n[AVISO] XM no devolvió escenarios de la UPME para ese rango.")
        return

    with SessionLocal() as db:
        insertados, actualizados = guardar_proyeccion_upme(db, df)

    print(f"\n[OK] Escenarios UPME: {len(df)} meses ({insertados} nuevos)")
    print(f"     Rango: {df['mes'].min():%Y-%m} -> {df['mes'].max():%Y-%m}")


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
