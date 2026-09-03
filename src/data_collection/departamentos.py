"""Catálogo de departamentos y reparto de la demanda de XM sobre ellos.

El problema que resuelve este módulo
------------------------------------

La API pública de XM **no tiene entidad "Departamento"**. Lo más cercano es
``DemaCome`` desagregada por ``MercadoComercializacion``: 29 mercados de
comercialización cuya delimitación es *administrativa*, no política. La mayoría
coincide con un departamento (ANTIOQUIA, BOYACA, HUILA...), pero unos pocos no:

* ``CARIBE MAR`` y ``CARIBE SOL`` cubren cuatro y tres departamentos
  respectivamente (son los dos operadores que heredaron el área de la antigua
  Electricaribe).
* ``BOGOTA - CUNDINAMARCA`` mezcla el Distrito Capital con 116 municipios
  cundinamarqueses.
* ``CALI - YUMBO - PUERTO TEJADA`` es de EMCALI y se sale del Valle: Puerto
  Tejada está en Cauca.
* Varios mercados pequeños (``CARTAGO``, ``TULUA``, ``PEREIRA``, ``RUITOQUE``,
  ``VALLE DEL SIBUNDOY``, ``BAJO PUTUMAYO``, ``POPAYAN - PURACE``) son partes de
  un departamento que ya tiene otro mercado: se **suman** al mismo destino.

Por eso el reparto se hace con pesos explícitos y no ocultos en una consulta.

Honestidad del dato
-------------------

Los pesos de los mercados multidepartamentales son **aproximaciones** basadas en
el reparto de demanda entre los departamentos que atiende cada operador de red.
No son una medición. El modelo de datos guarda `factor_reparto` en cada fila y
la interfaz marca esos departamentos como *estimados* para que nadie los lea
como si XM los publicara así. Los mercados con peso 1.0 sí son atribución
directa y se marcan como *directos*.

Zonas No Interconectadas
------------------------

Amazonas, Guainía, Vaupés, Vichada y San Andrés no aparecen en ningún mercado
porque **no están conectados al SIN**: se abastecen con generación local (ZNI,
competencia del IPSE, no de XM). El mapa debe mostrarlos como "sin cobertura
SIN", nunca con demanda cero, que sugeriría que no consumen energía.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Catálogo DANE
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Departamento:
    """Un departamento colombiano según la codificación DANE."""

    codigo: str
    nombre: str
    #: `False` para las Zonas No Interconectadas, que no tienen demanda en el SIN.
    interconectado: bool = True


DEPARTAMENTOS: tuple[Departamento, ...] = (
    Departamento("05", "Antioquia"),
    Departamento("08", "Atlántico"),
    Departamento("11", "Bogotá D.C."),
    Departamento("13", "Bolívar"),
    Departamento("15", "Boyacá"),
    Departamento("17", "Caldas"),
    Departamento("18", "Caquetá"),
    Departamento("19", "Cauca"),
    Departamento("20", "Cesar"),
    Departamento("23", "Córdoba"),
    Departamento("25", "Cundinamarca"),
    Departamento("27", "Chocó"),
    Departamento("41", "Huila"),
    Departamento("44", "La Guajira"),
    Departamento("47", "Magdalena"),
    Departamento("50", "Meta"),
    Departamento("52", "Nariño"),
    Departamento("54", "Norte de Santander"),
    Departamento("63", "Quindío"),
    Departamento("66", "Risaralda"),
    Departamento("68", "Santander"),
    Departamento("70", "Sucre"),
    Departamento("73", "Tolima"),
    Departamento("76", "Valle del Cauca"),
    Departamento("81", "Arauca"),
    Departamento("85", "Casanare"),
    Departamento("86", "Putumayo"),
    Departamento("88", "San Andrés y Providencia", False),
    Departamento("91", "Amazonas", False),
    Departamento("94", "Guainía", False),
    Departamento("95", "Guaviare"),
    Departamento("97", "Vaupés", False),
    Departamento("99", "Vichada", False),
)

POR_CODIGO: dict[str, Departamento] = {d.codigo: d for d in DEPARTAMENTOS}


# ---------------------------------------------------------------------------
# Reparto mercado de comercialización -> departamentos
# ---------------------------------------------------------------------------

#: ``mercado -> ((codigo_dane, peso), ...)``. Los pesos de cada mercado suman 1.
#:
#: Un peso de 1.0 significa atribución directa (el mercado cae íntegro en un
#: departamento). Los repartidos llevan su justificación al lado.
REPARTO: dict[str, tuple[tuple[str, float], ...]] = {
    # --- Atribución directa ------------------------------------------------
    "ANTIOQUIA": (("05", 1.0),),
    "ARAUCA": (("81", 1.0),),
    "BOYACA": (("15", 1.0),),
    "CALDAS": (("17", 1.0),),
    "CAQUETA": (("18", 1.0),),
    "CASANARE": (("85", 1.0),),
    "CAUCA": (("19", 1.0),),
    "CHOCO": (("27", 1.0),),
    "GUAVIARE": (("95", 1.0),),
    "HUILA": (("41", 1.0),),
    "META": (("50", 1.0),),
    "NARIÑO": (("52", 1.0),),
    "NORTE DE SANTANDER": (("54", 1.0),),
    "QUINDIO": (("63", 1.0),),
    "SANTANDER": (("68", 1.0),),
    "TOLIMA": (("73", 1.0),),
    "VALLE DEL CAUCA": (("76", 1.0),),
    # --- Directos que se acumulan sobre un departamento ya presente --------
    "CARTAGO": (("76", 1.0),),  # municipio del norte del Valle
    "TULUA": (("76", 1.0),),  # Compañía de Electricidad de Tuluá
    "PEREIRA": (("66", 1.0),),  # Empresa de Energía de Pereira
    "RUITOQUE": (("68", 1.0),),  # Ruitoque ESP, área metropolitana de Bucaramanga
    "POPAYAN - PURACE": (("19", 1.0),),
    "PUTUMAYO": (("86", 1.0),),
    "BAJO PUTUMAYO": (("86", 1.0),),
    "VALLE DEL SIBUNDOY": (("86", 1.0),),
    # --- Repartidos entre varios departamentos -----------------------------
    # Enel Colombia: Distrito Capital + 116 municipios de Cundinamarca. Bogotá
    # concentra la gran mayoría del consumo del mercado.
    "BOGOTA - CUNDINAMARCA": (("11", 0.78), ("25", 0.22)),
    # EMCALI: Cali y Yumbo están en Valle; Puerto Tejada, en Cauca.
    "CALI - YUMBO - PUERTO TEJADA": (("76", 0.97), ("19", 0.03)),
    # Caribemar (Afinia): Bolívar, Córdoba, Cesar y Sucre.
    "CARIBE MAR": (("13", 0.38), ("23", 0.26), ("20", 0.21), ("70", 0.15)),
    # Air-e: Atlántico, Magdalena y La Guajira.
    "CARIBE SOL": (("08", 0.60), ("47", 0.25), ("44", 0.15)),
}

#: Mercados cuyo valor por departamento es una estimación y no una atribución
#: directa. La interfaz los señala explícitamente.
MERCADOS_REPARTIDOS: frozenset[str] = frozenset(
    mercado for mercado, pesos in REPARTO.items() if len(pesos) > 1
)


def departamentos_de(mercado: str) -> tuple[tuple[str, float], ...]:
    """Devuelve el reparto de un mercado. Tupla vacía si no está catalogado."""
    return REPARTO.get(mercado.strip().upper(), ())


def es_estimado(mercado: str) -> bool:
    """¿El valor atribuido a partir de este mercado es una estimación?"""
    return mercado.strip().upper() in MERCADOS_REPARTIDOS


def validar_reparto() -> list[str]:
    """Comprueba la coherencia interna de la tabla. Devuelve los problemas.

    Se usa en las pruebas: si alguien añade un mercado nuevo con pesos que no
    suman 1, o apunta a un código DANE inexistente, la demanda nacional dejaría
    de cuadrar con la suma de los departamentos y nadie lo notaría a simple
    vista en el mapa.
    """
    problemas: list[str] = []

    for mercado, pesos in REPARTO.items():
        total = sum(peso for _, peso in pesos)
        if abs(total - 1.0) > 1e-6:
            problemas.append(f"{mercado}: los pesos suman {total:.4f}, no 1.0")

        for codigo, peso in pesos:
            if codigo not in POR_CODIGO:
                problemas.append(f"{mercado}: código DANE desconocido '{codigo}'")
            elif not POR_CODIGO[codigo].interconectado:
                problemas.append(
                    f"{mercado}: apunta a {POR_CODIGO[codigo].nombre}, marcado como ZNI"
                )
            if peso <= 0:
                problemas.append(f"{mercado}/{codigo}: peso no positivo ({peso})")

    return problemas
