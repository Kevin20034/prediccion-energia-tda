"""Endpoints del fenómeno del Niño.

El endpoint que importa es `/nino/efecto`: es el que responde a la pregunta de
para qué sirve la sección. Sobre los datos reales del proyecto dice algo que
contradice la intuición —El Niño multiplica el precio por 2,4 frente a La Niña
mientras la demanda apenas se mueve— así que tiene que calcular bien y, sobre
todo, **declarar cuándo la muestra no da para afirmarlo**.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.database.models import DatoHistorico


def token_de(cliente, email: str, password: str = "Password123*") -> str:
    respuesta = cliente.post("/auth/login", data={"username": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabecera(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


#: Cada fase arranca en un año distinto. Con muestras de un año de horas, unas
#: bases más juntas se solaparían y chocarían contra la clave única de la hora.
BASES = {
    "NEUTRO": datetime(2021, 1, 1, tzinfo=UTC),
    "EL_NINO": datetime(2023, 1, 1, tzinfo=UTC),
    "LA_NINA": datetime(2025, 1, 1, tzinfo=UTC),
}


def _sembrar(db, fase: str, horas: int, precio: float, demanda: float, oni: float) -> None:
    """Horas consecutivas de una misma fase ENSO."""
    base = BASES[fase]
    for i in range(horas):
        db.add(
            DatoHistorico(
                fecha_hora=base + timedelta(hours=i),
                precio_bolsa=precio,
                demanda_real=demanda,
                temperatura=25.0,
                indice_oni=oni,
                fenomeno_climatico=fase,
            )
        )
    db.commit()


class TestEfecto:
    def test_agrupa_por_fase(self, cliente, db, usuario_admin):
        _sembrar(db, "EL_NINO", 9000, precio=600.0, demanda=9_000_000.0, oni=1.5)
        _sembrar(db, "NEUTRO", 9000, precio=440.0, demanda=9_010_000.0, oni=0.1)

        r = cliente.get("/nino/efecto", headers=cabecera(token_de(cliente, usuario_admin.email)))

        assert r.status_code == 200
        por_fase = {f["fase"]: f for f in r.json()["fases"]}
        assert por_fase["EL_NINO"]["precio"] == pytest.approx(600.0)
        assert por_fase["EL_NINO"]["horas"] == 9000

    def test_marca_como_debil_la_muestra_de_menos_de_un_ano(self, cliente, db, usuario_admin):
        """La Niña son 123 días en los datos reales: su media es también la de
        esos cuatro meses concretos, con su estacionalidad. No se puede separar
        una cosa de la otra, y la interfaz tiene que poder decirlo."""
        _sembrar(db, "EL_NINO", 9000, precio=600.0, demanda=9_000_000.0, oni=1.5)
        _sembrar(db, "LA_NINA", 2952, precio=250.0, demanda=9_000_000.0, oni=-0.8)

        r = cliente.get("/nino/efecto", headers=cabecera(token_de(cliente, usuario_admin.email)))

        por_fase = {f["fase"]: f for f in r.json()["fases"]}
        assert por_fase["EL_NINO"]["evidencia"] == "solida"
        assert por_fase["LA_NINA"]["evidencia"] == "debil"

    def test_compara_contra_neutro(self, cliente, db, usuario_admin):
        """La cifra que interesa es cuánto se aparta de lo normal, no el nivel."""
        _sembrar(db, "NEUTRO", 9000, precio=400.0, demanda=9_000_000.0, oni=0.1)
        _sembrar(db, "EL_NINO", 9000, precio=600.0, demanda=9_090_000.0, oni=1.5)

        r = cliente.get("/nino/efecto", headers=cabecera(token_de(cliente, usuario_admin.email)))

        por_fase = {f["fase"]: f for f in r.json()["fases"]}
        # 600 sobre 400 es un 50 % más caro; la demanda solo sube un 1 %.
        assert por_fase["EL_NINO"]["variacion_precio"] == pytest.approx(50.0, abs=0.1)
        assert por_fase["EL_NINO"]["variacion_demanda"] == pytest.approx(1.0, abs=0.1)
        assert por_fase["NEUTRO"]["variacion_precio"] is None

    def test_explica_impacto_en_generacion_y_demanda(self, cliente, db, usuario_admin):
        _sembrar(db, "NEUTRO", 9000, precio=400.0, demanda=9_000_000.0, oni=0.1)
        _sembrar(db, "EL_NINO", 9000, precio=600.0, demanda=9_090_000.0, oni=1.5)

        # La energía hidráulica cae y la térmica sube sin que cambie mucho el consumo.
        db.add(
            DatoHistorico(
                fecha_hora=datetime(2023, 1, 1, tzinfo=UTC),
                precio_bolsa=600.0,
                demanda_real=9_090_000.0,
                generacion_hidraulica=800.0,
                generacion_termica=200.0,
                temperatura=25.0,
                indice_oni=1.5,
                fenomeno_climatico="EL_NINO",
            )
        )
        db.commit()

        r = cliente.get("/nino/efecto", headers=cabecera(token_de(cliente, usuario_admin.email)))

        por_fase = {f["fase"]: f for f in r.json()["fases"]}
        assert por_fase["EL_NINO"]["generacion_hidraulica"] == pytest.approx(800.0, abs=0.1)
        assert por_fase["EL_NINO"]["generacion_termica"] == pytest.approx(200.0, abs=0.1)
        assert por_fase["EL_NINO"]["variacion_generacion_hidraulica"] is not None
        assert por_fase["EL_NINO"]["variacion_generacion_termica"] is not None

    def test_sin_datos_devuelve_lista_vacia(self, cliente, usuario_admin):
        r = cliente.get("/nino/efecto", headers=cabecera(token_de(cliente, usuario_admin.email)))
        assert r.status_code == 200
        assert r.json()["fases"] == []


class TestEstado:
    def test_clasifica_la_intensidad(self, cliente, db, usuario_admin):
        """Criterio NOAA sobre el valor absoluto del ONI."""
        _sembrar(db, "EL_NINO", 10, precio=600.0, demanda=9_000_000.0, oni=1.7)

        r = cliente.get("/nino/estado", headers=cabecera(token_de(cliente, usuario_admin.email)))

        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["fase"] == "EL_NINO"
        assert cuerpo["intensidad"] == "fuerte"

    def test_sin_datos_no_revienta(self, cliente, usuario_admin):
        r = cliente.get("/nino/estado", headers=cabecera(token_de(cliente, usuario_admin.email)))
        assert r.status_code == 200
        assert r.json()["fase"] is None


class TestAcceso:
    def test_requiere_sesion(self, cliente):
        assert cliente.get("/nino/efecto").status_code == 401

    def test_lo_ve_el_rol_institucional(self, cliente, usuario_institucional):
        """Es una sección para todos, no solo para analistas."""
        r = cliente.get(
            "/nino/efecto", headers=cabecera(token_de(cliente, usuario_institucional.email))
        )
        assert r.status_code == 200
