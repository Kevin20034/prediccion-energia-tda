"""El planificador de ingesta automática.

Las dos cosas que pueden salir mal aquí no son de lógica de negocio sino de
concurrencia y de resistencia:

1. Que dos procesos —o `--reload`, que levanta dos— ingieran a la vez y se pisen.
2. Que una fuente caída se lleve por delante al resto y deje la API muerta.

Ambas se prueban explícitamente. Lo demás del planificador es un bucle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.api.planificador import Planificador


def _plan(intervalo: int = 60, trabajos=None) -> Planificador:
    return Planificador(intervalo_minutos=intervalo, trabajos=trabajos or [])


class TestGuarda:
    def test_la_primera_vez_debe_correr(self):
        assert _plan().debe_correr(datetime.now(UTC)) is True

    def test_no_repite_antes_del_intervalo(self):
        """Con `--reload` o varios workers, dos procesos piden correr casi a la vez."""
        plan = _plan(intervalo=60)
        ahora = datetime.now(UTC)
        plan.marcar_ejecucion(ahora)

        assert plan.debe_correr(ahora + timedelta(minutes=5)) is False
        assert plan.debe_correr(ahora + timedelta(minutes=59)) is False
        assert plan.debe_correr(ahora + timedelta(minutes=61)) is True

    def test_el_estado_anuncia_la_proxima_revision(self):
        plan = _plan(intervalo=30)
        ahora = datetime.now(UTC)
        plan.marcar_ejecucion(ahora)

        estado = plan.estado()
        assert estado["ultima_revision"] == ahora
        assert estado["proxima_revision"] == ahora + timedelta(minutes=30)

    def test_sin_ejecuciones_el_estado_es_nulo(self):
        """Nunca haber corrido no es lo mismo que haber corrido hace mucho."""
        estado = _plan().estado()
        assert estado["ultima_revision"] is None
        assert estado["proxima_revision"] is None


class TestResistencia:
    def test_un_trabajo_que_falla_no_detiene_a_los_demas(self):
        """Una fuente caída deja el dato viejo; no mata la ingesta entera."""
        ejecutados: list[str] = []

        def revienta():
            ejecutados.append("xm")
            raise RuntimeError("XM no responde")

        def funciona():
            ejecutados.append("clima")
            return (3, 1)

        plan = _plan(trabajos=[("XM", revienta), ("Clima", funciona)])
        resultado = plan.ejecutar_una_vez()

        assert ejecutados == ["xm", "clima"]
        assert resultado["XM"]["error"] is not None
        assert resultado["Clima"]["insertados"] == 3
        assert resultado["Clima"]["actualizados"] == 1
        assert resultado["Clima"]["error"] is None

    def test_ejecutar_marca_la_revision_aunque_todo_falle(self):
        """Se revisó: que no hubiera nada que traer no significa que no se miró.

        Si un fallo dejara la marca sin poner, el planificador reintentaría en
        bucle cerrado contra una fuente caída.
        """
        def revienta():
            raise RuntimeError("caída")

        plan = _plan(trabajos=[("XM", revienta)])
        plan.ejecutar_una_vez()

        assert plan.estado()["ultima_revision"] is not None

    def test_un_trabajo_que_no_devuelve_tupla_no_rompe(self):
        """Los scripts de ingesta no siempre devuelven el par (insertados, actualizados)."""
        plan = _plan(trabajos=[("Raro", lambda: None)])
        resultado = plan.ejecutar_una_vez()

        assert resultado["Raro"]["error"] is None
        assert resultado["Raro"]["insertados"] == 0
