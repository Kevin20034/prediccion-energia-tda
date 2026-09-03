"""Demanda energética por departamento, a partir de los mercados de XM.

XM publica ``DemaCome`` desagregada por ``MercadoComercializacion``: 29 mercados
con demanda **horaria real**. `departamentos.REPARTO` traduce esos mercados a
los 33 departamentos del DANE; este módulo hace la descarga y aplica el reparto.

El resultado es un `DataFrame` largo —una fila por hora y departamento— porque
es la forma natural de guardarlo en base de datos y de servirlo al mapa. El
ancho (una columna por departamento) solo se materializa en el momento de
graficar.

Sobre el total nacional
-----------------------

La suma de los 33 departamentos reproduce exactamente la demanda comercial
publicada por XM para los mercados: el reparto redistribuye, no crea ni
destruye energía. `verificar_conservacion` lo comprueba y es lo que permite
afirmar en el trabajo de grado que el mapa cuadra con la fuente.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.core.logging import get_logger
from src.data_collection import xm_api
from src.data_collection.base import ErrorRecoleccion, Recolector
from src.data_collection.departamentos import (
    POR_CODIGO,
    departamentos_de,
    es_estimado,
)

log = get_logger(__name__)

ENTIDAD_MERCADO = "MercadoComercializacion"
METRICA_DEMANDA = "DemaCome"

#: Tolerancia relativa al comprobar que el reparto conserva la energía.
#: 1e-9 sería exigirle a la aritmética de coma flotante más de lo que puede dar
#: sumando millones de valores; 1e-6 detecta cualquier error real de pesos.
TOLERANCIA_CONSERVACION = 1e-6


class XMDepartamentosClient(Recolector):
    """Descarga la demanda por mercado de comercialización y la reparte por departamento."""

    nombre = "XM-Departamentos"

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Devuelve la demanda horaria por departamento.

        Returns:
            `DataFrame` con `fecha_hora`, `codigo_dane`, `departamento`,
            `demanda_kwh`, `estimado` y `mercados` (los mercados que aportaron,
            separados por `+`, para poder trazar de dónde sale cada cifra).
        """
        crudo = self.obtener_por_mercado(fecha_inicio, fecha_fin)
        if crudo.empty:
            raise ErrorRecoleccion(
                "XM no devolvió demanda por mercado de comercialización para ese rango"
            )
        return repartir(crudo)

    def obtener_por_mercado(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Descarga cruda: `fecha_hora`, `mercado`, `demanda_kwh`."""
        if fecha_inicio > fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

        peticiones = xm_api.peticiones_para(
            "hourly", METRICA_DEMANDA, ENTIDAD_MERCADO, fecha_inicio, fecha_fin
        )
        trozos = [
            xm_api.aplanar_horaria(payload, "demanda_kwh", por_entidad=True)
            for _, payload in xm_api.ejecutar_todas(peticiones)
        ]

        df = xm_api.concatenar(trozos)
        if df.empty:
            return df

        df = df.rename(columns={"entidad": "mercado"})
        df["mercado"] = df["mercado"].astype(str).str.strip().str.upper()
        df = (
            df.groupby(["fecha_hora", "mercado"], as_index=False)["demanda_kwh"]
            .mean()
            .sort_values(["fecha_hora", "mercado"])
        )

        log.info(
            "XM: demanda de %d mercados · %d horas",
            df["mercado"].nunique(),
            df["fecha_hora"].nunique(),
        )
        return df


# ---------------------------------------------------------------------------
# Reparto
# ---------------------------------------------------------------------------


def repartir(por_mercado: pd.DataFrame) -> pd.DataFrame:
    """Aplica `REPARTO` y agrega por departamento.

    Los mercados que no estén catalogados se registran en el log y se descartan:
    aparecería uno nuevo solo si XM reorganiza el mercado de comercialización, y
    en ese caso hay que decidir a mano a qué departamento pertenece, no
    adivinarlo.
    """
    if por_mercado.empty:
        return pd.DataFrame()

    desconocidos = sorted(
        {m for m in por_mercado["mercado"].unique() if not departamentos_de(m)}
    )
    if desconocidos:
        log.warning(
            "Mercados sin reparto definido, se descartan: %s. "
            "Añádelos a departamentos.REPARTO.",
            ", ".join(desconocidos),
        )

    filas: list[dict] = []
    for fila in por_mercado.itertuples(index=False):
        for codigo, peso in departamentos_de(fila.mercado):
            filas.append(
                {
                    "fecha_hora": fila.fecha_hora,
                    "codigo_dane": codigo,
                    "demanda_kwh": float(fila.demanda_kwh) * peso,
                    "estimado": es_estimado(fila.mercado),
                    "mercado": fila.mercado,
                }
            )

    if not filas:
        return pd.DataFrame()

    largo = pd.DataFrame(filas)

    agregado = largo.groupby(["fecha_hora", "codigo_dane"], as_index=False).agg(
        demanda_kwh=("demanda_kwh", "sum"),
        # Un departamento se marca estimado si CUALQUIERA de los mercados que lo
        # alimentan lo es: basta una parte repartida para que el total deje de
        # ser una medición directa.
        estimado=("estimado", "any"),
        mercados=("mercado", lambda s: "+".join(sorted(set(s)))),
    )

    agregado["departamento"] = agregado["codigo_dane"].map(
        lambda c: POR_CODIGO[c].nombre if c in POR_CODIGO else c
    )

    return agregado.sort_values(["fecha_hora", "codigo_dane"]).reset_index(drop=True)


def verificar_conservacion(
    por_mercado: pd.DataFrame, por_departamento: pd.DataFrame
) -> tuple[bool, float]:
    """¿El reparto conservó la energía total?

    Returns:
        `(conserva, error_relativo)`. El error relativo se compara solo sobre
        los mercados con reparto definido: si se descartó alguno por no estar
        catalogado, es correcto que el total baje y no es un fallo del reparto.
    """
    if por_mercado.empty or por_departamento.empty:
        return False, float("inf")

    conocidos = por_mercado[por_mercado["mercado"].map(lambda m: bool(departamentos_de(m)))]
    total_origen = float(conocidos["demanda_kwh"].sum())
    total_destino = float(por_departamento["demanda_kwh"].sum())

    if total_origen == 0:
        return total_destino == 0, 0.0

    error = abs(total_destino - total_origen) / total_origen
    return error <= TOLERANCIA_CONSERVACION, error
