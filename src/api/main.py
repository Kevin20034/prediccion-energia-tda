"""Punto de entrada de la API REST.

Arranque:
    uvicorn src.api.main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.routers import auth, datos, entrenar, predicciones, usuarios
from src.core.config import settings
from src.core.logging import configurar_logging, get_logger
from src.database.session import engine

log = get_logger(__name__)

DESCRIPCION = """
API del trabajo de grado **"Análisis de modelos de transacción energética y
desarrollo de un modelo predictivo para la estimación del precio de la energía"**
— Tecnológico de Antioquia.

### Flujo de uso

1. `POST /auth/login` — autenticarse y obtener el token JWT.
2. `POST /datos/ingestar` — descargar histórico de XM y clima *(rol Analista)*.
3. `POST /entrenar` — entrenar y comparar los modelos *(rol Analista)*.
4. `POST /predicciones` — estimar el precio futuro.

### Roles

| Rol | Permisos |
|---|---|
| `ADMINISTRADOR` | Todo, incluida la gestión de usuarios |
| `ANALISTA` | Ingerir datos, entrenar modelos, predecir y consultar |
| `INSTITUCIONAL` | Solo consulta de datos y predicciones |
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Comprobaciones de arranque y cierre ordenado."""
    configurar_logging()
    log.info("Iniciando API (entorno=%s)", settings.APP_ENV)

    # Verificación temprana de la conexión: con Neon el primer acceso despierta
    # el cómputo, así que conviene pagar ese arranque en frío aquí y no en la
    # primera petición de un usuario.
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        log.info("Conexión con la base de datos verificada")
    except Exception as exc:  # noqa: BLE001 - queremos arrancar igualmente
        log.error("No se pudo conectar a la base de datos: %s", exc)
        log.error("Revisa DATABASE_URL en el archivo .env")

    yield

    engine.dispose()
    log.info("API detenida")


app = FastAPI(
    title="API — Predicción del precio de la energía (TdeA)",
    description=DESCRIPCION,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: en desarrollo se permite cualquier origen para que el frontend local
# pueda consumir la API. En producción hay que restringirlo al dominio real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.es_produccion else ["https://tu-dominio.edu.co"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(datos.router)
app.include_router(entrenar.router)
app.include_router(predicciones.router)
app.include_router(usuarios.router)


@app.get("/", tags=["Estado"], summary="Información de la API")
def raiz() -> dict[str, str]:
    return {
        "proyecto": "Predicción del precio de la energía — Tecnológico de Antioquia",
        "version": app.version,
        "documentacion": "/docs",
        "estado": "/salud",
    }


@app.get("/salud", tags=["Estado"], summary="Health check")
def salud() -> dict[str, str]:
    """Comprueba que la API responde y que la base de datos está accesible."""
    try:
        with engine.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        estado_bd = "ok"
    except Exception as exc:  # noqa: BLE001
        estado_bd = f"error: {type(exc).__name__}"

    return {"api": "ok", "base_datos": estado_bd, "entorno": settings.APP_ENV}
