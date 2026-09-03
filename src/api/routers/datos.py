"""Consulta e ingesta de datos históricos del mercado energético."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from src.api.catalogo import CATALOGO, GRUPOS, metadatos
from src.api.deps import SesionBD, UsuarioActual, analista_o_superior
from src.api.schemas.datos import (
    DatoHistoricoSalida,
    PerfilHorario,
    PuntoSerie,
    RespuestaIngesta,
    RespuestaPerfil,
    RespuestaSeries,
    ResumenDatos,
    SerieSalida,
)
from src.core.logging import get_logger
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient
from src.database.models import DatoHistorico
from src.database.persistencia import guardar_datos_historicos
from src.processing.limpieza import limpiar, unir_fuentes

log = get_logger(__name__)

router = APIRouter(prefix="/datos", tags=["Datos históricos"])

LIMITE_MAXIMO = 5000
MAX_SERIES = 6

#: Resoluciones de agregación que admite `GET /datos/series`.
#:
#: Sin agregación, pedir tres años de datos horarios devolvería 26.000 puntos
#: por serie: el navegador los dibuja, pero el usuario no distingue nada y la
#: respuesta pesa megabytes. La agregación se hace en la base de datos, que es
#: donde es barata.
RESOLUCIONES: dict[str, str] = {
    "hora": "hour",
    "dia": "day",
    "semana": "week",
    "mes": "month",
}


@router.get("", response_model=list[DatoHistoricoSalida], summary="Consultar datos históricos")
def listar_datos(
    db: SesionBD,
    _usuario: UsuarioActual,
    fecha_inicio: datetime | None = Query(None, description="Filtro inclusivo"),
    fecha_fin: datetime | None = Query(None, description="Filtro inclusivo"),
    limite: int = Query(500, ge=1, le=LIMITE_MAXIMO),
    desplazamiento: int = Query(0, ge=0, description="Para paginar"),
) -> list[DatoHistorico]:
    """Devuelve los registros horarios, con filtro por rango y paginación.

    Cualquier usuario autenticado puede consultar; el límite superior evita que
    una petición descargue millones de filas y tumbe la API.
    """
    consulta = select(DatoHistorico)

    if fecha_inicio:
        consulta = consulta.where(DatoHistorico.fecha_hora >= fecha_inicio)
    if fecha_fin:
        consulta = consulta.where(DatoHistorico.fecha_hora <= fecha_fin)

    consulta = (
        consulta.order_by(DatoHistorico.fecha_hora.desc())
        .offset(desplazamiento)
        .limit(limite)
    )
    return list(db.execute(consulta).scalars().all())


@router.get("/catalogo", summary="Variables disponibles para graficar")
def catalogo(_usuario: UsuarioActual, db: SesionBD) -> dict:
    """Variables del histórico agrupadas por tema, con su unidad y escala.

    Incluye `disponible`: si esa columna tiene al menos un dato cargado. El
    selector de series del frontend usa ese campo para no ofrecer variables que
    la ingesta actual no trajo.
    """
    pobladas = _columnas_con_datos(db)

    return {
        "grupos": [
            {
                "clave": clave,
                "titulo": titulo,
                "variables": [
                    {
                        "nombre": v.nombre,
                        "etiqueta": v.etiqueta,
                        "unidad": v.unidad,
                        "unidad_vista": v.unidad_vista,
                        "escala": v.escala,
                        "disponible": v.nombre in pobladas,
                    }
                    for v in CATALOGO.values()
                    if v.grupo == clave
                ],
            }
            for clave, titulo in GRUPOS
        ]
    }


@router.get("/resumen", response_model=ResumenDatos, summary="Estadísticos descriptivos")
def resumen(db: SesionBD, _usuario: UsuarioActual) -> ResumenDatos:
    """Agregados globales para alimentar el dashboard del frontend."""
    fila = db.execute(
        select(
            func.count(DatoHistorico.id),
            func.min(DatoHistorico.fecha_hora),
            func.max(DatoHistorico.fecha_hora),
            func.min(DatoHistorico.precio_bolsa),
            func.avg(DatoHistorico.precio_bolsa),
            func.max(DatoHistorico.precio_bolsa),
            func.min(DatoHistorico.demanda_real),
            func.avg(DatoHistorico.demanda_real),
            func.max(DatoHistorico.demanda_real),
        )
    ).one()

    pobladas = _columnas_con_datos(db)

    return ResumenDatos(
        total_registros=fila[0] or 0,
        fecha_minima=fila[1],
        fecha_maxima=fila[2],
        precio_minimo=_float(fila[3]),
        precio_medio=_float(fila[4]),
        precio_maximo=_float(fila[5]),
        demanda_minima=_float(fila[6]),
        demanda_media=_float(fila[7]),
        demanda_maxima=_float(fila[8]),
        variables_con_datos=len(pobladas & set(CATALOGO)),
        variables_totales=len(CATALOGO),
    )


@router.get("/series", response_model=RespuestaSeries, summary="Series para graficar")
def series(
    db: SesionBD,
    _usuario: UsuarioActual,
    variables: list[str] = Query(
        ["precio_bolsa"], description=f"Hasta {MAX_SERIES} nombres del catálogo"
    ),
    desde: datetime | None = Query(None),
    hasta: datetime | None = Query(None),
    resolucion: str = Query("hora", pattern="^(hora|dia|semana|mes)$"),
    limite: int = Query(2000, ge=10, le=20000, description="Puntos máximos por serie"),
) -> RespuestaSeries:
    """Devuelve varias variables alineadas en el mismo eje temporal.

    Es el endpoint que alimenta las gráficas conmutables: en vez de una ruta por
    gráfica, el frontend pide las series que el usuario ha activado.
    """
    desconocidas = [v for v in variables if v not in CATALOGO]
    if desconocidas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Variables desconocidas: {', '.join(desconocidas)}",
        )
    if len(variables) > MAX_SERIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Como máximo {MAX_SERIES} series por petición",
        )

    truncado = func.date_trunc(RESOLUCIONES[resolucion], DatoHistorico.fecha_hora)
    columnas = [func.avg(getattr(DatoHistorico, v)).label(v) for v in variables]

    consulta = select(truncado.label("instante"), *columnas)
    if desde:
        consulta = consulta.where(DatoHistorico.fecha_hora >= desde)
    if hasta:
        consulta = consulta.where(DatoHistorico.fecha_hora <= hasta)

    # `ORDER BY ... DESC LIMIT n` toma los N periodos MÁS RECIENTES; el orden
    # ascendente para dibujar se restablece después en Python. Al revés se
    # devolverían los N más antiguos, que casi nunca es lo que se quiere ver.
    consulta = consulta.group_by(truncado).order_by(truncado.desc()).limit(limite)

    filas = list(db.execute(consulta).all())
    filas.reverse()

    salida = [
        SerieSalida(
            variable=nombre,
            etiqueta=metadatos(nombre).etiqueta,
            unidad=metadatos(nombre).unidad,
            puntos=[
                PuntoSerie(fecha_hora=fila.instante, valor=_float(getattr(fila, nombre)))
                for fila in filas
            ],
        )
        for nombre in variables
    ]

    return RespuestaSeries(
        desde=filas[0].instante if filas else None,
        hasta=filas[-1].instante if filas else None,
        resolucion=resolucion,
        series=salida,
    )


@router.get("/perfil-horario", response_model=RespuestaPerfil, summary="Perfil por hora del día")
def perfil_horario(
    db: SesionBD,
    _usuario: UsuarioActual,
    variable: str = Query("demanda_real"),
    dias: int = Query(90, ge=7, le=1095, description="Ventana hacia atrás"),
) -> RespuestaPerfil:
    """Media de la variable por hora del día, separando laborables de fin de semana.

    Es la vista que revela la curva de carga: el doble pico de la mañana y la
    noche en días laborables, y cómo se aplana el fin de semana. Un gráfico de
    serie temporal no la muestra, porque promedia semanas enteras.
    """
    if variable not in CATALOGO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Variable desconocida: {variable}"
        )

    limite_inferior = _ultimo_instante(db)
    if limite_inferior is None:
        return RespuestaPerfil(variable=variable, unidad=metadatos(variable).unidad, perfil=[])
    limite_inferior -= timedelta(days=dias)

    hora = func.extract("hour", DatoHistorico.fecha_hora)
    # `dow` de PostgreSQL: 0 = domingo, 6 = sábado.
    dia_semana = func.extract("dow", DatoHistorico.fecha_hora)
    es_finde = dia_semana.in_([0, 6])

    filas = db.execute(
        select(hora.label("hora"), es_finde.label("finde"), func.avg(getattr(DatoHistorico, variable)))
        .where(DatoHistorico.fecha_hora >= limite_inferior)
        .group_by(hora, es_finde)
        .order_by(hora)
    ).all()

    por_hora: dict[int, dict[str, float | None]] = {h: {} for h in range(24)}
    for fila in filas:
        clave = "fin_semana" if fila.finde else "laboral"
        por_hora[int(fila.hora)][clave] = _float(fila[2])

    return RespuestaPerfil(
        variable=variable,
        unidad=metadatos(variable).unidad,
        perfil=[
            PerfilHorario(
                hora=h,
                laboral=por_hora[h].get("laboral"),
                fin_semana=por_hora[h].get("fin_semana"),
            )
            for h in range(24)
        ],
    )


@router.post(
    "/ingestar",
    response_model=RespuestaIngesta,
    status_code=status.HTTP_201_CREATED,
    summary="Descargar datos de XM y clima, y guardarlos",
    dependencies=[Depends(analista_o_superior)],
)
def ingestar(
    db: SesionBD,
    fecha_inicio: date = Query(..., description="Formato AAAA-MM-DD"),
    fecha_fin: date | None = Query(None, description="Por defecto, hoy"),
    incluir_tecnologias: bool = Query(
        True, description="Descargar el desglose de generación planta a planta"
    ),
) -> RespuestaIngesta:
    """Ejecuta el pipeline de recolección y persiste el resultado.

    La escritura es **idempotente** (ver `database.persistencia`): reingestar un
    rango ya descargado actualiza los valores en vez de duplicarlos, que es lo
    que hace falta para reintentos y para recoger las correcciones que XM
    publica con retraso.
    """
    fecha_fin = fecha_fin or date.today()
    if fecha_inicio > fecha_fin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="fecha_inicio no puede ser posterior a fecha_fin",
        )
    if (fecha_fin - fecha_inicio) > timedelta(days=1095):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El rango no puede superar 3 años por petición",
        )

    df_xm = XMClient(incluir_tecnologias=incluir_tecnologias).obtener(fecha_inicio, fecha_fin)
    df_clima = ClimaClient().obtener(fecha_inicio, fecha_fin)
    df = limpiar(unir_fuentes(df_xm, df_clima))

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Las fuentes de datos no devolvieron información para ese rango",
        )

    insertados, actualizados = guardar_datos_historicos(db, df)
    pobladas = sorted(c for c in df.columns if c in CATALOGO and df[c].notna().any())

    return RespuestaIngesta(
        registros_descargados=len(df),
        registros_insertados=insertados,
        registros_actualizados=actualizados,
        fecha_inicio=fecha_inicio.isoformat(),
        fecha_fin=fecha_fin.isoformat(),
        mensaje=(
            f"Ingesta completada desde '{df['fuente'].iloc[0]}' "
            f"con {len(pobladas)} variables pobladas"
        ),
        variables_pobladas=pobladas,
    )


# ---------------------------------------------------------------------------


def _float(valor) -> float | None:
    return float(valor) if valor is not None else None


def _ultimo_instante(db: SesionBD) -> datetime | None:
    return db.execute(select(func.max(DatoHistorico.fecha_hora))).scalar_one_or_none()


def _columnas_con_datos(db: SesionBD) -> set[str]:
    """Qué columnas del catálogo tienen al menos un valor.

    Se resuelve con un único `SELECT count(col)` por columna dentro de la misma
    consulta: una pasada por la tabla en vez de una por variable.
    """
    columnas = [c for c in CATALOGO if hasattr(DatoHistorico, c)]
    if not columnas:
        return set()

    fila = db.execute(
        select(*[func.count(getattr(DatoHistorico, c)).label(c) for c in columnas])
    ).one()
    return {nombre for nombre, total in zip(columnas, fila, strict=True) if total}


def _cargar_historico(db: SesionBD) -> pd.DataFrame:
    """Vuelca `datos_historicos` a un `DataFrame`. Compartido por varios routers."""
    filas = db.execute(
        select(DatoHistorico).order_by(DatoHistorico.fecha_hora)
    ).scalars().all()

    if not filas:
        return pd.DataFrame()

    columnas = [c.name for c in DatoHistorico.__table__.columns if c.name != "creado_en"]
    return pd.DataFrame([{c: getattr(f, c) for c in columnas} for f in filas])
