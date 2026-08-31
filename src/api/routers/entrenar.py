"""Disparo del entrenamiento de modelos."""

from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from src.api.deps import SesionBD, analista_o_superior
from src.api.schemas.prediccion import (
    EjecucionSalida,
    MetricasSalida,
    RespuestaEntrenamiento,
    ResultadoModeloSalida,
    SolicitudEntrenamiento,
)
from src.core.logging import get_logger
from src.database.models import DatoHistorico, EjecucionEntrenamiento
from src.models.entrenamiento import entrenar_todos

log = get_logger(__name__)

router = APIRouter(tags=["Entrenamiento"])

MINIMO_REGISTROS = 500


@router.post(
    "/entrenar",
    response_model=RespuestaEntrenamiento,
    summary="Entrenar y comparar los modelos predictivos",
    dependencies=[Depends(analista_o_superior)],
)
def entrenar(solicitud: SolicitudEntrenamiento, db: SesionBD) -> RespuestaEntrenamiento:
    """Entrena todos los modelos y devuelve la tabla comparativa.

    Es una operación **síncrona y pesada** (entre segundos y varios minutos
    según el volumen). Para producción, lo correcto sería encolarla en un
    *worker* (Celery, RQ o `BackgroundTasks`) y exponer un endpoint de estado;
    se deja síncrona a propósito para que la demostración del trabajo de grado
    sea directa y el resultado se vea en la misma respuesta.
    """
    df = _cargar_datos(db)

    if len(df) < MINIMO_REGISTROS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Se requieren al menos {MINIMO_REGISTROS} registros para entrenar; "
                f"hay {len(df)}. Ejecuta primero POST /datos/ingestar."
            ),
        )

    try:
        resultado = entrenar_todos(
            df,
            db=db,
            modelos=solicitud.modelos,
            horizonte=solicitud.horizonte,
            proporcion_test=solicitud.proporcion_test,
            criterio=solicitud.criterio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    assert resultado.mejor is not None

    return RespuestaEntrenamiento(
        mejor_modelo=resultado.mejor.nombre,
        criterio=solicitud.criterio,
        n_muestras_entrenamiento=resultado.n_train,
        n_muestras_prueba=resultado.n_test,
        resultados=[
            ResultadoModeloSalida(
                nombre=r.nombre,
                metricas=MetricasSalida(**r.metricas.as_dict()) if r.metricas else None,
                duracion_segundos=round(r.duracion_segundos, 2),
                es_mejor=r is resultado.mejor,
                error=r.error,
            )
            for r in resultado.resultados
        ],
    )


@router.get(
    "/entrenamientos",
    response_model=list[EjecucionSalida],
    summary="Histórico de entrenamientos",
    dependencies=[Depends(analista_o_superior)],
)
def historico(
    db: SesionBD,
    limite: int = Query(50, ge=1, le=500),
    solo_mejores: bool = Query(False),
) -> list[EjecucionEntrenamiento]:
    """Trazabilidad: qué se entrenó, cuándo y con qué error."""
    consulta = select(EjecucionEntrenamiento)
    if solo_mejores:
        consulta = consulta.where(EjecucionEntrenamiento.es_mejor.is_(True))
    consulta = consulta.order_by(EjecucionEntrenamiento.ejecutado_en.desc()).limit(limite)
    return list(db.execute(consulta).scalars().all())


# ---------------------------------------------------------------------------


def _cargar_datos(db: SesionBD) -> pd.DataFrame:
    """Vuelca `datos_historicos` a un `DataFrame`."""
    filas = db.execute(
        select(DatoHistorico).order_by(DatoHistorico.fecha_hora)
    ).scalars().all()

    if not filas:
        return pd.DataFrame()

    columnas = [c.name for c in DatoHistorico.__table__.columns if c.name != "creado_en"]
    return pd.DataFrame([{c: getattr(f, c) for c in columnas} for f in filas])
