"""Demanda energética por departamento y escenarios de la UPME.

El mapa del frontend se alimenta de `GET /departamentos/mapa`. La ingesta la
dispara `POST /departamentos/ingestar`, que descarga la demanda por mercado de
comercialización de XM y la reparte según la tabla documentada en
`data_collection.departamentos`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select

from src.api.deps import SesionBD, UsuarioActual, analista_o_superior
from src.api.schemas.territorio import (
    DepartamentoSalida,
    EscenarioUPME,
    PuntoDemanda,
    RespuestaIngestaTerritorio,
    RespuestaMapa,
    RespuestaUPME,
    SerieDepartamento,
)
from src.core.logging import get_logger
from src.data_collection.departamentos import DEPARTAMENTOS, POR_CODIGO
from src.data_collection.xm_departamentos import (
    XMDepartamentosClient,
    repartir,
    verificar_conservacion,
)
from src.data_collection.xm_upme import UPMEClient
from src.database.models import DatoHistorico, DemandaDepartamento, ProyeccionUPME
from src.database.persistencia import guardar_demanda_departamento, guardar_proyeccion_upme

log = get_logger(__name__)

router = APIRouter(tags=["Territorio"])

RESOLUCIONES: dict[str, str] = {"hora": "hour", "dia": "day", "semana": "week", "mes": "month"}


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------


@router.get(
    "/departamentos/mapa",
    response_model=RespuestaMapa,
    summary="Demanda por departamento para el mapa interactivo",
)
def mapa(
    db: SesionBD,
    _usuario: UsuarioActual,
    horas: int = Query(24, ge=1, le=720, description="Ventana agregada hacia atrás"),
) -> RespuestaMapa:
    """Instantánea de la demanda de cada departamento.

    Devuelve **los 33 departamentos siempre**, incluidos los que no están
    conectados al SIN. Omitirlos dejaría huecos en el mapa que el usuario
    interpretaría como un fallo de carga; devolverlos con `interconectado=False`
    permite pintarlos con su propio tratamiento y explicar por qué no tienen
    dato.
    """
    ultimo = db.execute(select(func.max(DemandaDepartamento.fecha_hora))).scalar_one_or_none()
    if ultimo is None:
        return RespuestaMapa(
            instante=None, horas_agregadas=horas, total_nacional=None,
            departamentos=[_vacio(d.codigo) for d in DEPARTAMENTOS],
        )

    inicio = ultimo - timedelta(hours=horas - 1)
    inicio_previo = inicio - timedelta(hours=horas)

    actual = _agregar(db, inicio, ultimo)
    previo = _agregar(db, inicio_previo, inicio - timedelta(hours=1))
    media_7d = _media_horaria(db, ultimo - timedelta(days=7), ultimo)
    picos = _hora_pico(db, ultimo - timedelta(days=7), ultimo)

    total_nacional = sum(v["total"] for v in actual.values()) or None

    departamentos = []
    for departamento in DEPARTAMENTOS:
        datos = actual.get(departamento.codigo)
        if datos is None:
            departamentos.append(_vacio(departamento.codigo))
            continue

        anterior = previo.get(departamento.codigo, {}).get("total")
        departamentos.append(
            DepartamentoSalida(
                codigo_dane=departamento.codigo,
                departamento=departamento.nombre,
                interconectado=departamento.interconectado,
                demanda_ultima_hora=datos["ultima"],
                demanda_24h=datos["total"],
                demanda_media_horaria_7d=media_7d.get(departamento.codigo),
                variacion_24h=_variacion(datos["total"], anterior),
                participacion=(
                    round(datos["total"] / total_nacional * 100, 2) if total_nacional else None
                ),
                pico_horario=picos.get(departamento.codigo),
                estimado=datos["estimado"],
                mercados=datos["mercados"],
            )
        )

    return RespuestaMapa(
        instante=ultimo,
        horas_agregadas=horas,
        total_nacional=total_nacional,
        departamentos=departamentos,
    )


@router.get(
    "/departamentos/{codigo}/serie",
    response_model=SerieDepartamento,
    summary="Serie temporal de un departamento",
)
def serie_departamento(
    db: SesionBD,
    _usuario: UsuarioActual,
    codigo: str = Path(..., min_length=1, max_length=2, description="Código DANE"),
    resolucion: str = Query("hora", pattern="^(hora|dia|semana|mes)$"),
    limite: int = Query(720, ge=10, le=5000),
) -> SerieDepartamento:
    """Demanda del departamento en el tiempo, para el panel de detalle del mapa."""
    codigo = codigo.zfill(2)
    if codigo not in POR_CODIGO:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Departamento '{codigo}' desconocido"
        )

    truncado = func.date_trunc(RESOLUCIONES[resolucion], DemandaDepartamento.fecha_hora)
    filas = db.execute(
        select(
            truncado.label("instante"),
            func.sum(DemandaDepartamento.demanda_kwh).label("total"),
            func.bool_or(DemandaDepartamento.factor_estimado).label("estimado"),
        )
        .where(DemandaDepartamento.codigo_dane == codigo)
        .group_by(truncado)
        .order_by(truncado.desc())
        .limit(limite)
    ).all()

    filas = list(reversed(filas))

    return SerieDepartamento(
        codigo_dane=codigo,
        departamento=POR_CODIGO[codigo].nombre,
        estimado=any(f.estimado for f in filas),
        resolucion=resolucion,
        puntos=[
            PuntoDemanda(fecha_hora=f.instante, demanda_kwh=float(f.total)) for f in filas
        ],
    )


@router.post(
    "/departamentos/ingestar",
    response_model=RespuestaIngestaTerritorio,
    status_code=status.HTTP_201_CREATED,
    summary="Descargar la demanda por mercado de XM y repartirla por departamento",
    dependencies=[Depends(analista_o_superior)],
)
def ingestar_departamentos(
    db: SesionBD,
    fecha_inicio: date = Query(..., description="Formato AAAA-MM-DD"),
    fecha_fin: date | None = Query(None, description="Por defecto, hoy"),
) -> RespuestaIngestaTerritorio:
    """Ingesta territorial, con comprobación de que el reparto conserva la energía."""
    fecha_fin = fecha_fin or date.today()
    if fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_inicio no puede ser posterior a fecha_fin",
        )

    cliente = XMDepartamentosClient()
    por_mercado = cliente.obtener_por_mercado(fecha_inicio, fecha_fin)
    if por_mercado.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="XM no devolvió demanda por mercado de comercialización para ese rango",
        )

    por_departamento = repartir(por_mercado)
    conserva, error = verificar_conservacion(por_mercado, por_departamento)
    if not conserva:
        # No se aborta: el dato sigue siendo útil y el aviso queda en la
        # respuesta. Abortar dejaría la base vacía por un desajuste que puede
        # ser de redondeo.
        log.warning("El reparto por departamento no conserva la energía (error=%.3g)", error)

    insertados, actualizados = guardar_demanda_departamento(db, por_departamento)

    return RespuestaIngestaTerritorio(
        registros_descargados=len(por_departamento),
        registros_insertados=insertados,
        registros_actualizados=actualizados,
        departamentos=int(por_departamento["codigo_dane"].nunique()),
        fecha_inicio=fecha_inicio.isoformat(),
        fecha_fin=fecha_fin.isoformat(),
        conserva_energia=conserva,
        error_relativo=error,
        mensaje=(
            f"{por_mercado['mercado'].nunique()} mercados repartidos en "
            f"{por_departamento['codigo_dane'].nunique()} departamentos"
        ),
    )


# ---------------------------------------------------------------------------
# UPME
# ---------------------------------------------------------------------------


@router.get("/upme/escenarios", response_model=RespuestaUPME, summary="Proyección UPME")
def escenarios_upme(db: SesionBD, _usuario: UsuarioActual) -> RespuestaUPME:
    """Escenarios mensuales de la UPME cruzados con la demanda realmente observada.

    Sirve de contraste del pronóstico a un mes: no es un competidor del modelo
    —la UPME hace planeación de largo plazo, no pronóstico operativo—, pero que
    la proyección propia caiga dentro de su banda alto–bajo es una señal de
    cordura fácil de leer.
    """
    proyecciones = db.execute(select(ProyeccionUPME).order_by(ProyeccionUPME.mes)).scalars().all()
    if not proyecciones:
        return RespuestaUPME(escenarios=[])

    mes = func.date_trunc("month", DatoHistorico.fecha_hora)
    observado = {
        fila.mes: float(fila.total)
        for fila in db.execute(
            select(mes.label("mes"), func.sum(DatoHistorico.demanda_real).label("total"))
            .where(DatoHistorico.demanda_real.isnot(None))
            .group_by(mes)
        ).all()
        if fila.total is not None
    }

    return RespuestaUPME(
        escenarios=[
            EscenarioUPME(
                mes=p.mes,
                escenario_alto=p.escenario_alto,
                escenario_medio=p.escenario_medio,
                escenario_bajo=p.escenario_bajo,
                observado=_buscar_mes(observado, p.mes),
                posicion=_situar(p, _buscar_mes(observado, p.mes)),
            )
            for p in proyecciones
        ]
    )


@router.post(
    "/upme/ingestar",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    summary="Descargar los escenarios de demanda proyectada de la UPME",
    dependencies=[Depends(analista_o_superior)],
)
def ingestar_upme(
    db: SesionBD,
    fecha_inicio: date = Query(...),
    fecha_fin: date | None = Query(None),
) -> dict:
    df = UPMEClient().obtener(fecha_inicio, fecha_fin or date.today())
    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="XM no devolvió los escenarios de la UPME para ese rango",
        )

    insertados, actualizados = guardar_proyeccion_upme(db, df)
    return {
        "meses": len(df),
        "insertados": insertados,
        "actualizados": actualizados,
        "desde": str(df["mes"].min()),
        "hasta": str(df["mes"].max()),
    }


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def _vacio(codigo: str) -> DepartamentoSalida:
    departamento = POR_CODIGO[codigo]
    return DepartamentoSalida(
        codigo_dane=codigo,
        departamento=departamento.nombre,
        interconectado=departamento.interconectado,
    )


def _agregar(db: SesionBD, desde: datetime, hasta: datetime) -> dict[str, dict]:
    """Total, última hora y marcas de trazabilidad por departamento en el rango."""
    filas = db.execute(
        select(
            DemandaDepartamento.codigo_dane,
            func.sum(DemandaDepartamento.demanda_kwh).label("total"),
            func.bool_or(DemandaDepartamento.factor_estimado).label("estimado"),
            func.max(DemandaDepartamento.mercados).label("mercados"),
        )
        .where(DemandaDepartamento.fecha_hora.between(desde, hasta))
        .group_by(DemandaDepartamento.codigo_dane)
    ).all()

    ultimas = {
        fila.codigo_dane: float(fila.demanda_kwh)
        for fila in db.execute(
            select(DemandaDepartamento.codigo_dane, DemandaDepartamento.demanda_kwh).where(
                DemandaDepartamento.fecha_hora == hasta
            )
        ).all()
    }

    return {
        fila.codigo_dane: {
            "total": float(fila.total or 0),
            "ultima": ultimas.get(fila.codigo_dane),
            "estimado": bool(fila.estimado),
            "mercados": fila.mercados,
        }
        for fila in filas
    }


def _media_horaria(db: SesionBD, desde: datetime, hasta: datetime) -> dict[str, float]:
    filas = db.execute(
        select(
            DemandaDepartamento.codigo_dane,
            func.avg(DemandaDepartamento.demanda_kwh).label("media"),
        )
        .where(DemandaDepartamento.fecha_hora.between(desde, hasta))
        .group_by(DemandaDepartamento.codigo_dane)
    ).all()
    return {f.codigo_dane: float(f.media) for f in filas if f.media is not None}


def _hora_pico(db: SesionBD, desde: datetime, hasta: datetime) -> dict[str, int]:
    """Hora del día en la que cada departamento alcanza su demanda media máxima.

    Es un dato con contenido: los departamentos de clima cálido pican al
    mediodía por refrigeración, y los de clima frío por la noche. Verlo en el
    panel del mapa explica diferencias que la cifra total esconde.
    """
    hora = func.extract("hour", DemandaDepartamento.fecha_hora).label("hora")
    filas = db.execute(
        select(
            DemandaDepartamento.codigo_dane,
            hora,
            func.avg(DemandaDepartamento.demanda_kwh).label("media"),
        )
        .where(DemandaDepartamento.fecha_hora.between(desde, hasta))
        .group_by(DemandaDepartamento.codigo_dane, hora)
    ).all()

    mejores: dict[str, tuple[int, float]] = {}
    for fila in filas:
        if fila.media is None:
            continue
        actual = mejores.get(fila.codigo_dane)
        if actual is None or float(fila.media) > actual[1]:
            mejores[fila.codigo_dane] = (int(fila.hora), float(fila.media))

    return {codigo: hora for codigo, (hora, _) in mejores.items()}


def _variacion(actual: float | None, anterior: float | None) -> float | None:
    if not actual or not anterior:
        return None
    return round((actual - anterior) / anterior * 100, 2)


def _buscar_mes(observado: dict, mes: datetime) -> float | None:
    """Busca por (año, mes) y no por igualdad exacta de `datetime`.

    Las proyecciones y los datos históricos pueden venir con zonas horarias
    distintas; comparar los objetos completos fallaría por una diferencia de
    cinco horas y dejaría la columna de observado siempre vacía.
    """
    for clave, valor in observado.items():
        if clave.year == mes.year and clave.month == mes.month:
            return valor
    return None


def _situar(proyeccion: ProyeccionUPME, observado: float | None) -> str | None:
    if observado is None:
        return None
    if proyeccion.escenario_alto and observado > proyeccion.escenario_alto:
        return "sobre_alto"
    if proyeccion.escenario_bajo and observado < proyeccion.escenario_bajo:
        return "bajo_bajo"
    return "en_banda"
