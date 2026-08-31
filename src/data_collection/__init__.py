"""Recolección de datos: mercado energético (XM) y variables climáticas."""

from src.data_collection.base import Recolector
from src.data_collection.clima_client import ClimaClient
from src.data_collection.xm_client import XMClient

__all__ = ["Recolector", "ClimaClient", "XMClient"]
