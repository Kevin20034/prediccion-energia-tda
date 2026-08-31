"""Generación y consulta de predicciones de precio."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.prediccion import PrediccionSalida, SolicitudPrediccion
from src.core.logging import get_logger
from src.database.models import DatoHistorico, Prediccion
from src.models.entrenamiento import cargar_mejor_modelo
from src.processing.features import columnas_features, construir_features
from src.processing.limpieza import limpiar

log = get_logger(__name__)

router = APIRouter(prefix="/predicciones", tags=["Predicciones"])

#: Historia mínima necesaria para calcular los rezagos largos (168 h) y las
#: ventanas móviles de 720 h. Con menos, las features salen incompletas.
HORAS_CONTEXTO = 1000


@router.get(
    "",
    response_model=list[PrediccionSalida],
    summary="Consultar predicciones ya generadas",
)
def listar(
    db: SesionBD,
    _usuario: UsuarioActual,
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    limite: int = Query(200, ge=1, le=2000),
) -> list[Prediccion]:
    consulta = select(Prediccion)
    if desde:
        consulta = consulta.where(Prediccion.fecha_objetivo >= desde)
    if hasta:
        consulta = consulta.where(Prediccion.fecha_objetivo <= hasta)
    consulta = consulta.order_by(Prediccion.fecha_objetivo.desc()).limit(limite)
    return list(db.execute(consulta).scalars().all())


@router.post(
    "",
    response_model=list[PrediccionSalida],
    status_code=status.HTTP_201_CREATED,
    summary="Generar predicciones con el mejor modelo entrenado",
)
def generar(
    solicitud: SolicitudPrediccion,
    db: SesionBD,
    usuario: UsuarioActual,
) -> list[Prediccion]:
    """Estima el precio de las próximas `horas` horas.

    Método: se toman las últimas horas de histórico, se construyen las mismas
    variables que en el entrenamiento y se predice sobre las filas finales.

    .. note::
       Es una predicción *un paso adelante* repetida sobre el histórico
       disponible, no una proyección autorregresiva iterativa (que realimentaría
       sus propias predicciones y acumularía error). Es la aproximación honesta
       con los datos que hay: para horizontes largos habría que reentrenar con
       el horizonte deseado, que es justo lo que permite el parámetro
       `horizonte` de `POST /entrenar`.
    """
    try:
        modelo = cargar_mejor_modelo()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    df = _historico_reciente(db, HORAS_CONTEXTO + solicitud.horas)
    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay datos históricos. Ejecuta primero POST /datos/ingestar.",
        )

    datos = construir_features(limpiar(df), horizonte=1, eliminar_nulos=False).dropna(
        subset=modelo.columnas_features or columnas_features(df)
    )
    if datos.empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Histórico insuficiente para construir las variables predictoras",
        )

    ultimas = datas_finales(datos, solicitud.horas)

    try:
        estimaciones = modelo.predict(ultimas[modelo.columnas_features])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El modelo no pudo predecir con los datos disponibles: {exc}",
        ) from exc

    # Las fechas objetivo son las horas siguientes al último dato conocido.
    ultima_fecha = pd.Timestamp(datos["fecha_hora"].max())
    predicciones = [
        Prediccion(
            fecha_objetivo=(ultima_fecha + pd.Timedelta(hours=i + 1)).to_pydatetime(),
            precio_estimado=float(valor),
            nombre_modelo=modelo.nombre,
            usuario_id=usuario.id,
        )
        for i, valor in enumerate(estimaciones[-solicitud.horas :])
    ]

    if solicitud.guardar:
        # Idempotencia: reemplaza las predicciones previas del mismo modelo para
        # las mismas horas objetivo. Sin esto, llamar dos veces al endpoint
        # acumula duplicados que falsean cualquier métrica de producción
        # posterior (y el conteo de aciertos del informe).
        objetivos = [p.fecha_objetivo for p in predicciones]
        db.execute(
            delete(Prediccion).where(
                Prediccion.fecha_objetivo.in_(objetivos),
                Prediccion.nombre_modelo == modelo.nombre,
            )
        )

        db.add_all(predicciones)
        db.commit()
        for p in predicciones:
            db.refresh(p)

    log.info("%d predicciones generadas con '%s'", len(predicciones), modelo.nombre)
    return predicciones


# ---------------------------------------------------------------------------


def datas_finales(datos: pd.DataFrame, horas: int) -> pd.DataFrame:
    """Devuelve las filas finales necesarias para producir `horas` predicciones.

    Se conserva más contexto del estrictamente necesario porque la LSTM
    necesita su ventana completa para formar secuencias.
    """
    minimo = max(horas * 2, 200)
    return datos.tail(max(minimo, horas)).reset_index(drop=True)


def _historico_reciente(db: SesionBD, n_horas: int) -> pd.DataFrame:
    filas = (
        db.execute(
            select(DatoHistorico).order_by(DatoHistorico.fecha_hora.desc()).limit(n_horas)
        )
        .scalars()
        .all()
    )
    if not filas:
        return pd.DataFrame()

    columnas = [c.name for c in DatoHistorico.__table__.columns if c.name != "creado_en"]
    df = pd.DataFrame([{c: getattr(f, c) for c in columnas} for f in filas])
    return df.sort_values("fecha_hora").reset_index(drop=True)
