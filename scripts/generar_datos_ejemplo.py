"""Genera el CSV de datos **simulados** usado como respaldo cuando XM no responde.

IMPORTANTE: estos datos son SINTÉTICOS. No son cifras reales de XM y no deben
usarse para conclusiones del trabajo de grado; sirven para que el pipeline sea
ejecutable y demostrable sin conexión. Los datos reales se obtienen con
``python -m scripts.ingestar_datos``.

La simulación reproduce las regularidades documentadas del mercado colombiano:

* estacionalidad **horaria** (pico de demanda al mediodía y hacia las 19:00),
* estacionalidad **semanal** (menor demanda en fin de semana),
* estacionalidad **anual** (temporada seca diciembre–marzo → precio más alto),
* efecto **El Niño**: menos aportes hídricos → más térmica → precio más alto,
* relación inversa entre generación hidráulica y precio.

Uso:
    python scripts/generar_datos_ejemplo.py [--anios 2] [--semilla 42]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

RUTA_SALIDA = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "data_collection"
    / "samples"
    / "xm_historico_ejemplo.csv"
)


def generar(anios: int = 2, semilla: int = 42, fin: str | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(semilla)

    fecha_fin = pd.Timestamp(fin) if fin else pd.Timestamp("2025-12-31 23:00")
    fecha_inicio = fecha_fin - pd.DateOffset(years=anios) + pd.Timedelta(hours=1)
    idx = pd.date_range(fecha_inicio, fecha_fin, freq="h")
    n = len(idx)

    hora = idx.hour.to_numpy()
    dia_semana = idx.dayofweek.to_numpy()
    dia_anio = idx.dayofyear.to_numpy()

    # --- Índice ONI simulado: ciclo lento de ~3.5 años -----------------------
    t_anios = np.arange(n) / (24 * 365.25)
    oni = 1.4 * np.sin(2 * np.pi * t_anios / 3.5 + 0.8)
    oni += rng.normal(0, 0.08, n)
    oni = np.round(oni, 2)

    # --- Demanda (kWh) ------------------------------------------------------
    # Doble pico diario: mediodía y noche.
    perfil_horario = (
        1.0
        + 0.16 * np.sin(2 * np.pi * (hora - 7) / 24)
        + 0.10 * np.exp(-((hora - 19) ** 2) / 6)
        + 0.05 * np.exp(-((hora - 12) ** 2) / 8)
    )
    factor_semana = np.where(dia_semana >= 5, 0.90, 1.0)
    tendencia = 1 + 0.02 * t_anios  # crecimiento vegetativo de la demanda
    demanda = 9_500_000 * perfil_horario * factor_semana * tendencia
    demanda *= rng.normal(1.0, 0.025, n)

    # --- Hidrología ---------------------------------------------------------
    # Temporada seca en Colombia: diciembre–marzo (día del año cercano a 0/365).
    estacion_seca = np.cos(2 * np.pi * (dia_anio - 15) / 365.25)  # +1 en enero
    aportes = 100 - 22 * estacion_seca - 18 * oni + rng.normal(0, 6, n)
    aportes = np.clip(aportes, 25, 190)

    volumen_embalse = np.clip(
        62 - 12 * estacion_seca - 11 * oni + rng.normal(0, 4, n), 15, 95
    )

    # Cuanto mejor la hidrología, mayor participación hidráulica.
    fraccion_hidraulica = np.clip(0.48 + 0.0022 * (aportes - 100), 0.25, 0.80)
    generacion_hidraulica = demanda * fraccion_hidraulica
    generacion_termica = demanda * (1 - fraccion_hidraulica) * rng.normal(1.0, 0.03, n)
    disponibilidad = demanda * rng.normal(1.35, 0.04, n)

    # --- Clima local (Medellín) --------------------------------------------
    temperatura = (
        21.5
        + 4.5 * np.sin(2 * np.pi * (hora - 9) / 24)
        - 1.2 * estacion_seca
        + 0.6 * oni
        + rng.normal(0, 1.1, n)
    )
    prob_lluvia = np.clip(0.16 + 0.10 * (-estacion_seca) - 0.05 * oni, 0.02, 0.45)
    precipitacion = rng.exponential(2.2, n) * (rng.random(n) < prob_lluvia)
    humedad = np.clip(
        72 - 1.6 * (temperatura - 21.5) + 12 * (precipitacion > 0) + rng.normal(0, 4, n),
        35,
        99,
    )

    # --- Precio de bolsa (COP/kWh) -----------------------------------------
    # Escasez hídrica y alta demanda empujan el precio; buena hidrología lo baja.
    precio = (
        230
        + 2.6 * (100 - aportes)               # escasez de aportes
        + 1.9 * (62 - volumen_embalse)        # embalses bajos
        + 34 * oni                            # El Niño
        + 26 * (perfil_horario - 1) * 10      # pico horario
        + 260 * np.clip(fraccion_hidraulica, 0, 1) ** -1 - 470
    )
    precio *= rng.lognormal(0, 0.10, n)  # volatilidad multiplicativa
    # Picos de escasez esporádicos (2 % de las horas).
    picos = rng.random(n) < 0.02
    precio[picos] *= rng.uniform(1.4, 2.6, picos.sum())
    precio = np.clip(precio, 55, 3000)

    df = pd.DataFrame(
        {
            "fecha_hora": idx,
            "precio_bolsa": np.round(precio, 2),
            "demanda_real": np.round(demanda, 1),
            "generacion_hidraulica": np.round(generacion_hidraulica, 1),
            "generacion_termica": np.round(generacion_termica, 1),
            "disponibilidad_real": np.round(disponibilidad, 1),
            "aportes_hidricos": np.round(aportes, 2),
            "volumen_util_embalse": np.round(volumen_embalse, 2),
            "temperatura": np.round(temperatura, 2),
            "precipitacion": np.round(precipitacion, 2),
            "humedad_relativa": np.round(humedad, 1),
            "indice_oni": oni,
            "fenomeno_climatico": np.where(
                oni >= 0.5, "EL_NINO", np.where(oni <= -0.5, "LA_NINA", "NEUTRO")
            ),
            "fuente": "SIMULADO",
        }
    )
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anios", type=int, default=2, help="años de historia a generar")
    parser.add_argument("--semilla", type=int, default=42, help="semilla de reproducibilidad")
    parser.add_argument("--fin", type=str, default=None, help="fecha final, ej. 2025-12-31")
    args = parser.parse_args()

    df = generar(anios=args.anios, semilla=args.semilla, fin=args.fin)
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(RUTA_SALIDA, index=False)

    print(f"[OK] {len(df):,} registros escritos en {RUTA_SALIDA}")
    print(f"     Rango: {df['fecha_hora'].min()} -> {df['fecha_hora'].max()}")
    print(
        f"     Precio COP/kWh  min={df['precio_bolsa'].min():.1f}  "
        f"media={df['precio_bolsa'].mean():.1f}  max={df['precio_bolsa'].max():.1f}"
    )
    print(f"     Fenómenos: {df['fenomeno_climatico'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
