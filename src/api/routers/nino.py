"""Fenómeno del Niño: estado ENSO, anomalía térmica por departamento y su efecto.

Lo que esta sección tiene que contar
------------------------------------

La intuición dice: El Niño calienta, el calor sube el consumo, y más consumo sube
el precio. Los datos del propio proyecto dicen otra cosa. Agrupando las 32.232
horas de `datos_historicos` por fase ENSO:

===========  =======  ==================  =================
Fase          Horas   Precio (COP/kWh)    Demanda (kWh)
===========  =======  ==================  =================
El Niño       10.704             660,1          9.511.846
Neutro        18.576             418,8          9.405.986
La Niña        2.952             259,5          9.444.726
===========  =======  ==================  =================

Con El Niño la energía cuesta un **58 % más** que en condiciones normales y
**2,5 veces** lo que cuesta con La Niña. La demanda, en cambio, se mueve un 1 %.
El fenómeno no golpea el consumo, golpea lo que cuesta producirlo: sin agua en
los embalses entra la generación térmica, que es cara. Por eso el endpoint
devuelve las dos variaciones juntas y no solo la del precio: la del consumo,
casi plana, es la mitad interesante del hallazgo.

Y por eso devuelve también `evidencia`. La Niña son 123 días —cuatro meses
seguidos—, así que su media es también la media de esos cuatro meses concretos,
con su estacionalidad: no se puede separar una cosa de la otra, y quien lea la
cifra tiene que saberlo sin ir a buscar la nota al pie.

Estas cifras salieron mal hasta que se reparó `fenomeno_climatico`: 1.200 horas
con un ONI de 1,39 estaban etiquetadas como neutras y entraban en la media
equivocada. Ver `scripts/reparar_fenomeno.py`.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from fastapi import APIRouter, Query
from sqlalchemy import Integer, func, select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.nino import (
    DepartamentoNino,
    EfectoFase,
    PuntoOni,
    RespuestaEfecto,
    RespuestaEstado,
    RespuestaMapa,
)
from src.core.logging import get_logger
from src.data_collection.clima_departamentos import aplicar_anomalia
from src.data_collection.departamentos import DEPARTAMENTOS
from src.database.models import ClimaDepartamento, DatoHistorico, DemandaDepartamento

log = get_logger(__name__)

router = APIRouter(prefix="/nino", tags=["Fenómeno del Niño"])

#: Un año de horas. Por debajo, la media de una fase no se puede separar de la
#: época del año en que le tocó caer: La Niña son cuatro meses seguidos, así que
#: su media es también la media de esos cuatro meses concretos, con su clima y su
#: estacionalidad de demanda. Un umbral más laxo —treinta días, por ejemplo— la
#: daría por sólida y estaría escondiendo justo ese problema.
HORAS_EVIDENCIA_SOLIDA = 8760

FASE_NEUTRA = "NEUTRO"

#: Criterio de la NOAA sobre el valor absoluto del ONI.
UMBRALES_INTENSIDAD: tuple[tuple[float, str], ...] = (
    (2.0, "muy fuerte"),
    (1.5, "fuerte"),
    (1.0, "moderado"),
    (0.5, "débil"),
)

MESES_SERIE_ONI = 36


@router.get("/estado", response_model=RespuestaEstado, summary="Situación ENSO actual")
def estado(db: SesionBD, _usuario: UsuarioActual) -> RespuestaEstado:
    ultimo = db.execute(
        select(DatoHistorico.fecha_hora, DatoHistorico.indice_oni, DatoHistorico.fenomeno_climatico)
        .where(DatoHistorico.indice_oni.is_not(None))
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).first()

    if ultimo is None:
        return RespuestaEstado()

    fecha, oni, fase = ultimo

    desde = fecha - timedelta(days=30 * MESES_SERIE_ONI)
    mes = func.strftime("%Y-%m", DatoHistorico.fecha_hora)
    if db.get_bind().dialect.name == "postgresql":
        mes = func.to_char(DatoHistorico.fecha_hora, "YYYY-MM")

    filas = db.execute(
        select(mes.label("mes"), func.avg(DatoHistorico.indice_oni))
        .where(DatoHistorico.indice_oni.is_not(None), DatoHistorico.fecha_hora >= desde)
        .group_by(mes)
        .order_by(mes)
    ).all()

    return RespuestaEstado(
        fase=fase,
        oni=round(float(oni), 2),
        intensidad=_intensidad(float(oni)),
        actualizado_en=fecha,
        serie=[
            PuntoOni(mes=m, oni=round(float(v), 2), fase=_fase_de(float(v))) for m, v in filas
        ],
    )


@router.get("/mapa", response_model=RespuestaMapa, summary="Anomalía térmica por departamento")
def mapa(
    db: SesionBD,
    _usuario: UsuarioActual,
    horas: int = Query(24, ge=1, le=720, description="Ventana a promediar"),
) -> RespuestaMapa:
    instante = db.execute(select(func.max(ClimaDepartamento.fecha_hora))).scalar_one_or_none()
    if instante is None:
        return RespuestaMapa(horas_agregadas=horas)

    desde = pd.Timestamp(instante) - pd.Timedelta(hours=horas)

    # Las normales se agregan en la base, no trayéndose la tabla entera: son más
    # de un millón de filas y la primera versión de este endpoint tardaba 15
    # segundos en responder por hacerlo así. La resta sigue viviendo en un solo
    # sitio (`aplicar_anomalia`); lo único que cambia es quién calcula la media.
    normales = pd.DataFrame(
        db.execute(
            select(
                ClimaDepartamento.codigo_dane,
                _mes_de(db, ClimaDepartamento.fecha_hora).label("_mes"),
                func.avg(ClimaDepartamento.temperatura),
            )
            .where(ClimaDepartamento.temperatura.is_not(None))
            .group_by(ClimaDepartamento.codigo_dane, _mes_de(db, ClimaDepartamento.fecha_hora))
        ).all(),
        columns=["codigo_dane", "_mes", "media_mensual"],
    )
    if normales.empty:
        return RespuestaMapa(instante=instante, horas_agregadas=horas)

    normales["_mes"] = normales["_mes"].astype(int)

    # Solo la ventana pedida: para 24 h son 33 departamentos × 24 horas.
    reciente = pd.DataFrame(
        db.execute(
            select(
                ClimaDepartamento.fecha_hora,
                ClimaDepartamento.codigo_dane,
                ClimaDepartamento.temperatura,
            ).where(
                ClimaDepartamento.temperatura.is_not(None),
                ClimaDepartamento.fecha_hora > desde.to_pydatetime(),
            )
        ).all(),
        columns=["fecha_hora", "codigo_dane", "temperatura"],
    )
    if reciente.empty:
        return RespuestaMapa(instante=instante, horas_agregadas=horas)

    resumen = aplicar_anomalia(reciente, normales).groupby("codigo_dane")[
        ["temperatura", "media_mensual", "anomalia"]
    ].mean()

    demanda = dict(
        db.execute(
            select(DemandaDepartamento.codigo_dane, func.sum(DemandaDepartamento.demanda_kwh))
            .where(DemandaDepartamento.fecha_hora > desde.to_pydatetime())
            .group_by(DemandaDepartamento.codigo_dane)
        ).all()
    )

    departamentos = []
    for d in DEPARTAMENTOS:
        fila = resumen.loc[d.codigo] if d.codigo in resumen.index else None
        departamentos.append(
            DepartamentoNino(
                codigo_dane=d.codigo,
                departamento=d.nombre,
                interconectado=d.interconectado,
                temperatura=_redondear(fila, "temperatura"),
                media_mensual=_redondear(fila, "media_mensual"),
                anomalia=_redondear(fila, "anomalia"),
                demanda_kwh=demanda.get(d.codigo),
            )
        )

    anomalias = [abs(d.anomalia) for d in departamentos if d.anomalia is not None]

    return RespuestaMapa(
        instante=instante,
        horas_agregadas=horas,
        departamentos=departamentos,
        # Extremo simétrico: la leyenda divergente tiene que abarcar lo mismo a
        # ambos lados del cero, o un medio grado de más se pintaría igual que
        # tres y el mapa exageraría.
        anomalia_maxima=round(max(anomalias), 2) if anomalias else 0.0,
    )


@router.get(
    "/efecto",
    response_model=RespuestaEfecto,
    summary="Precio y demanda medios bajo cada fase ENSO",
)
def efecto(db: SesionBD, _usuario: UsuarioActual) -> RespuestaEfecto:
    filas = db.execute(
        select(
            DatoHistorico.fenomeno_climatico,
            func.count().label("horas"),
            func.avg(DatoHistorico.precio_bolsa),
            func.avg(DatoHistorico.demanda_real),
            func.avg(DatoHistorico.temperatura),
        )
        .where(DatoHistorico.fenomeno_climatico.is_not(None))
        .group_by(DatoHistorico.fenomeno_climatico)
    ).all()

    if not filas:
        return RespuestaEfecto(horas_para_evidencia_solida=HORAS_EVIDENCIA_SOLIDA)

    fases = {
        fase: EfectoFase(
            fase=fase,
            horas=horas,
            precio=_redondeo(precio, 1),
            demanda=_redondeo(demanda, 0),
            temperatura=_redondeo(temperatura, 2),
            evidencia="solida" if horas >= HORAS_EVIDENCIA_SOLIDA else "debil",
        )
        for fase, horas, precio, demanda, temperatura in filas
    }

    referencia = fases.get(FASE_NEUTRA)
    if referencia is not None:
        for fase, dato in fases.items():
            if fase == FASE_NEUTRA:
                continue
            dato.variacion_precio = _variacion(dato.precio, referencia.precio)
            dato.variacion_demanda = _variacion(dato.demanda, referencia.demanda)

    # Orden fijo y no el que devuelva la base: la interfaz los pinta en fila y
    # que bailen entre consultas hace ilegible la comparación.
    orden = ("EL_NINO", FASE_NEUTRA, "LA_NINA")
    ordenadas = [fases[f] for f in orden if f in fases]
    ordenadas += [d for f, d in fases.items() if f not in orden]

    return RespuestaEfecto(fases=ordenadas, horas_para_evidencia_solida=HORAS_EVIDENCIA_SOLIDA)


# ---------------------------------------------------------------------------


def _mes_de(db: SesionBD, columna):
    """Mes del año de una columna temporal, en el dialecto que toque.

    SQLite no tiene `EXTRACT`, y las pruebas corren sobre SQLite. Sin esta
    bifurcación el endpoint funcionaría en producción y reventaría en las
    pruebas, que es donde menos sirve descubrirlo.
    """
    if db.get_bind().dialect.name == "postgresql":
        return func.extract("month", columna)
    return func.cast(func.strftime("%m", columna), Integer)


def _intensidad(oni: float) -> str:
    magnitud = abs(oni)
    for umbral, etiqueta in UMBRALES_INTENSIDAD:
        if magnitud >= umbral:
            return etiqueta
    return "neutro"


def _fase_de(oni: float) -> str:
    if oni >= 0.5:
        return "EL_NINO"
    if oni <= -0.5:
        return "LA_NINA"
    return FASE_NEUTRA


def _redondear(fila, columna: str) -> float | None:
    if fila is None or pd.isna(fila[columna]):
        return None
    return round(float(fila[columna]), 2)


def _redondeo(valor, decimales: int) -> float | None:
    return None if valor is None else round(float(valor), decimales)


def _variacion(valor: float | None, referencia: float | None) -> float | None:
    if valor is None or not referencia:
        return None
    return round((valor - referencia) / referencia * 100, 2)
