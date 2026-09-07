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
    #: Coordenadas de la **capital**, no del centroide geométrico.
    #:
    #: El clima solo interesa aquí en la medida en que explica consumo, y el
    #: consumo está donde está la gente. El centroide del Chocó cae en selva
    #: deshabitada y el del Meta en llanura vacía: su temperatura no explica
    #: ninguna curva de demanda.
    latitud: float = 0.0
    longitud: float = 0.0


DEPARTAMENTOS: tuple[Departamento, ...] = (
    Departamento("05", "Antioquia", True, 6.2442, -75.5812),           # Medellín
    Departamento("08", "Atlántico", True, 10.9685, -74.7813),          # Barranquilla
    Departamento("11", "Bogotá D.C.", True, 4.7110, -74.0721),         # Bogotá
    Departamento("13", "Bolívar", True, 10.3910, -75.4794),            # Cartagena
    Departamento("15", "Boyacá", True, 5.5353, -73.3678),              # Tunja
    Departamento("17", "Caldas", True, 5.0703, -75.5138),              # Manizales
    Departamento("18", "Caquetá", True, 1.6144, -75.6062),             # Florencia
    Departamento("19", "Cauca", True, 2.4448, -76.6147),               # Popayán
    Departamento("20", "Cesar", True, 10.4631, -73.2532),              # Valledupar
    Departamento("23", "Córdoba", True, 8.7479, -75.8814),             # Montería
    # La capital de Cundinamarca es Bogotá, que aquí es un departamento aparte.
    # Se usa Soacha, su municipio más poblado, para no medir el mismo punto dos
    # veces y atribuirle a Cundinamarca el clima del Distrito Capital.
    Departamento("25", "Cundinamarca", True, 4.5794, -74.2168),        # Soacha
    Departamento("27", "Chocó", True, 5.6919, -76.6583),               # Quibdó
    Departamento("41", "Huila", True, 2.9273, -75.2819),               # Neiva
    Departamento("44", "La Guajira", True, 11.5444, -72.9072),         # Riohacha
    Departamento("47", "Magdalena", True, 11.2408, -74.1990),          # Santa Marta
    Departamento("50", "Meta", True, 4.1420, -73.6266),                # Villavicencio
    Departamento("52", "Nariño", True, 1.2136, -77.2811),              # Pasto
    Departamento("54", "Norte de Santander", True, 7.8939, -72.5078),  # Cúcuta
    Departamento("63", "Quindío", True, 4.5339, -75.6811),             # Armenia
    Departamento("66", "Risaralda", True, 4.8133, -75.6961),           # Pereira
    Departamento("68", "Santander", True, 7.1193, -73.1227),           # Bucaramanga
    Departamento("70", "Sucre", True, 9.3047, -75.3978),               # Sincelejo
    Departamento("73", "Tolima", True, 4.4389, -75.2322),              # Ibagué
    Departamento("76", "Valle del Cauca", True, 3.4516, -76.5320),     # Cali
    Departamento("81", "Arauca", True, 7.0844, -70.7591),              # Arauca
    Departamento("85", "Casanare", True, 5.3378, -72.3959),            # Yopal
    Departamento("86", "Putumayo", True, 1.1519, -76.6483),            # Mocoa
    Departamento("88", "San Andrés y Providencia", False, 12.5847, -81.7006),
    Departamento("91", "Amazonas", False, -4.2153, -69.9406),          # Leticia
    Departamento("94", "Guainía", False, 3.8653, -67.9239),            # Inírida
    Departamento("95", "Guaviare", True, 2.5729, -72.6459),            # San José del Guaviare
    Departamento("97", "Vaupés", False, 1.2518, -70.2340),             # Mitú
    Departamento("99", "Vichada", False, 6.1890, -67.4859),            # Puerto Carreño
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
