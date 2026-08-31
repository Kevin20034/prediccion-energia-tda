"""Esquemas Pydantic: contrato público de la API.

Separar los esquemas de los modelos ORM evita exponer accidentalmente campos
internos (como `password_hash`) y permite versionar la API sin tocar la base
de datos.
"""

from src.api.schemas.auth import Token, UsuarioCrear, UsuarioLogin, UsuarioSalida
from src.api.schemas.datos import DatoHistoricoSalida, ResumenDatos
from src.api.schemas.prediccion import (
    EjecucionSalida,
    PrediccionSalida,
    SolicitudEntrenamiento,
    SolicitudPrediccion,
)

__all__ = [
    "Token",
    "UsuarioCrear",
    "UsuarioLogin",
    "UsuarioSalida",
    "DatoHistoricoSalida",
    "ResumenDatos",
    "PrediccionSalida",
    "SolicitudPrediccion",
    "SolicitudEntrenamiento",
    "EjecucionSalida",
]
