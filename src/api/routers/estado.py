"""Estado de los datos: cuánto hace que cada fuente publicó algo.

Este endpoint existe por un fallo concreto. El sistema estuvo sirviendo datos del
31 de agosto durante toda la primera semana de septiembre sin que nada en
pantalla lo dijera: las gráficas se veían perfectas, el pronóstico se calculaba,
y todo era viejo. Una interfaz que no puede distinguir «no ha pasado nada» de
«nadie está mirando» acaba mintiendo por omisión.

De ahí que se devuelvan dos relojes distintos y separados:

* `ultimo_dato` — hasta cuándo llega lo que la fuente publicó.
* `ultima_revision` — cuándo se comprobó por última vez si había algo nuevo.

Pueden estar muy lejos el uno del otro y ninguno sustituye al otro.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.estado import FuenteSalida, RespuestaEstado
from src.core.config import settings
from src.database.models import DatoHistorico, DemandaDepartamento

router = APIRouter(tags=["Estado"])

#: Cada fuente con la tabla y la columna temporal que la representan.
FUENTES: tuple[tuple[str, type, str], ...] = (
    ("XM", DatoHistorico, "Serie horaria del sistema: precio, demanda y generación"),
    ("Departamentos", DemandaDepartamento, "Demanda horaria repartida por departamento"),
)


@router.get(
    "/estado-datos",
    response_model=RespuestaEstado,
    summary="Frescura de cada fuente y estado de la ingesta automática",
)
def estado_datos(db: SesionBD, _usuario: UsuarioActual) -> RespuestaEstado:
    ahora = datetime.now(UTC)

    fuentes = [
        _frescura(db, nombre, modelo, descripcion, ahora)
        for nombre, modelo, descripcion in FUENTES
    ]

    # Se importa aquí y no arriba para no crear un ciclo: el planificador
    # necesita la sesión de base de datos, que a su vez arrastra la app.
    from src.api.planificador import planificador

    marcas = planificador.estado()

    return RespuestaEstado(
        fuentes=fuentes,
        consultado_en=ahora,
        ultima_revision=marcas["ultima_revision"],
        proxima_revision=marcas["proxima_revision"],
        ingesta_automatica=settings.INGESTA_AUTOMATICA,
        intervalo_minutos=settings.INGESTA_INTERVALO_MINUTOS,
    )


def _frescura(
    db: SesionBD, nombre: str, modelo: type, descripcion: str, ahora: datetime
) -> FuenteSalida:
    """Última marca temporal y antigüedad de una fuente."""
    ultimo, filas = db.execute(
        select(func.max(modelo.fecha_hora), func.count()).select_from(modelo)
    ).one()

    if ultimo is None:
        # Sin datos no hay retraso que medir. Devolver 0 aquí se pintaría en la
        # barra como "al día", que es exactamente lo contrario de la verdad.
        return FuenteSalida(nombre=nombre, filas=0, descripcion=descripcion)

    # SQLite devuelve la marca sin zona horaria; PostgreSQL con ella. Sin este
    # ajuste la resta revienta en las pruebas y funciona en producción, que es
    # la peor combinación posible.
    if ultimo.tzinfo is None:
        ultimo = ultimo.replace(tzinfo=UTC)

    return FuenteSalida(
        nombre=nombre,
        ultimo_dato=ultimo,
        horas_de_retraso=round((ahora - ultimo).total_seconds() / 3600, 2),
        filas=filas,
        descripcion=descripcion,
    )
