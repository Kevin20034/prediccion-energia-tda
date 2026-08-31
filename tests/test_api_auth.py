"""Pruebas de la API: autenticación, autorización por rol y endpoints básicos."""

from __future__ import annotations

import pytest

from src.core.security import (
    crear_access_token,
    decodificar_access_token,
    hashear_password,
    verificar_password,
)
from src.database.models import DatoHistorico, RolUsuario


def token_de(cliente, email: str, password: str = "Password123*") -> str:
    respuesta = cliente.post(
        "/auth/login", data={"username": email, "password": password}
    )
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()["access_token"]


def cabecera(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestSeguridad:
    def test_hash_no_es_reversible(self):
        hash_generado = hashear_password("MiClave123*")
        assert hash_generado != "MiClave123*"
        assert verificar_password("MiClave123*", hash_generado)
        assert not verificar_password("otra", hash_generado)

    def test_el_mismo_password_genera_hashes_distintos(self):
        """Cada hash lleva su propia sal: dos hashes iguales serían un fallo."""
        assert hashear_password("MiClave123*") != hashear_password("MiClave123*")

    def test_hash_malformado_no_revienta(self):
        assert verificar_password("cualquiera", "no-es-un-hash") is False

    def test_ida_y_vuelta_del_token(self):
        token = crear_access_token(subject="a@b.co", rol="ANALISTA")
        payload = decodificar_access_token(token)
        assert payload is not None
        assert payload["sub"] == "a@b.co"
        assert payload["rol"] == "ANALISTA"

    def test_token_manipulado_se_rechaza(self):
        token = crear_access_token(subject="a@b.co", rol="INSTITUCIONAL")
        assert decodificar_access_token(token[:-4] + "xxxx") is None

    def test_token_expirado_se_rechaza(self):
        from datetime import timedelta

        token = crear_access_token("a@b.co", "ANALISTA", expira_en=timedelta(seconds=-1))
        assert decodificar_access_token(token) is None


class TestEstado:
    def test_raiz(self, cliente):
        respuesta = cliente.get("/")
        assert respuesta.status_code == 200
        assert "documentacion" in respuesta.json()

    def test_salud(self, cliente):
        respuesta = cliente.get("/salud")
        assert respuesta.status_code == 200
        assert respuesta.json()["api"] == "ok"


class TestLogin:
    def test_login_correcto(self, cliente, usuario_admin):
        respuesta = cliente.post(
            "/auth/login", data={"username": usuario_admin.email, "password": "Password123*"}
        )
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["token_type"] == "bearer"
        assert cuerpo["rol"] == RolUsuario.ADMINISTRADOR.value
        assert cuerpo["access_token"]

    def test_password_incorrecta(self, cliente, usuario_admin):
        respuesta = cliente.post(
            "/auth/login", data={"username": usuario_admin.email, "password": "incorrecta"}
        )
        assert respuesta.status_code == 401

    def test_usuario_inexistente_da_el_mismo_error(self, cliente, usuario_admin):
        """No debe poder distinguirse un email registrado de uno que no lo está."""
        r_inexistente = cliente.post(
            "/auth/login", data={"username": "nadie@test.co", "password": "loquesea"}
        )
        r_password_mala = cliente.post(
            "/auth/login", data={"username": usuario_admin.email, "password": "loquesea"}
        )
        assert r_inexistente.status_code == r_password_mala.status_code == 401
        assert r_inexistente.json()["detail"] == r_password_mala.json()["detail"]

    def test_usuario_desactivado(self, cliente, db, usuario_admin):
        usuario_admin.activo = False
        db.commit()
        respuesta = cliente.post(
            "/auth/login", data={"username": usuario_admin.email, "password": "Password123*"}
        )
        assert respuesta.status_code == 403

    def test_perfil_propio(self, cliente, usuario_admin):
        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.get("/auth/yo", headers=cabecera(token))
        assert respuesta.status_code == 200
        assert respuesta.json()["email"] == usuario_admin.email
        # El hash jamás debe salir en la respuesta.
        assert "password_hash" not in respuesta.json()


class TestAutorizacion:
    def test_sin_token_devuelve_401(self, cliente):
        assert cliente.get("/datos").status_code == 401

    def test_token_invalido_devuelve_401(self, cliente):
        assert cliente.get("/datos", headers=cabecera("token.falso.xyz")).status_code == 401

    def test_institucional_no_puede_entrenar(self, cliente, usuario_institucional):
        token = token_de(cliente, usuario_institucional.email)
        respuesta = cliente.post("/entrenar", json={}, headers=cabecera(token))
        assert respuesta.status_code == 403

    def test_institucional_no_puede_gestionar_usuarios(self, cliente, usuario_institucional):
        token = token_de(cliente, usuario_institucional.email)
        assert cliente.get("/usuarios", headers=cabecera(token)).status_code == 403

    def test_administrador_si_puede(self, cliente, usuario_admin):
        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.get("/usuarios", headers=cabecera(token))
        assert respuesta.status_code == 200

    def test_administrador_no_puede_autodesactivarse(self, cliente, usuario_admin):
        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.patch(
            f"/usuarios/{usuario_admin.id}/estado?activo=false", headers=cabecera(token)
        )
        assert respuesta.status_code == 400


class TestDatos:
    def test_lista_vacia(self, cliente, usuario_admin):
        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.get("/datos", headers=cabecera(token))
        assert respuesta.status_code == 200
        assert respuesta.json() == []

    def test_lista_con_registros(self, cliente, db, usuario_admin):
        from datetime import UTC, datetime

        db.add_all(
            [
                DatoHistorico(
                    fecha_hora=datetime(2025, 1, 1, hora, tzinfo=UTC),
                    precio_bolsa=200.0 + hora,
                    demanda_real=9_000_000.0,
                    fuente="TEST",
                )
                for hora in range(24)
            ]
        )
        db.commit()

        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.get("/datos?limite=10", headers=cabecera(token))
        assert respuesta.status_code == 200
        assert len(respuesta.json()) == 10

        resumen = cliente.get("/datos/resumen", headers=cabecera(token)).json()
        assert resumen["total_registros"] == 24
        assert resumen["precio_minimo"] == pytest.approx(200.0)
        assert resumen["precio_maximo"] == pytest.approx(223.0)

    def test_entrenar_sin_datos_suficientes(self, cliente, usuario_admin):
        token = token_de(cliente, usuario_admin.email)
        respuesta = cliente.post("/entrenar", json={}, headers=cabecera(token))
        assert respuesta.status_code == 409
        assert "registros" in respuesta.json()["detail"]
