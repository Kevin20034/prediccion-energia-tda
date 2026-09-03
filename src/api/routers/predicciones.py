"""Generación y consulta de pronósticos.

Estrategia de pronóstico
------------------------

El artefacto de cada horizonte se entrenó con *direct multi-step*: el modelo de
720 h aprendió a mapear las variables del instante *t* al valor de *t + 720 h*.
Para producir la curva completa de las próximas *h* horas se aplica ese mismo
modelo a las **últimas h filas** del histórico: la fila *t* aporta el valor de
*t + h*, así que las filas ``t_final - h + 1 … t_final`` cubren exactamente
``t_final + 1 … t_final + h``.

Consecuencia honesta de este método: la primera hora del pronóstico se calcula
con variables de hace *h - 1* horas. A 24 h eso es irrelevante; a un mes
significa que el primer punto usa información de hace 29 días. Es el precio de
no realimentar predicciones sobre predicciones —que a 720 pasos acumula error
hasta volver la cifra inservible— y por eso la interfaz ofrece cada horizonte
con su propio modelo en vez de estirar el de 24 h.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.prediccion import (
    MetricasSalida,
    PrediccionSalida,
    PuntoObservado,
    RespuestaPronostico,
    SolicitudPrediccion,
)
from src.core.logging import get_logger
from src.database.models import DatoHistorico, Prediccion
from src.models.entrenamiento import (
    HORIZONTES,
    ArtefactoPronostico,
    cargar_artefacto,
)
from src.processing.features import OBJETIVO_POR_DEFECTO, construir_features
from src.processing.limpieza import limpiar

log = get_logger(__name__)

router = APIRouter(tags=["Pronóstico"])

#: Historia mínima necesaria para calcular los rezagos largos (336 h) y las
#: ventanas móviles de 720 h. Con menos, las features salen incompletas.
HORAS_CONTEXTO = 1200

#: Puntos de histórico que acompañan al pronóstico en la gráfica, por horizonte.
#: La proporción importa: si el histórico ocupa el 95 % del ancho, la parte
#: pronosticada —que es lo que se ha venido a ver— queda aplastada contra el
#: borde. Se muestran unas tres veces las horas pronosticadas.
def _ventana_observada(horizonte: int) -> int:
    return min(max(horizonte * 3, 168), 2160)


def _etiqueta(horizonte: int) -> str:
    for etiqueta, horas in HORIZONTES.items():
        if horas == horizonte:
            return etiqueta
    return f"{horizonte}h"


@router.get(
    "/predicciones",
    response_model=list[PrediccionSalida],
    summary="Consultar predicciones ya generadas",
)
def listar(
    db: SesionBD,
    _usuario: UsuarioActual,
    objetivo: str | None = Query(None),
    horizonte: int | None = Query(None, ge=1, le=720),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    limite: int = Query(200, ge=1, le=2000),
) -> list[Prediccion]:
    consulta = select(Prediccion)
    if objetivo:
        consulta = consulta.where(Prediccion.objetivo == objetivo)
    if horizonte:
        consulta = consulta.where(Prediccion.horizonte_horas == horizonte)
    if desde:
        consulta = consulta.where(Prediccion.fecha_objetivo >= desde)
    if hasta:
        consulta = consulta.where(Prediccion.fecha_objetivo <= hasta)
    consulta = consulta.order_by(Prediccion.fecha_objetivo.desc()).limit(limite)
    return list(db.execute(consulta).scalars().all())


@router.post(
    "/predicciones",
    response_model=list[PrediccionSalida],
    status_code=status.HTTP_201_CREATED,
    summary="Generar el pronóstico con el modelo del horizonte pedido",
)
def generar(
    solicitud: SolicitudPrediccion,
    db: SesionBD,
    usuario: UsuarioActual,
) -> list[Prediccion]:
    """Estima el objetivo para las próximas `horizonte` horas."""
    artefacto = _artefacto(solicitud.objetivo, solicitud.horizonte)
    predicciones = _calcular(db, artefacto, usuario_id=usuario.id)

    if solicitud.guardar:
        _persistir(db, predicciones, artefacto)

    log.info(
        "%d predicciones de %s a %dh con '%s'",
        len(predicciones),
        artefacto.objetivo,
        artefacto.horizonte,
        artefacto.modelo.nombre,
    )
    return predicciones


@router.get(
    "/pronostico",
    response_model=RespuestaPronostico,
    summary="Histórico reciente + pronóstico con banda, en una sola llamada",
)
def pronostico(
    db: SesionBD,
    usuario: UsuarioActual,
    objetivo: str = Query(OBJETIVO_POR_DEFECTO, pattern="^(precio_bolsa|demanda_real)$"),
    horizonte: int = Query(24, ge=1, le=720),
    recalcular: bool = Query(
        False, description="Fuerza recalcular en vez de reutilizar lo ya guardado"
    ),
) -> RespuestaPronostico:
    """Lo que la gráfica principal necesita, resuelto de una vez.

    Reutiliza el pronóstico guardado si sigue siendo posterior al último dato
    observado. Si el histórico ya alcanzó a las predicciones, esas predicciones
    dejaron de ser pronóstico —son historial— y se recalculan.
    """
    artefacto = _artefacto(objetivo, horizonte)

    ultimo = db.execute(
        select(DatoHistorico.fecha_hora)
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).scalar_one_or_none()

    guardadas: list[Prediccion] = []
    if not recalcular and ultimo is not None:
        guardadas = list(
            db.execute(
                select(Prediccion)
                .where(
                    Prediccion.objetivo == objetivo,
                    Prediccion.horizonte_horas == horizonte,
                    Prediccion.fecha_objetivo > ultimo,
                )
                .order_by(Prediccion.fecha_objetivo)
            )
            .scalars()
            .all()
        )

    if not guardadas:
        guardadas = _calcular(db, artefacto, usuario_id=usuario.id)
        _persistir(db, guardadas, artefacto)

    observado = _observado(db, objetivo, _ventana_observada(horizonte))

    return RespuestaPronostico(
        objetivo=objetivo,
        unidad=artefacto.unidad,
        horizonte=horizonte,
        etiqueta_horizonte=_etiqueta(horizonte),
        nombre_modelo=artefacto.modelo.nombre,
        entrenado_en=artefacto.entrenado_en,
        metricas=MetricasSalida(**artefacto.metricas) if artefacto.metricas else None,
        corte=observado[-1].fecha_hora if observado else None,
        observado=observado,
        pronostico=[PrediccionSalida.model_validate(p) for p in guardadas],
    )


@router.get("/pronostico/horizontes", summary="Horizontes con modelo entrenado")
def horizontes_disponibles(_usuario: UsuarioActual) -> dict:
    """Qué combinaciones objetivo/horizonte tienen artefacto en disco.

    El frontend lo usa para deshabilitar las pestañas que aún no se pueden
    mostrar, en vez de ofrecerlas y devolver un 409 al pulsarlas.
    """
    from src.models.entrenamiento import artefactos_disponibles

    return {
        "horizontes": [
            {"etiqueta": etiqueta, "horas": horas} for etiqueta, horas in HORIZONTES.items()
        ],
        "disponibles": [
            {
                "objetivo": a.objetivo,
                "horizonte": a.horizonte,
                "etiqueta": _etiqueta(a.horizonte),
                "modelo": a.modelo.nombre,
                "unidad": a.unidad,
                "entrenado_en": a.entrenado_en,
                "rmse": a.metricas.get("rmse"),
            }
            for a in artefactos_disponibles()
        ],
    }


# ---------------------------------------------------------------------------


def _artefacto(objetivo: str, horizonte: int) -> ArtefactoPronostico:
    try:
        return cargar_artefacto(objetivo, horizonte)
    except (FileNotFoundError, TypeError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


def _calcular(
    db: SesionBD, artefacto: ArtefactoPronostico, *, usuario_id: int | None
) -> list[Prediccion]:
    """Aplica el modelo a las últimas `horizonte` filas del histórico."""
    horizonte = artefacto.horizonte
    df = _historico_reciente(db, HORAS_CONTEXTO + horizonte)
    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay datos históricos. Ejecuta primero POST /datos/ingestar.",
        )

    datos = construir_features(
        limpiar(df, objetivo=artefacto.objetivo),
        objetivo=artefacto.objetivo,
        horizonte=horizonte,
        eliminar_nulos=False,
    ).dropna(subset=artefacto.columnas)

    if datos.empty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Histórico insuficiente para construir las variables predictoras "
                f"del horizonte de {horizonte} h"
            ),
        )

    # La LSTM necesita su ventana completa para formar secuencias, así que se le
    # pasa más contexto del estrictamente necesario y se recorta la salida.
    filas = datos.tail(max(horizonte * 2, 200))

    try:
        estimaciones = artefacto.modelo.predict(filas[artefacto.columnas])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El modelo no pudo predecir con los datos disponibles: {exc}",
        ) from exc

    estimaciones = estimaciones[-horizonte:]
    inferiores, superiores = artefacto.banda(estimaciones)

    ultima_fecha = pd.Timestamp(datos["fecha_hora"].max())
    return [
        Prediccion(
            fecha_objetivo=(ultima_fecha + pd.Timedelta(hours=i + 1)).to_pydatetime(),
            objetivo=artefacto.objetivo,
            horizonte_horas=horizonte,
            unidad=artefacto.unidad,
            valor_estimado=float(valor),
            limite_inferior=float(inferiores[i]),
            limite_superior=float(superiores[i]),
            nombre_modelo=artefacto.modelo.nombre,
            usuario_id=usuario_id,
        )
        for i, valor in enumerate(estimaciones)
    ]


def _persistir(
    db: SesionBD, predicciones: list[Prediccion], artefacto: ArtefactoPronostico
) -> None:
    """Guarda reemplazando las anteriores del mismo objetivo, horizonte y hora.

    Sin este reemplazo, llamar dos veces al endpoint acumula duplicados que
    falsean cualquier métrica de producción posterior y el conteo de aciertos
    del informe.
    """
    if not predicciones:
        return

    db.execute(
        delete(Prediccion).where(
            Prediccion.fecha_objetivo.in_([p.fecha_objetivo for p in predicciones]),
            Prediccion.objetivo == artefacto.objetivo,
            Prediccion.horizonte_horas == artefacto.horizonte,
        )
    )
    db.add_all(predicciones)
    db.commit()
    for p in predicciones:
        db.refresh(p)


def _observado(db: SesionBD, objetivo: str, n_horas: int) -> list[PuntoObservado]:
    columna = getattr(DatoHistorico, objetivo)
    filas = db.execute(
        select(DatoHistorico.fecha_hora, columna)
        .where(columna.isnot(None))
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(n_horas)
    ).all()

    return [
        PuntoObservado(fecha_hora=fila[0], valor=float(fila[1])) for fila in reversed(filas)
    ]


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
