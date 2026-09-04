"""Vista de usuario: el estado del sistema resuelto en una sola llamada.

El tablero técnico reparte la información en cuatro secciones y deja que el
usuario la componga. Esta vista hace lo contrario: responde en un solo viaje a
las tres preguntas que tiene alguien que no trabaja en el sector —cómo está el
precio ahora, hacia dónde va, y por qué— y lo hace en lenguaje llano.

Todo lo que aquí se calcula sale de datos ya guardados: nada dispara un
entrenamiento ni una descarga. Si falta el pronóstico de algún horizonte se
devuelve marcado como no disponible, en vez de bloquear la pantalla mientras se
carga un modelo de cientos de megabytes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.panorama import (
    DepartamentoResumen,
    Embalses,
    Indicador,
    Panorama,
    ParteMezcla,
    ResumenPronostico,
)
from src.core.logging import get_logger
from src.database.models import DatoHistorico, DemandaDepartamento, Prediccion
from src.models.entrenamiento import HORIZONTES, artefactos_disponibles

log = get_logger(__name__)

router = APIRouter(tags=["Panorama"])

#: Tecnologías de generación que se muestran, en orden fijo.
#:
#: Eólica y cogeneración van juntas en "Otras fuentes": entre las dos no llegan
#: al 3 % del sistema, y darles franja propia gastaría dos colores de la paleta
#: —que está validada para cuatro categorías distinguibles— en segmentos que a
#: escala real no se ven.
TECNOLOGIAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("generacion_hidraulica", ("generacion_hidraulica",)),
    ("generacion_termica", ("generacion_termica",)),
    ("generacion_solar", ("generacion_solar",)),
    ("generacion_otras", ("generacion_eolica", "generacion_cogeneracion")),
)

ETIQUETAS_TECNOLOGIA: dict[str, str] = {
    "generacion_hidraulica": "Hidráulica",
    "generacion_termica": "Térmica",
    "generacion_solar": "Solar",
    "generacion_otras": "Eólica y cogeneración",
}

#: Cortes del nivel de embalse. No son arbitrarios: por debajo del 30 % el
#: sistema colombiano entra en la zona donde se activa el precio de escasez, y
#: por encima del 70 % la generación térmica apenas participa.
CORTES_EMBALSE: tuple[tuple[float, str, str], ...] = (
    (70, "holgado", "Los embalses están llenos. El sistema genera con agua, que es lo barato."),
    (50, "normal", "Los embalses están en un nivel habitual para la época."),
    (30, "ajustado", "Los embalses van bajos: entra más generación térmica y el precio sube."),
    (0, "critico", "Los embalses están muy bajos. El sistema opera cerca del precio de escasez."),
)

#: Umbral por debajo del cual una variación se considera ruido y no tendencia.
UMBRAL_ESTABLE = 2.0


@router.get("/panorama", response_model=Panorama, summary="Estado del sistema para la vista de usuario")
def panorama(
    db: SesionBD,
    _usuario: UsuarioActual,
    objetivo: str = Query("precio_bolsa", pattern="^(precio_bolsa|demanda_real)$"),
) -> Panorama:
    """Resumen del sistema, ya interpretado."""
    ultimo = db.execute(
        select(DatoHistorico)
        .where(DatoHistorico.precio_bolsa.isnot(None))
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).scalar_one_or_none()

    if ultimo is None:
        return Panorama(titular="Todavía no hay datos cargados.")

    instante = ultimo.fecha_hora
    precio = _indicador(db, "precio_bolsa", instante, "COP/kWh")
    demanda = _indicador(db, "demanda_real", instante, "kWh")
    embalses = _embalses(db, instante)
    mezcla = _mezcla(db, instante)
    pronosticos = _pronosticos(db, objetivo, instante)
    departamentos = _departamentos(db)

    principal = next((p for p in pronosticos if p.horizonte == 24 and p.disponible), None)

    return Panorama(
        instante=instante,
        titular=_titular(objetivo, precio, demanda, principal),
        detalle=_detalle(embalses, mezcla),
        precio=precio,
        demanda=demanda,
        embalses=embalses,
        mezcla=mezcla,
        pronosticos=pronosticos,
        departamentos=departamentos,
    )


# ---------------------------------------------------------------------------
# Bloques
# ---------------------------------------------------------------------------


def _indicador(db: SesionBD, columna: str, instante: datetime, unidad: str) -> Indicador:
    """Valor más reciente de la variable, con su media semanal y su variación.

    **Cada métrica tiene su propio "ahora".** XM publica el precio de bolsa casi
    en tiempo real y la demanda con un par de días de retraso, así que leer las
    dos en la misma marca temporal devolvería una demanda a medias. Aquí se
    busca la última hora en la que *esa* columna tiene dato y todo lo demás se
    calcula respecto de ella.

    La comparación es contra **la misma hora del día anterior**, no contra la
    hora anterior: la demanda de las 3 de la mañana siempre es menor que la de
    medianoche, y comparar horas contiguas produciría un "baja un 20 %" que solo
    describe el ciclo diario.
    """
    campo = getattr(DatoHistorico, columna)

    fila = db.execute(
        select(DatoHistorico.fecha_hora, campo)
        .where(campo.isnot(None), DatoHistorico.fecha_hora <= instante)
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).one_or_none()

    if fila is None:
        return Indicador(unidad=unidad)

    momento, actual = fila

    ayer = db.execute(
        select(campo).where(DatoHistorico.fecha_hora == momento - timedelta(hours=24))
    ).scalar_one_or_none()

    media = db.execute(
        select(func.avg(campo)).where(
            DatoHistorico.fecha_hora > momento - timedelta(days=7),
            DatoHistorico.fecha_hora <= momento,
        )
    ).scalar_one_or_none()

    return Indicador(
        valor=_float(actual),
        unidad=unidad,
        variacion_24h=_variacion(actual, ayer),
        media_7d=_float(media),
        instante=momento,
    )


def _embalses(db: SesionBD, instante: datetime) -> Embalses:
    nivel = db.execute(
        select(DatoHistorico.volumen_util_embalse)
        .where(
            DatoHistorico.volumen_util_embalse.isnot(None),
            DatoHistorico.fecha_hora <= instante,
        )
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).scalar_one_or_none()

    if nivel is None:
        return Embalses(descripcion="No hay dato de embalses en el histórico cargado.")

    hace_una_semana = db.execute(
        select(DatoHistorico.volumen_util_embalse)
        .where(
            DatoHistorico.volumen_util_embalse.isnot(None),
            DatoHistorico.fecha_hora <= instante - timedelta(days=7),
        )
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).scalar_one_or_none()

    estado, descripcion = next(
        (estado, texto) for corte, estado, texto in CORTES_EMBALSE if nivel >= corte
    )

    return Embalses(
        nivel=round(float(nivel), 1),
        # Diferencia en puntos porcentuales, no variación relativa: pasar del
        # 60 % al 57 % es "tres puntos menos", no "un 5 % menos", y así es como
        # se habla del nivel de un embalse.
        variacion_7d=(
            round(float(nivel) - float(hace_una_semana), 1) if hace_una_semana else None
        ),
        estado=estado,
        descripcion=descripcion,
    )


def _mezcla(db: SesionBD, instante: datetime) -> list[ParteMezcla]:
    """Reparto de la generación por tecnología en las últimas 24 horas."""
    origenes = sorted({c for _, columnas in TECNOLOGIAS for c in columnas})
    fila = db.execute(
        select(*[func.sum(getattr(DatoHistorico, c)).label(c) for c in origenes]).where(
            DatoHistorico.fecha_hora > instante - timedelta(hours=24),
            DatoHistorico.fecha_hora <= instante,
        )
    ).one()

    crudo = {
        columna: (float(valor) if valor is not None else 0.0)
        for columna, valor in zip(origenes, fila, strict=True)
    }

    agrupado = {
        clave: sum(crudo.get(c, 0.0) for c in columnas) for clave, columnas in TECNOLOGIAS
    }
    total = sum(agrupado.values())
    if total <= 0:
        return []

    partes = [
        ParteMezcla(
            clave=clave,
            etiqueta=ETIQUETAS_TECNOLOGIA[clave],
            porcentaje=round(valor / total * 100, 1),
        )
        for clave, valor in agrupado.items()
        if valor > 0
    ]
    return sorted(partes, key=lambda p: -p.porcentaje)


def _pronosticos(db: SesionBD, objetivo: str, instante: datetime) -> list[ResumenPronostico]:
    """Último pronóstico guardado de cada horizonte, sin recalcular nada."""
    unidad = "COP/kWh" if objetivo == "precio_bolsa" else "kWh"

    # El valor de referencia es el último dato real del objetivo, que puede ser
    # anterior al instante general: la demanda llega con retraso y compararla
    # con un precio de hoy daría una variación inventada.
    referencia = db.execute(
        select(getattr(DatoHistorico, objetivo))
        .where(
            getattr(DatoHistorico, objetivo).isnot(None),
            DatoHistorico.fecha_hora <= instante,
        )
        .order_by(DatoHistorico.fecha_hora.desc())
        .limit(1)
    ).scalar_one_or_none()

    entrenados = {
        (a.objetivo, a.horizonte) for a in artefactos_disponibles()
    }

    resumenes: list[ResumenPronostico] = []

    for etiqueta, horas in HORIZONTES.items():
        hay_modelo = (objetivo, horas) in entrenados
        ultimo = db.execute(
            select(Prediccion)
            .where(
                Prediccion.objetivo == objetivo,
                Prediccion.horizonte_horas == horas,
                Prediccion.fecha_objetivo > instante,
            )
            .order_by(Prediccion.fecha_objetivo.desc())
            .limit(1)
        ).scalar_one_or_none()

        if ultimo is None:
            resumenes.append(
                ResumenPronostico(
                    horizonte=horas,
                    etiqueta=etiqueta,
                    unidad=unidad,
                    disponible=False,
                    hay_modelo=hay_modelo,
                )
            )
            continue

        variacion = _variacion(ultimo.valor_estimado, referencia)
        resumenes.append(
            ResumenPronostico(
                horizonte=horas,
                etiqueta=etiqueta,
                valor_final=round(float(ultimo.valor_estimado), 2),
                unidad=ultimo.unidad or unidad,
                variacion=variacion,
                tendencia=_tendencia(variacion),
                limite_inferior=_float(ultimo.limite_inferior),
                limite_superior=_float(ultimo.limite_superior),
                nombre_modelo=ultimo.nombre_modelo,
                error_tipico=_error_tipico(ultimo),
                disponible=True,
                hay_modelo=hay_modelo,
            )
        )

    return resumenes


def _departamentos(db: SesionBD, cuantos: int = 6) -> list[DepartamentoResumen]:
    """Los departamentos que más consumen en las últimas 24 horas."""
    ultimo = db.execute(select(func.max(DemandaDepartamento.fecha_hora))).scalar_one_or_none()
    if ultimo is None:
        return []

    filas = db.execute(
        select(
            DemandaDepartamento.codigo_dane,
            func.max(DemandaDepartamento.departamento).label("nombre"),
            func.sum(DemandaDepartamento.demanda_kwh).label("total"),
            func.bool_or(DemandaDepartamento.factor_estimado).label("estimado"),
        )
        .where(DemandaDepartamento.fecha_hora > ultimo - timedelta(hours=24))
        .group_by(DemandaDepartamento.codigo_dane)
        .order_by(func.sum(DemandaDepartamento.demanda_kwh).desc())
    ).all()

    total_nacional = sum(float(f.total) for f in filas) or None

    return [
        DepartamentoResumen(
            codigo_dane=f.codigo_dane,
            departamento=f.nombre,
            demanda_24h=float(f.total),
            participacion=(
                round(float(f.total) / total_nacional * 100, 1) if total_nacional else None
            ),
            estimado=bool(f.estimado),
        )
        for f in filas[:cuantos]
    ]


# ---------------------------------------------------------------------------
# Redacción
# ---------------------------------------------------------------------------


def _titular(
    objetivo: str,
    precio: Indicador,
    demanda: Indicador,
    pronostico: ResumenPronostico | None,
) -> str:
    """Una frase que responde a "¿cómo está esto?" sin usar jerga.

    Se redacta aquí y no en la interfaz porque depende de los datos, y porque
    así la misma frase vale para cualquier cliente que consuma la API.
    """
    nombre = "El precio de la energía" if objetivo == "precio_bolsa" else "La demanda de energía"
    indicador = precio if objetivo == "precio_bolsa" else demanda

    if indicador.valor is None:
        return f"{nombre} no tiene dato reciente."

    if pronostico is None or not pronostico.disponible or pronostico.variacion is None:
        movimiento = _movimiento(indicador.variacion_24h)
        return f"{nombre} {movimiento} respecto a ayer a esta misma hora."

    cambio = abs(pronostico.variacion)
    if pronostico.tendencia == "estable":
        return f"{nombre} se mantendrá estable durante las próximas 24 horas."
    direccion = "subirá" if pronostico.tendencia == "sube" else "bajará"
    return f"{nombre} {direccion} alrededor de un {cambio:.0f} % en las próximas 24 horas."


def _movimiento(variacion: float | None) -> str:
    if variacion is None:
        return "no ha cambiado de forma apreciable"
    if abs(variacion) < UMBRAL_ESTABLE:
        return "se mantiene estable"
    return f"{'subió' if variacion > 0 else 'bajó'} un {abs(variacion):.0f} %"


def _detalle(embalses: Embalses, mezcla: list[ParteMezcla]) -> str:
    """La explicación de por qué: hidrología y mezcla de generación."""
    if not mezcla:
        return embalses.descripcion

    principal = mezcla[0]
    frase = (
        f"En las últimas 24 horas, el {principal.porcentaje:.0f} % de la energía "
        f"del país vino de generación {principal.etiqueta.lower()}."
    )
    return f"{embalses.descripcion} {frase}" if embalses.descripcion else frase


def _tendencia(variacion: float | None) -> str:
    if variacion is None or abs(variacion) < UMBRAL_ESTABLE:
        return "estable"
    return "sube" if variacion > 0 else "baja"


def _error_tipico(prediccion: Prediccion) -> float | None:
    """Semiancho de la banda: el "más o menos" del pronóstico, en su unidad."""
    if prediccion.limite_inferior is None or prediccion.limite_superior is None:
        return None
    return round((prediccion.limite_superior - prediccion.limite_inferior) / 2, 2)


def _variacion(actual, referencia) -> float | None:
    if actual is None or not referencia:
        return None
    return round((float(actual) - float(referencia)) / abs(float(referencia)) * 100, 2)


def _float(valor) -> float | None:
    return float(valor) if valor is not None else None
