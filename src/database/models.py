"""Modelos ORM (SQLAlchemy 2.0, estilo declarativo tipado).

Nota sobre los enums: se declaran con ``native_enum=False``, de forma que en
PostgreSQL se materializan como ``VARCHAR`` + ``CHECK`` en lugar de un tipo
``ENUM`` nativo. Motivo: alterar un enum nativo de PostgreSQL en una migración
es doloroso (``ALTER TYPE ... ADD VALUE`` no es transaccional), y además así las
mismas migraciones funcionan contra SQLite en las pruebas.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarativa de la que heredan todos los modelos."""


def _ahora() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Módulo administrativo
# ---------------------------------------------------------------------------


class RolUsuario(enum.StrEnum):
    """Roles definidos en el trabajo de grado.

    `StrEnum` (Python 3.11+) hace que cada miembro sea también una cadena, de
    modo que se serializa solo en JSON y se compara directamente con texto.
    """

    ADMINISTRADOR = "ADMINISTRADOR"
    ANALISTA = "ANALISTA"
    INSTITUCIONAL = "INSTITUCIONAL"


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        SAEnum(RolUsuario, native_enum=False, length=20, name="rol_usuario"),
        nullable=False,
        default=RolUsuario.INSTITUCIONAL,
    )
    activo: Mapped[bool] = mapped_column(default=True, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    predicciones: Mapped[list[Prediccion]] = relationship(
        back_populates="solicitado_por", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Usuario {self.email} ({self.rol.value})>"


# ---------------------------------------------------------------------------
# Módulo de datos
# ---------------------------------------------------------------------------


class DatoHistorico(Base):
    """Una observación horaria del mercado energético + variables climáticas.

    Es la tabla que alimenta el entrenamiento: una fila por hora, con el precio
    objetivo y todas las variables explicativas del trabajo de grado.
    """

    __tablename__ = "datos_historicos"
    __table_args__ = (
        UniqueConstraint("fecha_hora", name="uq_dato_historico_fecha_hora"),
        Index("ix_datos_historicos_fecha_hora", "fecha_hora"),
        CheckConstraint("precio_bolsa >= 0", name="ck_precio_no_negativo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Variable objetivo -------------------------------------------------
    precio_bolsa: Mapped[float] = mapped_column(Float, nullable=False, comment="COP/kWh")

    # --- Precio y mercado (XM, horarias) ----------------------------------
    precio_bolsa_tx1: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_oferta_maximo: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    costo_marginal: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_contratos_regulado: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_contratos_no_regulado: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")

    # --- Demanda (XM, horarias) -------------------------------------------
    demanda_real: Mapped[float | None] = mapped_column(Float, comment="kWh")
    demanda_comercial: Mapped[float | None] = mapped_column(Float, comment="kWh")
    demanda_regulada: Mapped[float | None] = mapped_column(Float, comment="kWh")
    demanda_no_regulada: Mapped[float | None] = mapped_column(Float, comment="kWh")

    # --- Generación y disponibilidad (XM, horarias) ------------------------
    generacion_total: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_ideal: Mapped[float | None] = mapped_column(
        Float, comment="kWh — generación sin restricciones; proxy de disponibilidad"
    )
    # Desglose por tecnología: se obtiene agregando `Gene` por Recurso y
    # cruzando cada planta con su tipo en `ListadoRecursos`.
    generacion_hidraulica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_termica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_solar: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_eolica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_cogeneracion: Mapped[float | None] = mapped_column(Float, comment="kWh")
    disponibilidad_real: Mapped[float | None] = mapped_column(Float, comment="kW")

    # --- Sistema y restricciones (XM, horarias) ----------------------------
    perdidas_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    restricciones_aliviadas: Mapped[float | None] = mapped_column(Float, comment="COP")
    restricciones_sin_alivio: Mapped[float | None] = mapped_column(Float, comment="COP")
    factor_emision_co2: Mapped[float | None] = mapped_column(Float, comment="gCO2e/kWh")
    exportaciones_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    importaciones_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    compras_bolsa_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    compras_contratos_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")

    # --- Hidrología y escasez (XM, diarias propagadas a las 24 horas) ------
    aportes_hidricos: Mapped[float | None] = mapped_column(Float, comment="kWh")
    aportes_media_historica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    porcentaje_aportes: Mapped[float | None] = mapped_column(
        Float, comment="fracción sobre la media histórica"
    )
    volumen_util_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    capacidad_util_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    porcentaje_volumen_util: Mapped[float | None] = mapped_column(
        Float, comment="fracción publicada por XM"
    )
    volumen_util_embalse: Mapped[float | None] = mapped_column(
        Float, comment="% de llenado de los embalses"
    )
    vertimientos_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    precio_escasez: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_escasez_base: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_escasez_marginal: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    precio_bolsa_ponderado: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")
    demanda_sin_diaria: Mapped[float | None] = mapped_column(Float, comment="kWh/día")
    demanda_maxima_potencia: Mapped[float | None] = mapped_column(Float, comment="kW")
    delta_nacional: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")

    # --- Variables climáticas (Open-Meteo / NOAA) -------------------------
    temperatura: Mapped[float | None] = mapped_column(Float, comment="°C")
    precipitacion: Mapped[float | None] = mapped_column(Float, comment="mm")
    humedad_relativa: Mapped[float | None] = mapped_column(Float, comment="%")
    indice_oni: Mapped[float | None] = mapped_column(Float, comment="Oceanic Niño Index")
    fenomeno_climatico: Mapped[str | None] = mapped_column(
        String(20), comment="EL_NINO | LA_NINA | NEUTRO"
    )

    fuente: Mapped[str] = mapped_column(String(50), default="XM", nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<DatoHistorico {self.fecha_hora:%Y-%m-%d %H:%M} precio={self.precio_bolsa}>"


# ---------------------------------------------------------------------------
# Módulo predictivo
# ---------------------------------------------------------------------------


class EjecucionEntrenamiento(Base):
    """Registro de cada entrenamiento, con las métricas de todos los modelos.

    Guardar esto en base de datos (y no solo en un log) es lo que permite
    responder en la tesis "¿qué modelo fue mejor y con qué error?" de forma
    trazable y reproducible.
    """

    __tablename__ = "ejecuciones_entrenamiento"
    __table_args__ = (
        Index("ix_ejecuciones_objetivo_horizonte", "objetivo", "horizonte_horas"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre_modelo: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    #: Identificador del entrenamiento que produjo esta fila.
    #:
    #: Es lo que permite comparar modelos entre sí con garantías: todas las
    #: filas de un mismo lote se entrenaron con los mismos datos, el mismo corte
    #: y el mismo código. Sin él, un modelo que falla en la última ejecución
    #: conserva su fila anterior y la tabla comparativa lo muestra como si
    #: hubiera competido —con métricas de otro conjunto de datos.
    lote: Mapped[str | None] = mapped_column(String(36), index=True)

    #: Qué se predijo y a cuántas horas vista. Sin estas dos columnas, comparar
    #: dos ejecuciones es comparar peras con manzanas: el RMSE de un pronóstico
    #: a 24 h y el de uno a 720 h no viven en la misma escala de dificultad.
    objetivo: Mapped[str] = mapped_column(String(40), nullable=False, default="precio_bolsa")
    horizonte_horas: Mapped[int] = mapped_column(Integer, nullable=False, default=24)

    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    mape: Mapped[float] = mapped_column(Float, nullable=False)
    smape: Mapped[float | None] = mapped_column(Float, comment="MAPE simétrico, %")
    mase: Mapped[float | None] = mapped_column(
        Float, comment="Error relativo al baseline estacional; <1 significa que le gana"
    )
    r2: Mapped[float | None] = mapped_column(Float)

    #: Media y desviación del RMSE en la validación *walk-forward*. Una
    #: desviación alta delata un modelo que solo funciona en algunos tramos.
    rmse_validacion: Mapped[float | None] = mapped_column(Float)
    desviacion_validacion: Mapped[float | None] = mapped_column(Float)
    n_pliegues: Mapped[int | None] = mapped_column(Integer)

    n_muestras_entrenamiento: Mapped[int] = mapped_column(Integer, nullable=False)
    n_muestras_prueba: Mapped[int] = mapped_column(Integer, nullable=False)
    hiperparametros: Mapped[str | None] = mapped_column(Text, comment="JSON serializado")
    importancia_variables: Mapped[str | None] = mapped_column(
        Text, comment="JSON: variable -> importancia, ya ordenado"
    )
    ruta_artefacto: Mapped[str | None] = mapped_column(String(500))
    es_mejor: Mapped[bool] = mapped_column(default=False, nullable=False)
    duracion_segundos: Mapped[float | None] = mapped_column(Float)

    ejecutado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ejecucion {self.nombre_modelo} {self.horizonte_horas}h RMSE={self.rmse:.2f}>"


class Prediccion(Base):
    """Un punto de pronóstico emitido por un modelo entrenado.

    Sirve tanto para el precio de bolsa como para la demanda: la columna
    `objetivo` dice cuál de los dos, y `unidad` cómo se lee `valor_estimado`.
    Generalizar la tabla en vez de duplicarla evita tener dos caminos paralelos
    que se desincronizan a la primera.
    """

    __tablename__ = "predicciones"
    __table_args__ = (
        Index("ix_predicciones_fecha_objetivo", "fecha_objetivo"),
        Index("ix_predicciones_consulta", "objetivo", "horizonte_horas", "fecha_objetivo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_objetivo: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    objetivo: Mapped[str] = mapped_column(String(40), nullable=False, default="precio_bolsa")
    horizonte_horas: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    unidad: Mapped[str] = mapped_column(String(20), nullable=False, default="COP/kWh")

    valor_estimado: Mapped[float] = mapped_column(Float, nullable=False)
    #: Banda de predicción empírica (cuantiles de los residuos de validación).
    #: Un pronóstico sin banda invita a leerlo como certeza; a 720 h eso es
    #: directamente engañoso.
    limite_inferior: Mapped[float | None] = mapped_column(Float)
    limite_superior: Mapped[float | None] = mapped_column(Float)

    valor_real: Mapped[float | None] = mapped_column(
        Float, comment="Se rellena a posteriori para medir el error en producción"
    )
    nombre_modelo: Mapped[str] = mapped_column(String(60), nullable=False)

    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    solicitado_por: Mapped[Usuario | None] = relationship(back_populates="predicciones")

    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Prediccion {self.objetivo} {self.fecha_objetivo:%Y-%m-%d %H:%M} "
            f"= {self.valor_estimado:.2f}>"
        )


# ---------------------------------------------------------------------------
# Módulo territorial
# ---------------------------------------------------------------------------


class DemandaDepartamento(Base):
    """Demanda horaria atribuida a un departamento.

    El origen es ``DemaCome`` por mercado de comercialización; `factor_estimado`
    marca las filas cuyo valor viene de repartir un mercado entre varios
    departamentos (Caribe Mar, Caribe Sol, Bogotá–Cundinamarca...). Guardar esa
    marca en la fila, y no solo en la documentación, es lo que permite que el
    mapa distinga lo medido de lo estimado sin volver a consultar la tabla de
    pesos.
    """

    __tablename__ = "demanda_departamento"
    __table_args__ = (
        UniqueConstraint("fecha_hora", "codigo_dane", name="uq_demanda_depto_hora"),
        Index("ix_demanda_depto_fecha", "fecha_hora"),
        Index("ix_demanda_depto_codigo", "codigo_dane"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    codigo_dane: Mapped[str] = mapped_column(String(2), nullable=False)
    departamento: Mapped[str] = mapped_column(String(60), nullable=False)
    demanda_kwh: Mapped[float] = mapped_column(Float, nullable=False)
    factor_estimado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mercados: Mapped[str | None] = mapped_column(
        String(200), comment="Mercados de XM que aportaron, separados por +"
    )

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Demanda {self.departamento} {self.fecha_hora:%Y-%m-%d %H:%M}>"


class ClimaDepartamento(Base):
    """Clima horario en la capital de cada departamento.

    Se mide en la capital y no en el centroide geométrico porque el clima solo
    interesa aquí en la medida en que explica consumo, y el consumo está donde
    está la gente: el centroide del Chocó cae en selva deshabitada.

    Alimenta el mapa del fenómeno del Niño. La anomalía —cuánto se aparta la
    temperatura de lo normal en ese departamento y ese mes— **no se guarda**: se
    calcula al consultar, con `clima_departamentos.anomalia_mensual`. Guardarla
    obligaría a recalcular la tabla entera cada vez que llegan datos nuevos,
    porque cada hora nueva mueve la normal de su mes.
    """

    __tablename__ = "clima_departamento"
    __table_args__ = (
        UniqueConstraint("fecha_hora", "codigo_dane", name="uq_clima_depto_hora"),
        Index("ix_clima_depto_fecha", "fecha_hora"),
        Index("ix_clima_depto_codigo", "codigo_dane"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    codigo_dane: Mapped[str] = mapped_column(String(2), nullable=False)
    departamento: Mapped[str] = mapped_column(String(60), nullable=False)
    temperatura: Mapped[float | None] = mapped_column(Float, comment="°C")
    precipitacion: Mapped[float | None] = mapped_column(Float, comment="mm")
    humedad_relativa: Mapped[float | None] = mapped_column(Float, comment="%")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Clima {self.departamento} {self.fecha_hora:%Y-%m-%d %H:%M}>"


class ProyeccionUPME(Base):
    """Escenario mensual de demanda nacional proyectada por la UPME."""

    __tablename__ = "proyecciones_upme"
    __table_args__ = (UniqueConstraint("mes", name="uq_proyeccion_upme_mes"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mes: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    escenario_alto: Mapped[float | None] = mapped_column(Float, comment="kWh/mes")
    escenario_medio: Mapped[float | None] = mapped_column(Float, comment="kWh/mes")
    escenario_bajo: Mapped[float | None] = mapped_column(Float, comment="kWh/mes")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<UPME {self.mes:%Y-%m}>"
