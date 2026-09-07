"""El endpoint de estado de los datos.

Lo que se comprueba aquí no es que devuelva 200, sino que diga **la verdad sobre
la edad del dato**. Este endpoint existe porque el sistema estuvo una semana
sirviendo datos viejos sin que nada en pantalla lo dijera; una versión que
responda bonito pero mida mal la antigüedad reproduciría exactamente ese fallo.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.database.models import DatoHistorico


def token_de(cliente, email: str, password: str = "Password123*") -> str:
    respuesta = cliente.post("/auth/login", data={"username": email, "password": password})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabecera(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def fuente(cuerpo: dict, nombre: str) -> dict:
    return next(f for f in cuerpo["fuentes"] if f["nombre"] == nombre)


class TestEstadoDatos:
    def test_mide_el_retraso_contra_el_reloj(self, cliente, db, usuario_admin):
        """La edad del dato se mide contra ahora, no contra la última ingesta.

        Confundir las dos es justo lo que deja pasar una semana sin que nadie se
        entere: la ingesta puede haber corrido hace un minuto y traer, aun así,
        un dato de hace seis días.
        """
        db.add(
            DatoHistorico(
                fecha_hora=datetime.now(UTC) - timedelta(hours=48),
                precio_bolsa=500.0,
            )
        )
        db.commit()

        respuesta = cliente.get("/estado-datos", headers=cabecera(token_de(cliente, usuario_admin.email)))

        assert respuesta.status_code == 200
        xm = fuente(respuesta.json(), "XM")
        assert 47.5 < xm["horas_de_retraso"] < 48.5

    def test_sin_datos_devuelve_nulo_y_no_cero(self, cliente, usuario_admin):
        """Una tabla vacía no está «al día»: está vacía.

        Devolver 0 horas de retraso se leería en pantalla como dato fresco, que es
        la mentira más cara que puede contar este endpoint.
        """
        respuesta = cliente.get("/estado-datos", headers=cabecera(token_de(cliente, usuario_admin.email)))

        assert respuesta.status_code == 200
        xm = fuente(respuesta.json(), "XM")
        assert xm["ultimo_dato"] is None
        assert xm["horas_de_retraso"] is None

    def test_informa_si_la_ingesta_automatica_esta_activa(self, cliente, usuario_admin):
        """La interfaz necesita distinguir «no hay datos nuevos» de «nadie los busca»."""
        respuesta = cliente.get("/estado-datos", headers=cabecera(token_de(cliente, usuario_admin.email)))

        cuerpo = respuesta.json()
        assert "ingesta_automatica" in cuerpo
        assert isinstance(cuerpo["ingesta_automatica"], bool)

    def test_requiere_sesion(self, cliente):
        """El estado del sistema no es público."""
        assert cliente.get("/estado-datos").status_code == 401

    def test_lo_ve_cualquier_rol(self, cliente, usuario_institucional):
        """La frescura del dato sale en la barra, que la ven todos los roles."""
        respuesta = cliente.get(
            "/estado-datos", headers=cabecera(token_de(cliente, usuario_institucional.email))
        )
        assert respuesta.status_code == 200
