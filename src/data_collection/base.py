"""Interfaz común de los recolectores de datos.

Definir un contrato explícito permite añadir fuentes nuevas (por ejemplo, IDEAM
o el SIN) sin tocar el resto del sistema: basta con implementar `Recolector`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class Recolector(ABC):
    """Contrato que cumple toda fuente de datos del proyecto."""

    #: Nombre corto de la fuente, se guarda en `DatoHistorico.fuente`.
    nombre: str = "generico"

    @abstractmethod
    def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame:
        """Descarga los datos del rango pedido.

        Returns:
            `DataFrame` indexado (o con columna) `fecha_hora` en resolución
            horaria. Las implementaciones deben devolver siempre las mismas
            columnas para un mismo recolector, aunque la fuente falle (en cuyo
            caso se usan datos de respaldo).
        """
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} fuente={self.nombre}>"


class ErrorRecoleccion(RuntimeError):
    """Error irrecuperable al obtener datos de una fuente externa."""
