"""Los trabajos que el planificador ejecuta periódicamente.

Son la versión desatendida de los scripts de `scripts/ingestar_*.py`. La
diferencia no es la lógica —es la misma: mismos clientes, misma limpieza, misma
escritura idempotente— sino el alcance: los scripts sirven para traer años de
historia, y esto solo mira **la ventana reciente**, que es lo único que puede
haber cambiado desde la última revisión.

Por qué siempre se repite una ventana en lugar de pedir «desde el último dato»
------------------------------------------------------------------------------

XM **corrige hacia atrás**: publica una demanda preliminar y la consolida días
después. Si cada revisión empezara justo donde acabó la anterior, esas
correcciones no se recogerían nunca y la base quedaría fijada en el primer valor
provisional que XM soltó. Repetir unos días cuesta poco —la escritura es
idempotente, actualiza en vez de duplicar— y es lo que mantiene el histórico
alineado con la fuente.
"""

from __future__ import annotations

from datetime import date, timedelta

from src.core.logging import get_logger
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient
from src.data_collection.xm_departamentos import XMDepartamentosClient
from src.database.persistencia import (
    guardar_datos_historicos,
    guardar_demanda_departamento,
)
from src.database.session import SessionLocal
from src.processing.limpieza import limpiar, unir_fuentes

log = get_logger(__name__)

#: Días hacia atrás que revisa cada pasada. Siete cubre de sobra la ventana en
#: la que XM todavía corrige lo publicado, sin descargar de más en cada ciclo.
DIAS_VENTANA = 7


def _ventana() -> tuple[date, date]:
    fin = date.today()
    return fin - timedelta(days=DIAS_VENTANA), fin


def ingestar_sistema() -> tuple[int, int]:
    """Serie horaria de XM más el clima del punto de referencia."""
    inicio, fin = _ventana()

    df_xm = XMClient().obtener(inicio, fin)
    df_clima = ClimaClient().obtener(inicio, fin)
    # Sin imputar: en la base se guarda lo que la fuente publicó, no lo estimado.
    # Rellenar aquí dejaría estimaciones marcadas como si fueran mediciones.
    df = limpiar(unir_fuentes(df_xm, df_clima), imputar=False)

    if df.empty:
        log.info("Ingesta del sistema: XM no devolvió nada nuevo en la ventana")
        return 0, 0

    with SessionLocal() as db:
        return guardar_datos_historicos(db, df)


def ingestar_departamentos() -> tuple[int, int]:
    """Demanda por mercado de comercialización, repartida por departamento."""
    inicio, fin = _ventana()

    df = XMDepartamentosClient().obtener(inicio, fin)
    if df.empty:
        return 0, 0

    with SessionLocal() as db:
        return guardar_demanda_departamento(db, df)


#: Orden deliberado: primero la serie del sistema, que es la que alimenta el
#: pronóstico y la portada. Si la segunda falla, lo importante ya está dentro.
TRABAJOS: tuple[tuple[str, object], ...] = (
    ("Sistema", ingestar_sistema),
    ("Departamentos", ingestar_departamentos),
)
