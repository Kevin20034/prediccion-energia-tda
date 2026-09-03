"""Entrenamiento de modelos y comparación consolidada."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from src.api.deps import SesionBD, UsuarioActual, analista_o_superior
from src.api.routers.datos import _cargar_historico
from src.api.schemas.prediccion import (
    EjecucionSalida,
    FilaComparacion,
    GanadorHorizonte,
    MetricasSalida,
    RespuestaComparacion,
    RespuestaEntrenamiento,
    ResultadoModeloSalida,
    SolicitudEntrenamiento,
)
from src.core.logging import get_logger
from src.database.models import EjecucionEntrenamiento
from src.models import FAMILIAS
from src.models.baseline import ModeloBaselineEstacional
from src.models.entrenamiento import HORIZONTES, entrenar_todos

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
    según el volumen y los modelos elegidos). Para producción, lo correcto sería
    encolarla en un *worker* y exponer un endpoint de estado; se deja síncrona a
    propósito para que la demostración del trabajo de grado sea directa y el
    resultado se vea en la misma respuesta.
    """
    df = _cargar_historico(db)

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
            objetivo=solicitud.objetivo,
            horizonte=solicitud.horizonte,
            proporcion_test=solicitud.proporcion_test,
            criterio=solicitud.criterio,
            pliegues_validacion=solicitud.pliegues_validacion,
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
        objetivo=resultado.objetivo,
        horizonte=resultado.horizonte,
        criterio=resultado.criterio,
        n_muestras_entrenamiento=resultado.n_train,
        n_muestras_prueba=resultado.n_test,
        resultados=[
            ResultadoModeloSalida(
                nombre=r.nombre,
                familia=r.familia,
                metricas=MetricasSalida(**r.metricas.as_dict()) if r.metricas else None,
                duracion_segundos=round(r.duracion_segundos, 2),
                es_mejor=r is resultado.mejor,
                error=r.error,
                rmse_validacion=r.rmse_validacion,
                desviacion_validacion=r.desviacion_validacion,
                importancia=r.importancia,
            )
            for r in resultado.resultados
        ],
    )


@router.get(
    "/entrenamientos",
    response_model=list[EjecucionSalida],
    summary="Histórico de entrenamientos",
)
def historico(
    db: SesionBD,
    _usuario: UsuarioActual,
    objetivo: str | None = Query(None),
    horizonte: int | None = Query(None, ge=1, le=720),
    limite: int = Query(50, ge=1, le=500),
    solo_mejores: bool = Query(False),
) -> list[EjecucionEntrenamiento]:
    """Trazabilidad: qué se entrenó, cuándo y con qué error."""
    consulta = select(EjecucionEntrenamiento)
    if objetivo:
        consulta = consulta.where(EjecucionEntrenamiento.objetivo == objetivo)
    if horizonte:
        consulta = consulta.where(EjecucionEntrenamiento.horizonte_horas == horizonte)
    if solo_mejores:
        consulta = consulta.where(EjecucionEntrenamiento.es_mejor.is_(True))
    consulta = consulta.order_by(EjecucionEntrenamiento.ejecutado_en.desc()).limit(limite)
    return list(db.execute(consulta).scalars().all())


@router.get(
    "/modelos/comparacion",
    response_model=RespuestaComparacion,
    summary="Qué modelo gana en cada horizonte, y por qué",
)
def comparacion(
    db: SesionBD,
    _usuario: UsuarioActual,
    objetivo: str | None = Query(None, description="Filtra por objetivo"),
) -> RespuestaComparacion:
    """Consolida el **último lote** de entrenamiento de cada objetivo y horizonte.

    Un mismo modelo se entrena muchas veces mientras se ajusta el proyecto, y la
    comparación solo tiene sentido entre modelos entrenados en las mismas
    condiciones. Por eso se toma el lote completo más reciente de cada
    combinación y no "la fila más reciente de cada modelo": si en la última
    ejecución un modelo divergió y no dejó fila, con el segundo criterio seguiría
    apareciendo con las métricas de una ejecución anterior —sobre otros datos— y
    la tabla mentiría sin que nada lo delatara.
    """
    consulta = select(EjecucionEntrenamiento).order_by(
        EjecucionEntrenamiento.ejecutado_en.desc()
    )
    if objetivo:
        consulta = consulta.where(EjecucionEntrenamiento.objetivo == objetivo)

    ejecuciones = list(db.execute(consulta).scalars().all())
    if not ejecuciones:
        return RespuestaComparacion(
            filas=[],
            ganadores=[],
            recomendacion="Todavía no hay entrenamientos registrados.",
        )

    ultimas = _ultimo_lote(ejecuciones)
    referencias = _rmse_baseline(ultimas.values())

    filas = [
        FilaComparacion(
            nombre_modelo=e.nombre_modelo,
            familia=FAMILIAS.get(e.nombre_modelo, "otro"),
            objetivo=e.objetivo,
            horizonte_horas=e.horizonte_horas,
            mae=e.mae,
            rmse=e.rmse,
            mape=e.mape,
            smape=e.smape,
            mase=e.mase,
            r2=e.r2,
            duracion_segundos=e.duracion_segundos,
            es_mejor=e.es_mejor,
            ejecutado_en=e.ejecutado_en,
            mejora_sobre_baseline=_mejora(
                e.rmse, referencias.get((e.objetivo, e.horizonte_horas))
            ),
        )
        for e in ultimas.values()
    ]
    filas.sort(key=lambda f: (f.objetivo, f.horizonte_horas, f.rmse))

    ganadores = _ganadores(filas, referencias)
    mejor_global = _mejor_global(ganadores)

    return RespuestaComparacion(
        filas=filas,
        ganadores=ganadores,
        recomendacion=_redactar_recomendacion(ganadores),
        importancia_ganador=_importancia(ultimas.values(), mejor_global),
    )


# ---------------------------------------------------------------------------


def _ultimo_lote(
    ejecuciones: list[EjecucionEntrenamiento],
) -> dict[tuple[str, str, int], EjecucionEntrenamiento]:
    """Filas del lote más reciente de cada (objetivo, horizonte).

    `ejecuciones` llega de más reciente a más antigua, así que el primer lote
    que se ve para cada combinación es el bueno. Las ejecuciones anteriores a la
    introducción del lote no lo tienen; para esas se cae al criterio antiguo
    —la fila más reciente de cada modelo— en vez de descartarlas.
    """
    lote_vigente: dict[tuple[str, int], str | None] = {}
    seleccionadas: dict[tuple[str, str, int], EjecucionEntrenamiento] = {}

    for ejecucion in ejecuciones:
        combinacion = (ejecucion.objetivo, ejecucion.horizonte_horas)
        if combinacion not in lote_vigente:
            lote_vigente[combinacion] = ejecucion.lote

        vigente = lote_vigente[combinacion]
        if vigente is not None and ejecucion.lote != vigente:
            continue

        clave = (ejecucion.nombre_modelo, *combinacion)
        seleccionadas.setdefault(clave, ejecucion)

    return seleccionadas


def _rmse_baseline(ejecuciones) -> dict[tuple[str, int], float]:
    """RMSE del baseline estacional por objetivo y horizonte."""
    return {
        (e.objetivo, e.horizonte_horas): e.rmse
        for e in ejecuciones
        if e.nombre_modelo == ModeloBaselineEstacional.nombre
    }


def _mejora(rmse: float, referencia: float | None) -> float | None:
    """Reducción porcentual del RMSE respecto del baseline."""
    if not referencia:
        return None
    return round((referencia - rmse) / referencia * 100, 2)


def _ganadores(
    filas: list[FilaComparacion], referencias: dict[tuple[str, int], float]
) -> list[GanadorHorizonte]:
    """Mejor modelo real de cada objetivo/horizonte, excluyendo el baseline.

    El baseline no puede "ganar": es la vara de medir. Si resultara el de menor
    RMSE, lo correcto no es proclamarlo campeón sino decir que **ningún modelo
    superó al pronóstico ingenuo**, que es exactamente lo que dice el veredicto.
    """
    mejores: dict[tuple[str, int], FilaComparacion] = {}
    for fila in filas:
        if fila.nombre_modelo == ModeloBaselineEstacional.nombre:
            continue
        clave = (fila.objetivo, fila.horizonte_horas)
        if clave not in mejores or fila.rmse < mejores[clave].rmse:
            mejores[clave] = fila

    ganadores: list[GanadorHorizonte] = []
    for (objetivo, horizonte), fila in sorted(mejores.items()):
        referencia = referencias.get((objetivo, horizonte))
        ganadores.append(
            GanadorHorizonte(
                objetivo=objetivo,
                horizonte_horas=horizonte,
                etiqueta=_etiqueta(horizonte),
                nombre_modelo=fila.nombre_modelo,
                familia=fila.familia,
                rmse=fila.rmse,
                mase=fila.mase,
                mejora_sobre_baseline=fila.mejora_sobre_baseline,
                veredicto=_veredicto(fila, referencia),
            )
        )
    return ganadores


def _veredicto(fila: FilaComparacion, referencia: float | None) -> str:
    if referencia is None:
        return "Sin baseline con el que comparar en este horizonte."
    if fila.rmse >= referencia:
        return (
            "No supera al pronóstico ingenuo estacional: a este horizonte, repetir "
            "el ciclo anterior es tan bueno como el modelo."
        )
    mejora = _mejora(fila.rmse, referencia) or 0
    if mejora < 5:
        return f"Mejora el pronóstico ingenuo solo un {mejora:.1f} %: ventaja marginal."
    return f"Reduce el error del pronóstico ingenuo un {mejora:.1f} %."


def _mejor_global(ganadores: list[GanadorHorizonte]) -> str | None:
    """Modelo que gana en más horizontes; ante empate, el de menor RMSE."""
    if not ganadores:
        return None
    conteo: dict[str, int] = {}
    for g in ganadores:
        conteo[g.nombre_modelo] = conteo.get(g.nombre_modelo, 0) + 1
    maximo = max(conteo.values())
    empatados = [n for n, c in conteo.items() if c == maximo]
    if len(empatados) == 1:
        return empatados[0]
    return min(
        (g for g in ganadores if g.nombre_modelo in empatados), key=lambda g: g.rmse
    ).nombre_modelo


def _redactar_recomendacion(ganadores: list[GanadorHorizonte]) -> str:
    if not ganadores:
        return "Todavía no hay entrenamientos suficientes para recomendar un modelo."

    partes = [
        f"{g.etiqueta}: {g.nombre_modelo} (RMSE {g.rmse:,.2f})" for g in ganadores
    ]
    mejor = _mejor_global(ganadores)
    superan = [g for g in ganadores if (g.mejora_sobre_baseline or 0) > 0]

    resumen = " · ".join(partes)
    if not superan:
        return (
            f"{resumen}. Ningún modelo supera al pronóstico ingenuo estacional en "
            "ningún horizonte: con los datos actuales, la autocorrelación de la "
            "serie explica prácticamente todo. Conviene ampliar el histórico o "
            "incorporar más variables exógenas antes que probar modelos más "
            "complejos."
        )

    familias = {g.familia for g in superan}
    matiz = (
        "la familia que mejor funciona es consistente entre horizontes"
        if len(familias) == 1
        else "el mejor enfoque cambia según el horizonte, así que conviene mantener "
        "un modelo distinto para cada uno"
    )
    return f"{resumen}. Modelo recomendado en conjunto: {mejor}; {matiz}."


def _importancia(ejecuciones, nombre_modelo: str | None) -> dict[str, float]:
    """Importancia de variables de la ejecución más reciente del modelo ganador."""
    if not nombre_modelo:
        return {}
    for ejecucion in ejecuciones:
        if ejecucion.nombre_modelo == nombre_modelo and ejecucion.importancia_variables:
            try:
                return json.loads(ejecucion.importancia_variables)
            except json.JSONDecodeError:
                log.warning("Importancia mal serializada en la ejecución %d", ejecucion.id)
                return {}
    return {}


def _etiqueta(horizonte: int) -> str:
    for etiqueta, horas in HORIZONTES.items():
        if horas == horizonte:
            return etiqueta
    return f"{horizonte}h"


def _cargar_datos(db: SesionBD) -> pd.DataFrame:
    """Alias histórico, conservado por los scripts de línea de comandos."""
    return _cargar_historico(db)
