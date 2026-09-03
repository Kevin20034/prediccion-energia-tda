"""Catálogo de variables: etiqueta legible, unidad y grupo temático.

Un mismo diccionario alimenta el selector de series del frontend, las leyendas
de las gráficas y las respuestas de la API. Tenerlo en un solo sitio evita el
problema clásico de que el eje diga "kWh" y la leyenda "MWh" porque cada uno
tenía su propia tabla.

El campo `escala` es el divisor con el que la interfaz convierte la unidad de
origen en la de presentación: XM publica la demanda en kWh, y una demanda
horaria nacional en kWh son ocho cifras que nadie lee. Dividida por un millón
son GWh, que sí se leen.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Variable:
    """Metadatos de presentación de una variable del histórico."""

    nombre: str
    etiqueta: str
    unidad: str
    grupo: str
    escala: float = 1.0
    #: Unidad ya escalada, la que se muestra en los ejes.
    unidad_vista: str = ""

    def __post_init__(self) -> None:
        if not self.unidad_vista:
            object.__setattr__(self, "unidad_vista", self.unidad)


def _v(nombre, etiqueta, unidad, grupo, escala=1.0, unidad_vista="") -> Variable:
    return Variable(nombre, etiqueta, unidad, grupo, escala, unidad_vista)


CATALOGO: dict[str, Variable] = {
    v.nombre: v
    for v in (
        # --- Precio ---------------------------------------------------------
        _v("precio_bolsa", "Precio de bolsa", "COP/kWh", "precio"),
        _v("precio_bolsa_ponderado", "Precio de bolsa ponderado", "COP/kWh", "precio"),
        _v("precio_oferta_maximo", "Precio de oferta máximo", "COP/kWh", "precio"),
        _v("costo_marginal", "Costo marginal del despacho", "COP/kWh", "precio"),
        _v("precio_contratos_regulado", "Contratos · regulado", "COP/kWh", "precio"),
        _v("precio_contratos_no_regulado", "Contratos · no regulado", "COP/kWh", "precio"),
        _v("precio_escasez", "Precio de escasez", "COP/kWh", "precio"),
        _v("precio_escasez_marginal", "Precio marginal de escasez", "COP/kWh", "precio"),
        # --- Demanda --------------------------------------------------------
        _v("demanda_real", "Demanda real", "kWh", "demanda", 1e6, "GWh"),
        _v("demanda_comercial", "Demanda comercial", "kWh", "demanda", 1e6, "GWh"),
        _v("demanda_regulada", "Demanda regulada", "kWh", "demanda", 1e6, "GWh"),
        _v("demanda_no_regulada", "Demanda no regulada", "kWh", "demanda", 1e6, "GWh"),
        _v("demanda_maxima_potencia", "Demanda máxima de potencia", "kW", "demanda", 1e6, "GW"),
        # --- Generación -----------------------------------------------------
        _v("generacion_total", "Generación total", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_ideal", "Generación ideal", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_hidraulica", "Hidráulica", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_termica", "Térmica", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_solar", "Solar", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_eolica", "Eólica", "kWh", "generacion", 1e6, "GWh"),
        _v("generacion_cogeneracion", "Cogeneración", "kWh", "generacion", 1e6, "GWh"),
        _v("disponibilidad_real", "Disponibilidad real", "kW", "generacion", 1e6, "GW"),
        # --- Sistema --------------------------------------------------------
        _v("perdidas_energia", "Pérdidas de energía", "kWh", "sistema", 1e3, "MWh"),
        _v("restricciones_sin_alivio", "Restricciones sin alivio", "COP", "sistema", 1e6, "M COP"),
        _v("factor_emision_co2", "Factor de emisión", "gCO₂e/kWh", "sistema"),
        _v("exportaciones_energia", "Exportaciones", "kWh", "sistema", 1e3, "MWh"),
        _v("importaciones_energia", "Importaciones", "kWh", "sistema", 1e3, "MWh"),
        # --- Hidrología -----------------------------------------------------
        _v("volumen_util_embalse", "Nivel de embalses", "%", "hidrologia"),
        _v("aportes_hidricos", "Aportes hídricos", "kWh", "hidrologia", 1e6, "GWh"),
        _v("aportes_media_historica", "Aportes · media histórica", "kWh", "hidrologia", 1e6, "GWh"),
        _v("vertimientos_energia", "Vertimientos", "kWh", "hidrologia", 1e6, "GWh"),
        # --- Clima ----------------------------------------------------------
        _v("temperatura", "Temperatura", "°C", "clima"),
        _v("precipitacion", "Precipitación", "mm", "clima"),
        _v("humedad_relativa", "Humedad relativa", "%", "clima"),
        _v("indice_oni", "Índice ONI", "anomalía", "clima"),
    )
}

#: Orden en que la interfaz presenta los grupos.
GRUPOS: tuple[tuple[str, str], ...] = (
    ("precio", "Precio y mercado"),
    ("demanda", "Demanda"),
    ("generacion", "Generación"),
    ("hidrologia", "Hidrología"),
    ("sistema", "Sistema"),
    ("clima", "Clima"),
)


def metadatos(nombre: str) -> Variable:
    """Metadatos de una variable; genéricos si no está catalogada."""
    return CATALOGO.get(nombre) or Variable(nombre, nombre.replace("_", " "), "", "otros")


def variables_de(grupo: str) -> list[Variable]:
    return [v for v in CATALOGO.values() if v.grupo == grupo]
