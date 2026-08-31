"""Hash de contraseñas y emisión/verificación de tokens JWT.

Decisiones:

* **bcrypt directo** en vez de `passlib`. Passlib 1.7.4 (última versión, 2020)
  se rompe al leer `bcrypt.__about__` con bcrypt >= 4.1 y el proyecto está sin
  mantenimiento. Usar `bcrypt` directamente son 6 líneas y no arrastra el bug.
* **PyJWT** en vez de `python-jose`. Es la librería que usa hoy la documentación
  oficial de FastAPI; `python-jose` lleva años sin releases y acumula CVEs.
  La API es equivalente para HS256.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError

from src.core.config import settings

# --- Contraseñas -----------------------------------------------------------


def hashear_password(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en claro."""
    # bcrypt trunca silenciosamente en 72 bytes; recortamos explícitamente para
    # que el comportamiento sea visible y no dependa de la versión.
    bytes_password = password.encode("utf-8")[:72]
    return bcrypt.hashpw(bytes_password, bcrypt.gensalt()).decode("utf-8")


def verificar_password(password_plano: str, password_hash: str) -> bool:
    """Compara una contraseña en claro contra su hash almacenado."""
    try:
        return bcrypt.checkpw(
            password_plano.encode("utf-8")[:72],
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # Hash malformado en base de datos: se trata como credencial inválida.
        return False


# --- Tokens JWT ------------------------------------------------------------


def crear_access_token(
    subject: str,
    rol: str,
    expira_en: timedelta | None = None,
) -> str:
    """Emite un JWT firmado con HS256.

    Args:
        subject: identificador del usuario (usamos el email).
        rol: rol del usuario, se incrusta en el token para evitar una consulta
            a base de datos en cada petición.
        expira_en: vigencia; por defecto `ACCESS_TOKEN_EXPIRE_MINUTES`.
    """
    ahora = datetime.now(UTC)
    duracion = expira_en or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "rol": rol,
        "iat": ahora,
        "exp": ahora + duracion,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decodificar_access_token(token: str) -> dict[str, Any] | None:
    """Valida firma y expiración. Devuelve el payload o `None` si es inválido."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except InvalidTokenError:
        return None
