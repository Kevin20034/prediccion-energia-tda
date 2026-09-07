"""Punto de entrada de la API REST.

Arranque:
    uvicorn src.api.main:app --reload

Documentación interactiva en http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from src.api.planificador import planificador
from src.api.routers import (
    auth,
    datos,
    entrenar,
    estado,
    panorama,
    predicciones,
    territorio,
    usuarios,
)
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
3. `POST /departamentos/ingestar` — demanda por mercado, repartida por departamento.
4. `POST /entrenar` — entrenar y comparar los modelos, por objetivo y horizonte.
5. `GET /pronostico` — histórico + pronóstico con banda de predicción.
6. `GET /modelos/comparacion` — qué modelo gana en cada horizonte y por qué.

### Objetivos y horizontes

El sistema pronostica dos variables —`precio_bolsa` y `demanda_real`— en tres
horizontes: **24 h**, **7 días** (168 h) y **30 días** (720 h). Cada combinación
tiene su propio modelo entrenado con estrategia *direct multi-step*.

### Roles

| Rol | Permisos |
|---|---|
| `ADMINISTRADOR` | Todo, incluida la gestión de usuarios |
| `ANALISTA` | Ingerir datos, entrenar modelos, predecir y consultar |
| `INSTITUCIONAL` | Solo consulta de datos, mapa y predicciones |
"""


def _precargar_modelos() -> None:
    """Deja los artefactos entrenados en memoria antes de la primera petición.

    Un bosque aleatorio serializado tarda varios segundos en leerse del disco.
    Si esa lectura ocurre en la primera petición de pronóstico, el primer
    usuario que abre el tablero paga toda la espera. Se hace aquí, en un hilo
    aparte para no retrasar el arranque del servidor.
    """
    from src.models.entrenamiento import artefactos_disponibles

    try:
        artefactos = artefactos_disponibles()
    except Exception as exc:  # noqa: BLE001 - es una optimización, no un requisito
        log.warning("No se pudieron precargar los modelos: %s", exc)
        return

    log.info(
        "Modelos precargados: %s",
        ", ".join(f"{a.objetivo}/{a.horizonte}h" for a in artefactos) or "ninguno",
    )


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

    calentamiento = threading.Thread(target=_precargar_modelos, daemon=True)
    calentamiento.start()

    # Ingesta automática. Apagada por defecto: encenderla en dos procesos a la
    # vez —o con `--reload`, que levanta dos— haría que ambos descargasen lo
    # mismo en paralelo.
    tarea_ingesta = None
    if settings.INGESTA_AUTOMATICA:
        _registrar_trabajos()
        tarea_ingesta = asyncio.create_task(planificador.ciclo())
    else:
        log.info("Ingesta automatica desactivada (INGESTA_AUTOMATICA=false)")

    yield

    if tarea_ingesta is not None:
        tarea_ingesta.cancel()
        with suppress(asyncio.CancelledError):
            await tarea_ingesta

    engine.dispose()
    log.info("API detenida")


def _registrar_trabajos() -> None:
    """Da de alta las fuentes que el planificador debe mantener al día.

    Se importa aquí dentro y no arriba porque estos módulos arrastran pandas y
    los clientes de red: cargarlos al importar la API retrasaría el arranque
    incluso cuando la ingesta automática está apagada, que es lo habitual.
    """
    from src.api.trabajos_ingesta import TRABAJOS

    planificador.trabajos = list(TRABAJOS)
    log.info(
        "Ingesta automatica activada cada %d min · fuentes: %s",
        settings.INGESTA_INTERVALO_MINUTOS,
        ", ".join(nombre for nombre, _ in TRABAJOS),
    )


app = FastAPI(
    title="API — Predicción Energía TdeA",
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
app.include_router(panorama.router)
app.include_router(datos.router)
app.include_router(estado.router)
app.include_router(entrenar.router)
app.include_router(predicciones.router)
app.include_router(territorio.router)
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
