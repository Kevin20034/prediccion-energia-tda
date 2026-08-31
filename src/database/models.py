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
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
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

    # --- Variables del mercado (XM) ---------------------------------------
    # Series horarias
    demanda_real: Mapped[float | None] = mapped_column(Float, comment="kWh")
    demanda_comercial: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_total: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_ideal: Mapped[float | None] = mapped_column(
        Float, comment="kWh — generación sin restricciones; proxy de disponibilidad"
    )
    # Desglose por tecnología: requiere agregar la métrica `Gene` por Recurso y
    # mapear cada planta a su tipo. Lo llena el conjunto simulado; con datos
    # reales queda nulo salvo que se implemente ese cruce.
    generacion_hidraulica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    generacion_termica: Mapped[float | None] = mapped_column(Float, comment="kWh")
    disponibilidad_real: Mapped[float | None] = mapped_column(Float, comment="kWh")

    # Series diarias propagadas a resolución horaria
    aportes_hidricos: Mapped[float | None] = mapped_column(Float, comment="kWh")
    volumen_util_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    capacidad_util_energia: Mapped[float | None] = mapped_column(Float, comment="kWh")
    volumen_util_embalse: Mapped[float | None] = mapped_column(
        Float, comment="% de llenado = volumen / capacidad"
    )
    precio_escasez: Mapped[float | None] = mapped_column(Float, comment="COP/kWh")

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

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre_modelo: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    mape: Mapped[float] = mapped_column(Float, nullable=False)
    r2: Mapped[float | None] = mapped_column(Float)

    n_muestras_entrenamiento: Mapped[int] = mapped_column(Integer, nullable=False)
    n_muestras_prueba: Mapped[int] = mapped_column(Integer, nullable=False)
    hiperparametros: Mapped[str | None] = mapped_column(String(1000), comment="JSON serializado")
    ruta_artefacto: Mapped[str | None] = mapped_column(String(500))
    es_mejor: Mapped[bool] = mapped_column(default=False, nullable=False)
    duracion_segundos: Mapped[float | None] = mapped_column(Float)

    ejecutado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ejecucion {self.nombre_modelo} MAE={self.mae:.2f}>"


class Prediccion(Base):
    """Una predicción de precio emitida por un modelo entrenado."""

    __tablename__ = "predicciones"
    __table_args__ = (Index("ix_predicciones_fecha_objetivo", "fecha_objetivo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fecha_objetivo: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    precio_estimado: Mapped[float] = mapped_column(Float, nullable=False, comment="COP/kWh")
    precio_real: Mapped[float | None] = mapped_column(
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
        return f"<Prediccion {self.fecha_objetivo:%Y-%m-%d %H:%M} = {self.precio_estimado:.2f}>"
