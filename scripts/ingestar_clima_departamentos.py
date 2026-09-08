"""Ingesta del clima horario por departamento.

Uso:
    python -m scripts.ingestar_clima_departamentos --inicio 2023-01-01
    python -m scripts.ingestar_clima_departamentos --dias 7

Descarga temperatura, precipitación y humedad en la capital de cada uno de los
33 departamentos y las guarda en `clima_departamento`. Es lo que alimenta el mapa
del fenómeno del Niño.

La historia completa son unos tres años por 33 departamentos: alrededor de un
millón de filas y entre 15 y 25 minutos. Corre una sola vez; a partir de ahí el
planificador mantiene la ventana reciente al día.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from src.core.logging import get_logger
from src.data_collection.clima_departamentos import ClimaDepartamentosClient
from src.data_collection.departamentos import DEPARTAMENTOS
from src.database.persistencia import guardar_clima_departamento
from src.database.session import SessionLocal

log = get_logger(__name__)

#: Open-Meteo corta las peticiones muy largas, y con 33 coordenadas en paralelo
#: los bloques grandes además tardan en dar señales de vida. Noventa días es el
#: punto donde el avance se ve y la petición no se rechaza.
DIAS_POR_BLOQUE = 90


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicio", type=str, help="Fecha inicial AAAA-MM-DD")
    parser.add_argument("--fin", type=str, help="Fecha final AAAA-MM-DD (por defecto hoy)")
    parser.add_argument("--dias", type=int, help="Alternativa: últimos N días")
    parser.add_argument("--bloque", type=int, default=DIAS_POR_BLOQUE)
    args = parser.parse_args()

    sin_coordenada = [d.nombre for d in DEPARTAMENTOS if not d.latitud or not d.longitud]
    if sin_coordenada:
        print(f"[ERROR] Departamentos sin coordenada: {', '.join(sin_coordenada)}")
        raise SystemExit(1)

    fecha_fin = date.fromisoformat(args.fin) if args.fin else date.today()
    if args.inicio:
        fecha_inicio = date.fromisoformat(args.inicio)
    elif args.dias:
        fecha_inicio = fecha_fin - timedelta(days=args.dias)
    else:
        fecha_inicio = fecha_fin - timedelta(days=365)

    cliente = ClimaDepartamentosClient()
    total_filas = total_insertados = total_actualizados = 0
    departamentos_vistos: set[str] = set()

    print(f"Clima de {len(DEPARTAMENTOS)} departamentos, de {fecha_inicio} a {fecha_fin}\n")

    for bloque_inicio, bloque_fin in _bloques(fecha_inicio, fecha_fin, args.bloque):
        df = cliente.obtener(bloque_inicio, bloque_fin)

        if df.empty:
            print(f"  {bloque_inicio} -> {bloque_fin}: sin datos")
            continue

        with SessionLocal() as db:
            insertados, actualizados = guardar_clima_departamento(db, df)

        total_filas += len(df)
        total_insertados += insertados
        total_actualizados += actualizados
        departamentos_vistos |= set(df["codigo_dane"].unique())

        print(
            f"  {bloque_inicio} -> {bloque_fin}: {len(df):>7,} filas "
            f"({insertados:>7,} nuevas, {actualizados:>7,} actualizadas) "
            f"· {df['codigo_dane'].nunique()} deptos"
        )

    if total_filas == 0:
        print("\n[ERROR] No se obtuvo ningún dato de Open-Meteo.")
        raise SystemExit(1)

    print(f"\n[OK] {total_filas:,} registros procesados")
    print(f"     Insertados:    {total_insertados:,}")
    print(f"     Actualizados:  {total_actualizados:,}")
    print(f"     Departamentos: {len(departamentos_vistos)} de {len(DEPARTAMENTOS)}")

    faltan = {d.codigo for d in DEPARTAMENTOS} - departamentos_vistos
    if faltan:
        nombres = ", ".join(d.nombre for d in DEPARTAMENTOS if d.codigo in faltan)
        # No es motivo de fallo —el resto del mapa sirve— pero tiene que verse:
        # un departamento en gris por falta de datos se confunde a simple vista
        # con uno que no está en el SIN.
        print(f"\n[AVISO] Sin datos: {nombres}")


def _bloques(inicio: date, fin: date, dias: int) -> list[tuple[date, date]]:
    tramos: list[tuple[date, date]] = []
    actual = inicio
    while actual <= fin:
        tramos.append((actual, min(actual + timedelta(days=dias - 1), fin)))
        actual += timedelta(days=dias)
    return tramos


if __name__ == "__main__":
    main()
