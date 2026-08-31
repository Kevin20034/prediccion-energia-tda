"""Módulo administrativo: gestión de usuarios y roles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.api.deps import SesionBD, UsuarioActual, solo_administrador
from src.api.schemas.auth import UsuarioCrear, UsuarioSalida
from src.core.security import hashear_password
from src.database.models import RolUsuario, Usuario

router = APIRouter(
    prefix="/usuarios",
    tags=["Administración"],
    dependencies=[Depends(solo_administrador)],
)


@router.get("", response_model=list[UsuarioSalida], summary="Listar usuarios")
def listar(
    db: SesionBD,
    rol: RolUsuario | None = Query(None, description="Filtrar por rol"),
    limite: int = Query(100, ge=1, le=500),
) -> list[Usuario]:
    consulta = select(Usuario)
    if rol:
        consulta = consulta.where(Usuario.rol == rol)
    return list(db.execute(consulta.order_by(Usuario.id).limit(limite)).scalars().all())


@router.post(
    "",
    response_model=UsuarioSalida,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario",
)
def crear(datos: UsuarioCrear, db: SesionBD) -> Usuario:
    usuario = Usuario(
        email=datos.email.lower(),
        nombre=datos.nombre,
        password_hash=hashear_password(datos.password),
        rol=datos.rol,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con el email {datos.email}",
        ) from exc

    db.refresh(usuario)
    return usuario


@router.patch(
    "/{usuario_id}/estado",
    response_model=UsuarioSalida,
    summary="Activar o desactivar un usuario",
)
def cambiar_estado(
    usuario_id: int,
    activo: bool,
    db: SesionBD,
    administrador: UsuarioActual,
) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    # Sin esta guarda, un administrador podría desactivarse a sí mismo y dejar
    # el sistema sin nadie que pueda volver a activarlo.
    if usuario.id == administrador.id and not activo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Un administrador no puede desactivar su propia cuenta",
        )

    usuario.activo = activo
    db.commit()
    db.refresh(usuario)
    return usuario


@router.patch("/{usuario_id}/rol", response_model=UsuarioSalida, summary="Cambiar el rol")
def cambiar_rol(usuario_id: int, rol: RolUsuario, db: SesionBD) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    usuario.rol = rol
    db.commit()
    db.refresh(usuario)
    return usuario
