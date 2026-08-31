"""Esquemas de autenticación y gestión de usuarios."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from src.database.models import RolUsuario


class Token(BaseModel):
    """Respuesta de `POST /auth/login`."""

    access_token: str
    token_type: str = "bearer"
    expira_en_minutos: int
    rol: RolUsuario


class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UsuarioCrear(BaseModel):
    email: EmailStr
    nombre: str = Field(min_length=2, max_length=150)
    password: str = Field(
        min_length=8,
        max_length=72,  # límite duro de bcrypt
        description="Mínimo 8 caracteres",
    )
    rol: RolUsuario = RolUsuario.INSTITUCIONAL


class UsuarioSalida(BaseModel):
    """Vista pública de un usuario: nunca incluye el hash de la contraseña."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    nombre: str
    rol: RolUsuario
    activo: bool
    creado_en: datetime
