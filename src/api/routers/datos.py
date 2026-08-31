"""Consulta e ingesta de datos históricos del mercado energético."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.api.deps import SesionBD, UsuarioActual, analista_o_superior
from src.api.schemas.datos import DatoHistoricoSalida, RespuestaIngesta, ResumenDatos
from src.core.logging import get_logger
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient
from src.database.models import DatoHistorico
from src.processing.limpieza import limpiar, unir_fuentes

log = get_logger(__name__)

router = APIRouter(prefix="/datos", tags=["Datos históricos"])

LIMITE_MAXIMO = 5000


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
        )
    ).one()

    return ResumenDatos(
        total_registros=fila[0] or 0,
        fecha_minima=fila[1],
        fecha_maxima=fila[2],
        precio_minimo=float(fila[3]) if fila[3] is not None else None,
        precio_medio=float(fila[4]) if fila[4] is not None else None,
        precio_maximo=float(fila[5]) if fila[5] is not None else None,
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
) -> RespuestaIngesta:
    """Ejecuta el pipeline de recolección y persiste el resultado.

    La inserción usa `ON CONFLICT DO UPDATE` sobre `fecha_hora`: reingestar un
    rango ya descargado actualiza los valores en vez de fallar por clave
    duplicada. Esto hace la operación **idempotente**, que es lo que se necesita
    para reejecuciones y para corregir datos que XM publica con retraso.
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

    df_xm = XMClient().obtener(fecha_inicio, fecha_fin)
    df_clima = ClimaClient().obtener(fecha_inicio, fecha_fin)
    df = limpiar(unir_fuentes(df_xm, df_clima))

    if df.empty:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Las fuentes de datos no devolvieron información para ese rango",
        )

    insertados, actualizados = _guardar(db, df)

    return RespuestaIngesta(
        registros_descargados=len(df),
        registros_insertados=insertados,
        registros_actualizados=actualizados,
        fecha_inicio=fecha_inicio.isoformat(),
        fecha_fin=fecha_fin.isoformat(),
        mensaje=f"Ingesta completada desde la fuente '{df.get('fuente', ['?'])[0]}'",
    )


# ---------------------------------------------------------------------------


def _guardar(db: SesionBD, df) -> tuple[int, int]:
    """Inserta o actualiza los registros. Devuelve (insertados, actualizados)."""
    columnas_modelo = {c.name for c in DatoHistorico.__table__.columns}
    columnas = [c for c in df.columns if c in columnas_modelo]

    existentes_antes = db.execute(select(func.count(DatoHistorico.id))).scalar_one()

    registros = (
        df[columnas]
        .assign(fecha_hora=df["fecha_hora"].dt.to_pydatetime())
        .where(df[columnas].notna(), None)
        .to_dict(orient="records")
    )

    # `to_dict` puede dejar NaN de numpy; los normalizamos a None.
    for registro in registros:
        for clave, valor in registro.items():
            if valor is not None and isinstance(valor, float) and valor != valor:  # NaN
                registro[clave] = None

    dialecto = db.get_bind().dialect.name
    lote = 1000

    for inicio in range(0, len(registros), lote):
        trozo = registros[inicio : inicio + lote]
        if dialecto == "postgresql":
            sentencia = pg_insert(DatoHistorico).values(trozo)
            actualizables = {
                c: sentencia.excluded[c] for c in columnas if c not in {"id", "fecha_hora"}
            }
            sentencia = sentencia.on_conflict_do_update(
                index_elements=["fecha_hora"], set_=actualizables
            )
            db.execute(sentencia)
        else:
            # SQLite (pruebas): merge fila a fila.
            for registro in trozo:
                existente = db.execute(
                    select(DatoHistorico).where(
                        DatoHistorico.fecha_hora == registro["fecha_hora"]
                    )
                ).scalar_one_or_none()
                if existente:
                    for clave, valor in registro.items():
                        setattr(existente, clave, valor)
                else:
                    db.add(DatoHistorico(**registro))

    db.commit()

    existentes_despues = db.execute(select(func.count(DatoHistorico.id))).scalar_one()
    insertados = existentes_despues - existentes_antes
    return insertados, len(registros) - insertados
