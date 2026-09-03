"""Proyecciones oficiales de demanda de la UPME, publicadas a través de XM.

La UPME (Unidad de Planeación Minero Energética) publica tres escenarios de
demanda nacional —alto, medio y bajo— con resolución **mensual**. XM los expone
como métricas ``EscDemUPMEAlto``, ``EscDemUPMEMedio`` y ``EscDemUPMEBajo``.

Para qué sirven aquí
--------------------

Son la referencia con la que se contrasta el pronóstico a un mes del proyecto.
No son un competidor del modelo: son de otra naturaleza —planeación de largo
plazo, no pronóstico operativo— y por eso la comparación es informativa, no una
métrica de error. Que el pronóstico propio caiga dentro de la banda
alto–bajo de la UPME es una señal de que no se ha ido a ninguna parte rara;
que se salga sistemáticamente es una señal de que hay que mirarlo.

Unidades: kWh de energía **mensual** para todo el SIN.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.core.logging import get_logger
from src.data_collection import xm_api

log = get_logger(__name__)

ENTIDAD = "Sistema"

#: ``MetricId -> nombre del escenario``.
ESCENARIOS: dict[str, str] = {
    "EscDemUPMEAlto": "alto",
    "EscDemUPMEMedio": "medio",
    "EscDemUPMEBajo": "bajo",
}


class UPMEClient:
    """Descarga los escenarios mensuales de demanda proyectada de la UPME."""

    nombre = "UPME"

    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Devuelve un `DataFrame` ancho: `mes`, `alto`, `medio`, `bajo`.

        El índice temporal es el primer día de cada mes, que es como XM fecha
        las series mensuales.
        """
        if fecha_inicio > fecha_fin:
            raise ValueError("fecha_inicio no puede ser posterior a fecha_fin")

        resultado: pd.DataFrame | None = None

        for metric_id, escenario in ESCENARIOS.items():
            peticiones = xm_api.peticiones_para(
                "monthly", metric_id, ENTIDAD, fecha_inicio, fecha_fin
            )
            trozos = [
                xm_api.aplanar_mensual(payload, escenario)
                for _, payload in xm_api.ejecutar_todas(peticiones)
            ]
            serie = xm_api.concatenar(trozos)
            if serie.empty:
                log.warning("UPME: el escenario '%s' no devolvió datos", escenario)
                continue

            serie = serie.groupby("fecha_hora", as_index=False)[escenario].mean()
            resultado = (
                serie
                if resultado is None
                else resultado.merge(serie, on="fecha_hora", how="outer")
            )

        if resultado is None or resultado.empty:
            return pd.DataFrame(columns=["mes", *ESCENARIOS.values()])

        resultado = resultado.rename(columns={"fecha_hora": "mes"})
        log.info("UPME: %d meses proyectados", len(resultado))
        return resultado.sort_values("mes").reset_index(drop=True)


def contrastar(proyeccion: pd.DataFrame, demanda_real_mensual: pd.DataFrame) -> pd.DataFrame:
    """Cruza los escenarios UPME con la demanda mensual observada.

    Args:
        proyeccion: salida de `UPMEClient.obtener`.
        demanda_real_mensual: `DataFrame` con `mes` y `demanda_kwh`.

    Returns:
        El cruce con una columna `posicion`: dónde cae lo observado respecto de
        la banda proyectada (`sobre_alto`, `en_banda`, `bajo_bajo`).
    """
    if proyeccion.empty or demanda_real_mensual.empty:
        return pd.DataFrame()

    df = proyeccion.merge(demanda_real_mensual, on="mes", how="inner")
    if df.empty:
        return df

    def situar(fila: pd.Series) -> str:
        if pd.notna(fila.get("alto")) and fila["demanda_kwh"] > fila["alto"]:
            return "sobre_alto"
        if pd.notna(fila.get("bajo")) and fila["demanda_kwh"] < fila["bajo"]:
            return "bajo_bajo"
        return "en_banda"

    df["posicion"] = df.apply(situar, axis=1)
    return df
