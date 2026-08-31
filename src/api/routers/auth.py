"""Autenticación: login y perfil del usuario autenticado."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from src.api.deps import SesionBD, UsuarioActual
from src.api.schemas.auth import Token, UsuarioSalida
from src.core.config import settings
from src.core.security import crear_access_token, verificar_password
from src.database.models import Usuario

router = APIRouter(prefix="/auth", tags=["Autenticación"])


@router.post("/login", response_model=Token, summary="Iniciar sesión y obtener un JWT")
def login(db: SesionBD, form: OAuth2PasswordRequestForm = Depends()) -> Token:
    """Valida credenciales y emite un token JWT.

    Se usa `OAuth2PasswordRequestForm` (campos `username` y `password` en
    `form-data`) porque es lo que espera el botón **Authorize** de la
    documentación interactiva en `/docs`. El campo `username` es el email.
    """
    usuario = db.execute(
        select(Usuario).where(Usuario.email == form.username)
    ).scalar_one_or_none()

    # Mismo mensaje para "usuario inexistente" y "contraseña incorrecta": si se
    # distinguieran, un atacante podría enumerar qué correos están registrados.
    if usuario is None or not verificar_password(form.password, usuario.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not usuario.activo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La cuenta está desactivada",
        )

    return Token(
        access_token=crear_access_token(subject=usuario.email, rol=usuario.rol.value),
        expira_en_minutos=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        rol=usuario.rol,
    )


@router.get("/yo", response_model=UsuarioSalida, summary="Perfil del usuario autenticado")
def perfil(usuario: UsuarioActual) -> Usuario:
    return usuario
