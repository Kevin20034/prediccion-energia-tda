# Predicción del precio de la energía — Tecnológico de Antioquia

Software de analítica predictiva que recolecta datos del mercado eléctrico
colombiano (XM) y variables climáticas, los procesa, entrena varios modelos de
Machine Learning para estimar el precio de bolsa y expone los resultados
mediante una API REST.

Trabajo de grado: *«Análisis de modelos de transacción energética y desarrollo
de un modelo predictivo para la estimación del precio de la energía en el
Tecnológico de Antioquia»*.

---

## Índice

- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración (`.env`)](#configuración-env)
- [Base de datos](#base-de-datos)
- [Puesta en marcha](#puesta-en-marcha)
- [Uso de la API](#uso-de-la-api)
- [Fuentes de datos](#fuentes-de-datos)
- [Modelos predictivos](#modelos-predictivos)
- [Resultados obtenidos](#resultados-obtenidos)
- [Pruebas](#pruebas)
- [Decisiones técnicas](#decisiones-técnicas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Problemas frecuentes](#problemas-frecuentes)

---

## Arquitectura

Cliente-servidor en tres capas, con el motor analítico como módulo aparte:

```
┌──────────────┐   HTTPS/JSON   ┌──────────────────┐   SQLAlchemy   ┌─────────────┐
│  Frontend    │ ─────────────► │   API REST       │ ─────────────► │ PostgreSQL  │
│  (pendiente) │ ◄───────────── │   FastAPI + JWT  │ ◄───────────── │   (Neon)    │
└──────────────┘                └────────┬─────────┘                └─────────────┘
                                         │ invoca
                                         ▼
                                ┌──────────────────┐     ┌──────────────────────┐
                                │ Motor analítico  │ ◄── │ XM · Open-Meteo·NOAA │
                                │ LR·RF·XGB·LSTM   │     │  (fuentes externas)  │
                                └──────────────────┘     └──────────────────────┘
```

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Recolección | `src/data_collection/` | Descarga de XM, Open-Meteo y NOAA |
| Procesamiento | `src/processing/` | Limpieza, imputación, *feature engineering* |
| Predictivo | `src/models/` | Entrenamiento, evaluación y selección de modelos |
| API | `src/api/` | Endpoints REST, autenticación y control de acceso |
| Persistencia | `src/database/` | Modelos ORM y sesiones |
| Administrativo | `src/api/routers/usuarios.py` | Usuarios y roles |

---

## Requisitos

- **Python 3.11 o superior** (probado en 3.13)
- Una base de datos **PostgreSQL**. El proyecto está configurado para
  [Neon](https://neon.tech) (plan gratuito suficiente), pero funciona con
  cualquier PostgreSQL.
- Conexión a internet para descargar datos reales (hay respaldo simulado si no).

No hace falta instalar PostgreSQL en local: Neon es un servicio gestionado.

---

## Instalación

```bash
git clone <url-del-repositorio>
cd energia-tda

# Entorno virtual
python -m venv .venv

# Activarlo
.venv\Scripts\activate          # Windows (PowerShell/CMD)
source .venv/bin/activate       # Linux / macOS

# Dependencias
pip install --upgrade pip
pip install -r requirements.txt
```

La instalación descarga PyTorch (~200 MB), así que la primera vez tarda unos
minutos.

---

## Configuración (`.env`)

Copia la plantilla y rellena tus valores:

```bash
copy .env.example .env      # Windows
cp .env.example .env        # Linux / macOS
```

| Variable | Para qué sirve |
|---|---|
| `DATABASE_URL` | Conexión de la API. Endpoint **pooled** de Neon (el que lleva `-pooler`). |
| `DATABASE_URL_DIRECT` | Conexión de Alembic. Endpoint **directo** (sin `-pooler`). |
| `JWT_SECRET_KEY` | Clave de firma de los tokens. Genera una propia (ver abajo). |
| `JWT_ALGORITHM` | Algoritmo de firma. `HS256` por defecto. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Vigencia del token. 60 por defecto. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Administrador que crea `scripts/seed.py`. |
| `XM_API_URL` | `https://servapibi.xm.com.co`. **No requiere API key.** |
| `XM_API_KEY` | Vacía. Reservada por si se migra al portal autenticado de XM. |
| `CLIMA_LATITUD` / `CLIMA_LONGITUD` | Coordenadas para el clima. Medellín por defecto. |
| `APP_ENV` | `development` o `production`. En producción, CORS se restringe. |

Genera una clave JWT decente:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

> **El `.env` está en `.gitignore` y no debe subirse nunca al repositorio.**
> Solo se versiona `.env.example`, sin credenciales reales.

### Obtener las cadenas de Neon

1. Entra en [console.neon.tech](https://console.neon.tech) y crea un proyecto.
2. En **Connection Details** copia la cadena de conexión.
3. Neon ofrece dos hostnames. El que incluye `-pooler` va en `DATABASE_URL`; el
   mismo hostname **sin** `-pooler` va en `DATABASE_URL_DIRECT`.
4. Cambia el prefijo `postgresql://` por `postgresql+psycopg2://` en ambas.
5. Conserva `?sslmode=require` al final. Es obligatorio.

---

## Base de datos

Crear el esquema:

```bash
alembic upgrade head
```

Crear los usuarios iniciales:

```bash
python -m scripts.seed
```

Esto crea tres cuentas, una por rol:

| Rol | Email | Contraseña |
|---|---|---|
| Administrador | `admin@tda.edu.co` | `Admin123*` |
| Analista | `analista@tda.edu.co` | `Analista123*` |
| Institucional | `consulta@tda.edu.co` | `Consulta123*` |

Cámbialas antes de cualquier despliegue real.

### Migraciones posteriores

Tras modificar `src/database/models.py`:

```bash
alembic revision --autogenerate -m "descripción del cambio"
alembic upgrade head        # aplicar
alembic downgrade -1        # revertir la última
alembic current             # ver la revisión activa
```

---

## Puesta en marcha

```bash
# 1. Descargar datos históricos (2 años)
python -m scripts.ingestar_datos --inicio 2024-01-01 --fin 2025-12-31

# 2. Entrenar y comparar los modelos
python -m scripts.entrenar

# 3. Levantar la API
uvicorn src.api.main:app --reload
```

Documentación interactiva: **http://127.0.0.1:8000/docs**

### Otros comandos

```bash
# Entrenar solo algunos modelos (la LSTM es la lenta)
python -m scripts.entrenar --modelos regresion_lineal random_forest xgboost

# Cambiar el horizonte de predicción y el criterio de selección
python -m scripts.entrenar --horizonte 48 --criterio mae

# Entrenar desde un CSV, sin base de datos
python -m scripts.entrenar --csv src/data_collection/samples/xm_historico_ejemplo.csv

# Regenerar el conjunto simulado de respaldo
python scripts/generar_datos_ejemplo.py --anios 3

# Análisis exploratorio
jupyter notebook notebooks/01_eda.ipynb
```

---

## Uso de la API

### 1. Autenticarse

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -d "username=admin@tda.edu.co&password=Admin123*"
```

```json
{ "access_token": "eyJhbGci...", "token_type": "bearer",
  "expira_en_minutos": 60, "rol": "ADMINISTRADOR" }
```

### 2. Usar el token

```bash
curl http://127.0.0.1:8000/datos?limite=10 \
  -H "Authorization: Bearer eyJhbGci..."
```

### Endpoints

| Método | Ruta | Rol mínimo | Descripción |
|---|---|---|---|
| `POST` | `/auth/login` | — | Obtener token JWT |
| `GET` | `/auth/yo` | Institucional | Perfil propio |
| `GET` | `/datos` | Institucional | Datos históricos (con filtros y paginación) |
| `GET` | `/datos/resumen` | Institucional | Estadísticos descriptivos |
| `POST` | `/datos/ingestar` | Analista | Descargar y guardar datos |
| `POST` | `/entrenar` | Analista | Entrenar y comparar modelos |
| `GET` | `/entrenamientos` | Analista | Histórico de entrenamientos |
| `GET` | `/predicciones` | Institucional | Consultar predicciones |
| `POST` | `/predicciones` | Institucional | Generar predicciones |
| `GET` | `/usuarios` | Administrador | Listar usuarios |
| `POST` | `/usuarios` | Administrador | Crear usuario |
| `PATCH` | `/usuarios/{id}/rol` | Administrador | Cambiar rol |
| `PATCH` | `/usuarios/{id}/estado` | Administrador | Activar/desactivar |
| `GET` | `/salud` | — | Health check |

El **Administrador** hereda todos los permisos de los demás roles.

---

## Fuentes de datos

Las tres son **públicas y gratuitas**, ninguna requiere API key.

### XM — `https://servapibi.xm.com.co`

Operador del mercado eléctrico colombiano. Dos endpoints con formatos distintos:

- `POST /hourly` → `Items[].HourlyEntities[].Values.Hour01..Hour24`
- `POST /daily` → `Items[].DailyEntities[].Value`

Métricas utilizadas (todas verificadas contra la API en vivo):

| MetricId | Periodo | Variable |
|---|---|---|
| `PrecBolsNaci` | horario | Precio de bolsa nacional — **objetivo** |
| `DemaReal` | horario | Demanda real |
| `DemaCome` | horario | Demanda comercial |
| `Gene` | horario | Generación total |
| `GeneIdea` | horario | Generación ideal (sin restricciones) |
| `AporEner` | diario | Aportes hídricos de energía |
| `VoluUtilDiarEner` | diario | Volumen útil de embalses |
| `CapaUtilDiarEner` | diario | Capacidad útil de embalses |
| `PrecEscaAct` | diario | Precio de escasez de activación |

Las series diarias se propagan a las 24 horas del día (un volumen de embalse es
un estado diario, no una magnitud horaria). De `VoluUtilDiarEner` y
`CapaUtilDiarEner` se deriva `volumen_util_embalse` como porcentaje de llenado.

> **Nota.** El desglose de generación por tecnología (hidráulica frente a
> térmica) requiere consultar `Gene` por `Recurso` y mapear cada planta a su
> tipo. No está implementado: esas columnas quedan nulas con datos reales y solo
> las llena el conjunto simulado. Es una ampliación natural del trabajo.

### Open-Meteo — reanálisis climático histórico

Temperatura, precipitación y humedad relativa horarias para las coordenadas
configuradas. Gratuita para uso no comercial y sin registro.

### NOAA CPC — índice ONI

El *Oceanic Niño Index* es el estándar internacional para clasificar El Niño y
La Niña. Se descarga el fichero oficial (media móvil trimestral) y se clasifica
según el criterio de la NOAA: `ONI ≥ +0.5` → El Niño, `ONI ≤ −0.5` → La Niña.

### Respaldo simulado

Si XM no responde, el cliente cae automáticamente a
`src/data_collection/samples/xm_historico_ejemplo.csv`, un conjunto **sintético**
generado por `scripts/generar_datos_ejemplo.py`. Sirve para que el proyecto sea
siempre ejecutable, pero **no debe usarse para conclusiones del trabajo de
grado**. La columna `fuente` distingue `XM` de `SIMULADO`.

---

## Modelos predictivos

Los cuatro implementan la misma interfaz (`src/models/base.py`), de modo que el
orquestador los recorre en bucle y añadir uno nuevo no obliga a tocar nada más.

| Modelo | Librería | Papel en el estudio |
|---|---|---|
| Regresión Lineal (Ridge) | scikit-learn | Línea base. Los demás deben superarla. |
| Random Forest | scikit-learn | No linealidades e interacciones. |
| XGBoost | xgboost | *Gradient boosting*, con parada temprana. |
| LSTM | PyTorch | Red recurrente sobre la secuencia completa. |

### Variables predictoras (58 en total)

- **Calendario cíclico**: hora, día de semana y mes codificados con seno/coseno.
  La hora 23 y la hora 0 son adyacentes; sin esta codificación distarían 23.
- **Rezagos del precio**: 1, 2, 3, 6, 12, 24, 48 y 168 horas.
- **Ventanas móviles**: media, desviación, máximo y mínimo a 24 h, 168 h y 720 h.
- **Exógenas**: demanda, hidrología, margen de reserva, brecha de generación,
  distancia al precio de escasez, clima y fenómeno ENSO.

### Métricas

| Métrica | Por qué está |
|---|---|
| **MAE** | En COP/kWh, directamente interpretable. |
| **RMSE** | Penaliza los errores grandes. Es el criterio de selección por defecto. |
| **MAPE** | Adimensional, comparable entre periodos con niveles distintos. |
| **R²** | Bondad de ajuste, como referencia. |

### Validez metodológica

Dos salvaguardas, ambas cubiertas por pruebas automáticas:

- **Sin fuga de información**: todos los rezagos usan `shift()` hacia el pasado
  y las ventanas móviles se calculan sobre series ya desplazadas. Ninguna
  variable del instante *t* entra en la predicción de *t*.
- **Partición cronológica**: el conjunto de prueba es siempre el tramo final de
  la serie. Un `train_test_split` aleatorio metería futuro en el entrenamiento y
  produciría métricas optimistas que no se sostienen en producción.

---

## Resultados obtenidos

Ejecución real sobre datos de XM de 2024-2025 (17.544 registros horarios),
horizonte de 24 horas, 13.881 muestras de entrenamiento y 3.471 de prueba:

| Modelo | MAE | RMSE | MAPE (%) | R² | Tiempo (s) |
|---|---|---|---|---|---|
| **Random Forest** | **95.15** | **127.28** | 52.87 | **0.332** | 3.5 |
| XGBoost | 96.54 | 129.16 | 54.58 | 0.312 | 4.1 |
| Regresión Lineal | 99.03 | 133.47 | 49.39 | 0.266 | 0.1 |
| LSTM | 93.07 | 140.16 | **35.55** | 0.190 | 96.9 |

Variables más influyentes según el modelo ganador: `ratio_precio_escasez`,
`precio_media_24h`, `precio_lag_1`, `precio_lag_2`, `precio_media_168h`.

### Lectura honesta de estos números

Conviene discutirlos en el trabajo en lugar de presentarlos sin más:

- **Un R² de 0,33 es modesto**, pero no anómalo: predecir el precio *spot* a 24
  horas es intrínsecamente difícil, porque depende de decisiones de oferta y de
  eventos que no están en los datos históricos.
- **Los cuatro modelos quedan muy juntos.** Random Forest gana por poco a
  XGBoost, y la Regresión Lineal se queda a un 5 % del ganador. Eso sugiere que
  la mayor parte de la señal aprovechable es lineal y viene de los rezagos.
- **La LSTM tiene el mejor MAE y MAPE pero el peor RMSE.** No es contradictorio:
  acierta mejor en el caso típico y falla más en los picos. Con 96 segundos de
  entrenamiento frente a 3,5 del Random Forest, la relación coste-beneficio no
  la favorece en este conjunto.
- **Las variables de precio dominan sobre las exógenas.** El clima y la
  hidrología aportan menos de lo que la hipótesis inicial sugería, al menos en
  el horizonte de 24 horas y con solo dos años de datos.

Vías de mejora razonables: ampliar el histórico a 5-10 años (cubriría un ciclo
ENSO completo), incorporar el desglose de generación por tecnología, y probar
horizontes más cortos (1-6 horas), donde la autocorrelación es mucho mayor.

---

## Pruebas

```bash
pytest                              # todas
pytest -v                           # detalle
pytest --cov=src --cov-report=html  # con cobertura
pytest tests/test_processing.py     # un archivo
```

Las pruebas corren contra **SQLite en memoria**: son instantáneas, no dependen
de la red y no tocan la base real. El esquema no usa tipos exclusivos de
PostgreSQL, así que la compatibilidad es total.

Cobertura: limpieza e imputación, ausencia de fuga de información, partición
cronológica, métricas, contrato común de los modelos, serialización,
autenticación, autorización por rol y endpoints principales.

> Para probar contra PostgreSQL de verdad, Neon permite crear un *branch* de la
> base (copia instantánea, como una rama de git) y apuntar `DATABASE_URL` a él.

---

## Decisiones técnicas

**PyTorch en lugar de TensorFlow para la LSTM.** TensorFlow abandonó el soporte
nativo de GPU en Windows a partir de la 2.11 y su instalación en Python 3.13 es
frágil; la rueda pesa ~600 MB frente a ~200 MB de PyTorch CPU. Para un trabajo
que el jurado debe poder instalar en cualquier equipo, eso pesa más que las
diferencias de API, que son mínimas para una LSTM.

**PyJWT en lugar de python-jose.** Es lo que usa hoy la documentación oficial de
FastAPI. `python-jose` lleva años sin *releases* y acumula CVEs. La API es
equivalente para HS256. *(Esto se aparta del enunciado original, que pedía
`python-jose`; el cambio es deliberado y por seguridad.)*

**bcrypt directo en lugar de passlib.** Passlib 1.7.4 (de 2020, sin
mantenimiento) se rompe al leer `bcrypt.__about__` con bcrypt ≥ 4.1. Usar
`bcrypt` directamente son seis líneas y no arrastra el fallo.

**Enums no nativos en PostgreSQL.** Los enums se declaran con
`native_enum=False`, así que se materializan como `VARCHAR` + `CHECK`. Alterar
un enum nativo de PostgreSQL en una migración es doloroso
(`ALTER TYPE ... ADD VALUE` no es transaccional), y así las mismas migraciones
sirven para SQLite en las pruebas.

**Ridge en lugar de mínimos cuadrados ordinarios.** Las predictoras están muy
correlacionadas entre sí (los rezagos lo están por construcción). Con
multicolinealidad, OLS da coeficientes inestables; la penalización L2 los
estabiliza.

**Winsorizing con umbral IQR de 3.0, no 1.5.** En el mercado energético los
picos de escasez son reales, no errores de medición. Recortar con el 1.5 clásico
destruiría justo la señal que el modelo debe aprender. Además se recorta en
lugar de eliminar filas, para no abrir huecos en la serie.

**Ingesta idempotente.** Se usa `ON CONFLICT DO UPDATE` sobre `fecha_hora`:
reingestar un rango ya descargado actualiza los valores en vez de fallar. Es
necesario porque XM publica correcciones con retraso.

**Configuración de Neon.** Ver [Problemas frecuentes](#problemas-frecuentes).

---

## Estructura del proyecto

```
energia-tda/
├── .env                      # credenciales reales (NO se versiona)
├── .env.example              # plantilla sin secretos
├── requirements.txt
├── pyproject.toml            # configuración de pytest, ruff y mypy
├── alembic.ini
│
├── alembic/versions/         # migraciones
│
├── src/
│   ├── core/                 # config, seguridad (JWT + bcrypt), logging
│   ├── database/             # session.py (pool de Neon), models.py (ORM)
│   ├── data_collection/      # xm_client, clima_client, samples/
│   ├── processing/           # limpieza.py, features.py
│   ├── models/               # base + 4 modelos + métricas + entrenamiento
│   └── api/                  # main, deps, schemas/, routers/
│
├── scripts/
│   ├── seed.py                     # usuarios iniciales
│   ├── ingestar_datos.py           # descarga y persiste
│   ├── entrenar.py                 # entrena y compara
│   └── generar_datos_ejemplo.py    # conjunto simulado de respaldo
│
├── tests/                    # pytest sobre SQLite en memoria
├── notebooks/01_eda.ipynb    # análisis exploratorio
└── frontend/                 # pendiente (ver frontend/README.md)
```

---

## Problemas frecuentes

**`SSL connection has been closed unexpectedly`**

Neon suspende el cómputo tras unos minutos de inactividad y corta las conexiones
abiertas. Ya está resuelto con `pool_pre_ping=True` y `pool_recycle=300` en
`src/database/session.py`. Si aparece, verifica que no se haya modificado esa
configuración.

**La primera petición tarda varios segundos**

Es el arranque en frío de Neon: la base estaba suspendida y debe despertar. Es
normal en el plan gratuito y solo ocurre tras un rato de inactividad.

**Alembic falla con un error de *prepared statement***

Estás usando el endpoint *pooled* para las migraciones. `DATABASE_URL_DIRECT`
debe apuntar al hostname **sin** `-pooler`.

**`ValidationError` al arrancar**

Falta una variable obligatoria en el `.env`, o el archivo no existe. Cópialo de
`.env.example`. El fallo es intencionado: es mejor caer al arrancar con un
mensaje claro que reventar más tarde con un `None` inesperado.

**XM devuelve `400 Id de Métrica no encontrada`**

Esa métrica no existe en ese endpoint. Las horarias van a `/hourly` y las
diarias a `/daily`; no son intercambiables. El cliente omite las métricas que
XM rechace y continúa con el resto.

**`No hay modelo entrenado`**

`POST /predicciones` necesita un modelo previo. Ejecuta `python -m
scripts.entrenar` o llama a `POST /entrenar`.

**Las columnas de generación hidráulica/térmica salen vacías**

Es el comportamiento esperado con datos reales: requieren un cruce por recurso
que no está implementado. Ver la nota en [Fuentes de datos](#fuentes-de-datos).
