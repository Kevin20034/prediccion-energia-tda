"""Crea los usuarios iniciales del sistema.

Uso:
    python -m scripts.seed

Es idempotente: si un usuario ya existe, lo omite. Se puede reejecutar sin
miedo tras cada migración.
"""

from __future__ import annotations

from sqlalchemy import select

from src.core.config import settings
from src.core.logging import get_logger
from src.core.security import hashear_password
from src.database.models import RolUsuario, Usuario
from src.database.session import SessionLocal

log = get_logger(__name__)

#: Usuarios de demostración, uno por rol del trabajo de grado.
USUARIOS_DEMO = [
    ("analista@tda.edu.co", "Analista Energético", "Analista123*", RolUsuario.ANALISTA),
    ("consulta@tda.edu.co", "Usuario Institucional", "Consulta123*", RolUsuario.INSTITUCIONAL),
]


def crear_usuario(db, email: str, nombre: str, password: str, rol: RolUsuario) -> bool:
    """Crea el usuario si no existe. Devuelve True si lo creó."""
    existente = db.execute(select(Usuario).where(Usuario.email == email)).scalar_one_or_none()
    if existente:
        log.info("Ya existe: %-28s (%s)", email, existente.rol.value)
        return False

    db.add(
        Usuario(
            email=email,
            nombre=nombre,
            password_hash=hashear_password(password),
            rol=rol,
        )
    )
    log.info("Creado:    %-28s (%s)", email, rol.value)
    return True


def main() -> None:
    with SessionLocal() as db:
        creados = crear_usuario(
            db,
            settings.ADMIN_EMAIL,
            "Administrador",
            settings.ADMIN_PASSWORD,
            RolUsuario.ADMINISTRADOR,
        )
        for email, nombre, password, rol in USUARIOS_DEMO:
            creados += crear_usuario(db, email, nombre, password, rol)

        db.commit()

    print(f"\n[OK] {creados} usuario(s) creado(s).")
    print("\nCredenciales de acceso:")
    print(f"  Administrador : {settings.ADMIN_EMAIL} / {settings.ADMIN_PASSWORD}")
    for email, _, password, rol in USUARIOS_DEMO:
        print(f"  {rol.value.title():<14}: {email} / {password}")
    print("\nCambia estas contraseñas antes de cualquier despliegue real.")


if __name__ == "__main__":
    main()
