"""Dependencias compartidas de FastAPI: sesión de BD, usuario actual y roles.

El control de acceso se resuelve con dependencias en vez de con `if` dentro de
cada endpoint. Ventajas: la restricción queda declarada en la firma de la ruta,
aparece automáticamente en la documentación OpenAPI, y es imposible olvidarse
de comprobarla dentro del cuerpo de la función.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.security import decodificar_access_token
from src.database.models import RolUsuario, Usuario
from src.database.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

SesionBD = Annotated[Session, Depends(get_db)]
TokenBearer = Annotated[str, Depends(oauth2_scheme)]

_CREDENCIALES_INVALIDAS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas o token expirado",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_usuario_actual(token: TokenBearer, db: SesionBD) -> Usuario:
    """Resuelve el usuario a partir del JWT del encabezado `Authorization`."""
    payload = decodificar_access_token(token)
    if payload is None:
        raise _CREDENCIALES_INVALIDAS

    email = payload.get("sub")
    if not email:
        raise _CREDENCIALES_INVALIDAS

    usuario = db.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    if usuario is None:
        raise _CREDENCIALES_INVALIDAS

    # Se relee el estado desde la BD: si a un usuario se le revoca el acceso,
    # su token deja de servir de inmediato en vez de seguir válido hasta expirar.
    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    return usuario


UsuarioActual = Annotated[Usuario, Depends(get_usuario_actual)]


def require_rol(*roles_permitidos: RolUsuario) -> Callable[[Usuario], Usuario]:
    """Genera una dependencia que exige alguno de los roles indicados.

    Uso::

        @router.post("/entrenar", dependencies=[Depends(require_rol(RolUsuario.ANALISTA))])

    El ADMINISTRADOR siempre pasa: es superusuario por definición.
    """

    def verificador(usuario: UsuarioActual) -> Usuario:
        if usuario.rol is RolUsuario.ADMINISTRADOR:
            return usuario
        if usuario.rol not in roles_permitidos:
            permitidos = ", ".join(r.value for r in roles_permitidos)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Se requiere uno de estos roles: {permitidos}",
            )
        return usuario

    return verificador


#: Atajos para los casos más frecuentes.
solo_administrador = require_rol(RolUsuario.ADMINISTRADOR)
analista_o_superior = require_rol(RolUsuario.ANALISTA)
