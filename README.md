# Pronóstico del mercado eléctrico colombiano — Tecnológico de Antioquia

Plataforma de analítica predictiva sobre el Sistema Interconectado Nacional.
Recolecta datos horarios de XM y variables climáticas, entrena y compara nueve
modelos, y publica en una interfaz web el pronóstico del **precio de bolsa** y de
la **demanda** a tres horizontes —24 horas, 7 días y 30 días— junto con un mapa
interactivo de la demanda por departamento.

Trabajo de grado: *«Análisis de modelos de transacción energética y desarrollo
de un modelo predictivo para la estimación del precio de la energía en el
Tecnológico de Antioquia»*.

---

## Índice

- [Qué hace](#qué-hace)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración (`.env`)](#configuración-env)
- [Base de datos](#base-de-datos)
- [Puesta en marcha](#puesta-en-marcha)
- [Interfaz web](#interfaz-web)
- [Uso de la API](#uso-de-la-api)
- [Fuentes de datos](#fuentes-de-datos)
- [Demanda por departamento](#demanda-por-departamento)
- [Modelos predictivos](#modelos-predictivos)
- [Resultados obtenidos](#resultados-obtenidos)
- [Pruebas](#pruebas)
- [Decisiones técnicas](#decisiones-técnicas)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Problemas frecuentes](#problemas-frecuentes)

---

## Qué hace

- **Ingesta 34 variables horarias** del mercado eléctrico desde la API pública de
  XM, más clima (Open-Meteo) e índice ENSO (NOAA).
- **Pronostica dos objetivos** —precio de bolsa y demanda real— en **tres
  horizontes**, con un modelo entrenado específicamente para cada combinación.
- **Compara nueve modelos de cinco familias** contra un pronóstico ingenuo
  estacional, y dice cuál gana en cada horizonte y por cuánto.
- **Acompaña cada pronóstico de una banda de predicción** calibrada con los
  residuos reales del modelo.
- **Reparte la demanda comercial de los 29 mercados de XM sobre los 33
  departamentos** del DANE y la publica en un mapa coroplético interactivo.
- **Contrasta la demanda observada con la proyección oficial de la UPME.**

## Arquitectura

Cliente-servidor en tres capas, con el motor analítico como módulo aparte:

```
┌──────────────┐   HTTPS/JSON   ┌──────────────────┐   SQLAlchemy   ┌─────────────┐
│  Frontend    │ ─────────────► │   API REST       │ ─────────────► │ PostgreSQL  │
│ React + Vite │ ◄───────────── │   FastAPI + JWT  │ ◄───────────── │   (Neon)    │
└──────────────┘                └────────┬─────────┘                └─────────────┘
                                         │ invoca
                                         ▼
                    ┌────────────────────────────────┐   ┌──────────────────────┐
                    │ Motor analítico                │ ◄─│ XM · Open-Meteo·NOAA │
                    │ baseline·Ridge·ElasticNet·RF   │   │  (fuentes externas)  │
                    │ XGB·LightGBM·SARIMAX·HW·LSTM   │   └──────────────────────┘
                    └────────────────────────────────┘
```

| Capa | Módulo | Responsabilidad |
|---|---|---|
| Recolección | `src/data_collection/` | Transporte de XM, series del sistema, territorio, UPME, clima |
| Procesamiento | `src/processing/` | Limpieza, imputación, *feature engineering* |
| Predictivo | `src/models/` | Entrenamiento, evaluación y selección de modelos |
| API | `src/api/` | Endpoints REST, autenticación y control de acceso |
| Persistencia | `src/database/` | Modelos ORM, sesiones y escritura idempotente |
| Presentación | `frontend/` | Tablero React con mapa y gráficas interactivas |

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
# 1. Descargar el histórico del sistema (unos 15 min para 3 años)
python -m scripts.ingestar_datos --inicio 2023-01-01

# 2. Descargar la demanda por departamento y los escenarios de la UPME
python -m scripts.ingestar_territorio --inicio 2023-01-01

# 3. Entrenar la matriz completa: 2 objetivos × 3 horizontes
python -m scripts.entrenar --objetivo precio_bolsa demanda_real --todos-los-horizontes

# 4. Levantar la API
uvicorn src.api.main:app --reload

# 5. Levantar la interfaz (en otra terminal)
cd frontend && npm install && npm run dev
```

Interfaz: **http://127.0.0.1:5173** · Documentación de la API:
**http://127.0.0.1:8000/docs**

El paso 3 tarda unos minutos con los modelos de producción. Con
`--todos-los-modelos` sube a cerca de una hora, porque incluye la LSTM y
SARIMAX. Para una demostración rápida basta con `python -m scripts.entrenar`,
que entrena solo el precio a 24 horas.

### Otros comandos

```bash
# La comparación completa entre las cinco familias (la del trabajo de grado)
python -m scripts.entrenar --todos-los-modelos --todos-los-horizontes

# Entrenar solo algunos modelos
python -m scripts.entrenar --modelos baseline_estacional xgboost lightgbm

# Otro objetivo, otro horizonte, otro criterio de selección
python -m scripts.entrenar --objetivo demanda_real --horizonte 168 --criterio mae

# Validación walk-forward (multiplica el tiempo por el número de pliegues)
python -m scripts.entrenar --pliegues 3

# Ingesta rápida, sin el desglose de generación planta a planta
python -m scripts.ingestar_datos --dias 30 --sin-tecnologias

# Medir el error de las predicciones ya emitidas contra lo que de verdad pasó
python -m scripts.evaluar_produccion

# Entrenar desde un CSV, sin base de datos
python -m scripts.entrenar --csv src/data_collection/samples/xm_historico_ejemplo.csv

# Análisis exploratorio
jupyter notebook notebooks/01_eda.ipynb
```

---

## Interfaz web

Las secciones son enlazables por URL (`#inicio`, `#mapa`, `#pronostico`,
`#modelos`, `#datos`) y **dependen del rol**.

### Vista de usuario (rol Institucional)

Dos secciones. Quien entra a consultar el estado del mercado no necesita
comparar RMSE entre modelos ni lanzar ingestas: enseñarle esas pantallas no le da
poder, le da ruido.

| Sección | Qué muestra |
|---|---|
| **Inicio** | Una sola página que se lee de arriba abajo y responde en ese orden a tres preguntas: *cómo está ahora* (titular en lenguaje llano y la cifra del momento), *hacia dónde va* (tres plazos y la gráfica del elegido) y *por qué* (embalses, mezcla de generación y territorio). |
| **Mapa** | Coroplético de la demanda por departamento, con panel de detalle, serie histórica, hora punta y ranking. |

El titular lo redacta el servidor, no la interfaz: *«El precio de la energía
subirá alrededor de un 4 % en las próximas 24 horas»*. Es la diferencia entre
mostrar un número y decir lo que significa.

### Vista técnica (roles Analista y Administrador)

Las dos anteriores más tres:

| Sección | Qué muestra |
|---|---|
| **Pronóstico** | La costura entre lo medido y lo inferido, con banda de incertidumbre, para el objetivo y horizonte elegidos. Debajo, mezcla de generación y curva por hora del día. |
| **Modelos** | Tabla comparativa, gráfica de RMSE con la línea del pronóstico ingenuo, ganador por horizonte e importancia de variables por permutación. |
| **Datos** | Explorador de series con hasta seis variables, cuatro resoluciones, y el contraste con los escenarios de la UPME. |

### Lenguaje visual

Codifica una sola idea en todas partes: **turquesa es lo medido, ámbar es lo
inferido**. La regla bajo la barra superior no es un adorno: su relleno es el
nivel de los embalses del sistema, que es el contexto de cualquier cifra del
mercado colombiano.

El movimiento sirve a la lectura y no al espectáculo: la curva de carga viva en
el acceso y en la portada, las cifras que cuentan hasta su valor para dar
sensación de magnitud, y el revelado por bloques al desplazarse, que hace que la
página se cuente en lugar de presentarse entera de golpe. Todo respeta
`prefers-reduced-motion`, y con esa preferencia activa se ve exactamente el
mismo contenido, no una versión recortada.

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
| `GET` | `/datos/catalogo` | Institucional | Variables graficables, con unidad y disponibilidad |
| `GET` | `/datos/series` | Institucional | Hasta 6 series agregadas por hora, día, semana o mes |
| `GET` | `/datos/perfil-horario` | Institucional | Media por hora del día, laborables vs. fin de semana |
| `POST` | `/datos/ingestar` | Analista | Descargar y guardar datos de XM y clima |
| `GET` | `/departamentos/mapa` | Institucional | Demanda por departamento para el mapa |
| `GET` | `/departamentos/{codigo}/serie` | Institucional | Serie de un departamento |
| `POST` | `/departamentos/ingestar` | Analista | Descargar y repartir la demanda por mercado |
| `GET` | `/upme/escenarios` | Institucional | Proyección UPME frente a lo observado |
| `POST` | `/upme/ingestar` | Analista | Descargar los escenarios de la UPME |
| `POST` | `/entrenar` | Analista | Entrenar y comparar modelos |
| `GET` | `/entrenamientos` | Institucional | Histórico de entrenamientos |
| `GET` | `/modelos/comparacion` | Institucional | Ganador por horizonte, veredicto e importancias |
| `GET` | `/pronostico` | Institucional | Histórico + pronóstico con banda, en una llamada |
| `GET` | `/pronostico/horizontes` | Institucional | Qué combinaciones tienen modelo entrenado |
| `GET` | `/predicciones` | Institucional | Consultar predicciones emitidas |
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

Operador del mercado eléctrico colombiano. Cuatro endpoints con formatos
distintos, todos sin API key:

- `POST /hourly` → `Items[].HourlyEntities[].Values.Hour01..Hour24`
- `POST /daily` → `Items[].DailyEntities[].Value`
- `POST /monthly` → `Items[].MonthlyEntities[].Value`
- `POST /lists` → catálogos (recursos, agentes, embalses, ríos, métricas)

Cada consulta está limitada a 31 días para las series horarias y diarias, así
que los rangos se trocean y se descargan **en paralelo** (`src/data_collection/xm_api.py`).

**Métricas horarias del sistema** (20): precio de bolsa —objetivo—, precio TX1,
precio de oferta máximo, costo marginal del despacho, precios promedio de
contratos regulado y no regulado; demanda real, comercial, regulada y no
regulada; generación total e ideal; pérdidas, restricciones con y sin alivio,
factor de emisión de CO₂, importaciones y exportaciones; compras en bolsa y en
contratos.

**Métricas diarias** (14), propagadas a las 24 horas del día porque un estado
diario es el mismo durante todo el día: aportes hídricos y su media histórica,
porcentaje de aportes, volumen y capacidad útiles de embalse, porcentaje de
llenado, vertimientos, la familia de precios de escasez, demanda del SIN,
demanda máxima de potencia, precio de bolsa ponderado y delta nacional.

**Desglose de generación por tecnología.** XM publica la generación *planta a
planta*, no por fuente. Se descarga `Gene` por `Recurso` y se cruza con el
catálogo `ListadoRecursos`, que trae el `Type` de cada planta, para agregar cinco
columnas: hidráulica, térmica, solar, eólica y cogeneración. La participación
hidráulica es la variable estructural que más explica el precio en Colombia.

**Métricas mensuales**: los tres escenarios de demanda proyectada de la UPME
(`EscDemUPMEAlto`, `EscDemUPMEMedio`, `EscDemUPMEBajo`).

> **Métricas descartadas.** `PrecEscaAct` dejó de publicarse y `PrecTransBolsa`
> devuelve vacío; el cliente usa `PrecEsca` en su lugar. Se comprobó una a una
> contra la API en vivo antes de incluirlas.

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

## Demanda por departamento

La API pública de XM **no tiene entidad "Departamento"**. Lo más cercano es
`DemaCome` desagregada por `MercadoComercializacion`: 29 mercados con demanda
horaria real, cuya delimitación es administrativa y no política.

`src/data_collection/departamentos.py` traduce esos mercados a los 33
departamentos del DANE con una tabla de pesos explícita:

- La mayoría son **atribución directa** (ANTIOQUIA → Antioquia, peso 1,0). Varios
  mercados pequeños —Cartago, Tuluá, Pereira, Ruitoque, Valle del Sibundoy— se
  acumulan sobre el departamento que les corresponde.
- Cuatro son **repartos**: Caribe Mar (Bolívar, Córdoba, Cesar, Sucre), Caribe Sol
  (Atlántico, Magdalena, La Guajira), Bogotá–Cundinamarca y Cali–Yumbo–Puerto
  Tejada. Sus pesos son **aproximaciones documentadas**, no mediciones.

La interfaz marca esos departamentos como *estimados* y la tabla `demanda_departamento`
guarda la marca fila a fila. `verificar_conservacion` comprueba en cada ingesta
que el reparto **no crea ni destruye energía**: la suma de los departamentos
reproduce exactamente el total de los mercados de origen, y hay una prueba
automática que lo garantiza.

Amazonas, Guainía, Vaupés, Vichada y San Andrés no aparecen en ningún mercado
porque **no están conectados al SIN**. El mapa los pinta en gris con su propia
entrada en la leyenda: tienen otra fuente de abastecimiento, no demanda cero.

---

## Modelos predictivos

Los nueve implementan la misma interfaz (`src/models/base.py`), de modo que el
orquestador los recorre en bucle y añadir uno nuevo no obliga a tocar nada más.

| Modelo | Familia | Librería | Papel en el estudio | Por defecto |
|---|---|---|---|---|
| Pronóstico ingenuo estacional | Referencia | — | La vara de medir: repite el ciclo anterior. | ✓ |
| Random Forest | Árboles | scikit-learn | No linealidades e interacciones. | ✓ |
| XGBoost | Árboles | xgboost | *Boosting* por niveles, con parada temprana. | ✓ |
| LightGBM | Árboles | lightgbm | *Boosting* por hojas: captura mejor los casos raros. | ✓ |
| Ridge | Lineal | scikit-learn | Relación lineal con multicolinealidad controlada. | |
| ElasticNet | Lineal | scikit-learn | Selecciona variables: los coeficientes que sobreviven son un resultado. | |
| Holt-Winters | Serie temporal | statsmodels | Nivel + tendencia + estacionalidad, sin exógenas. | |
| SARIMAX | Serie temporal | statsmodels | Estructura temporal explícita, con exógenas. | |
| LSTM | Red neuronal | PyTorch | Red recurrente sobre la secuencia completa. | |

### Los tres de producción, y los otros seis

Por defecto se entrenan solo los cuatro marcados: los tres de árboles, que ganan
de forma consistente sobre datos reales, más el pronóstico ingenuo, que no
compite sino que hace de referencia. Así el sistema no carga en el día a día con
cinco modelos que ya se sabe que pierden y tardan minutos en entrenarse.

Los otros siguen implementados y se entrenan con `--todos-los-modelos`: la
comparación entre las cinco familias es el objeto del trabajo de grado y tiene
que poder reproducirse en cualquier momento.

### Estrategia multihorizonte

Se entrena **un modelo por cada (objetivo, horizonte)** con estrategia *direct
multi-step*: el modelo de 720 h aprende a mapear las variables del instante *t*
al valor de *t + 720 h*. La alternativa —predecir una hora y realimentar la
predicción 720 veces— acumula el error de cada paso sobre el siguiente y a un mes
vista produce cifras sin ningún valor.

### Variables predictoras (~120)

- **Calendario cíclico**: hora, día de semana, mes y día del año codificados con
  seno/coseno. La hora 23 y la hora 0 son adyacentes; sin esta codificación
  distarían 23.
- **Calendario festivo colombiano**: festivo, víspera y día laboral, calculados
  con la **ley Emiliani** (buena parte de los festivos se traslada al lunes
  siguiente, así que una lista de fechas fijas falla justo en los días que más
  desplazan la demanda).
- **Rezagos del objetivo**: 1, 2, 3, 6, 12, 24, 48, 72, 168 y 336 horas.
- **Ventanas móviles**: media, desviación, máximo y mínimo a 24 h, 168 h y 720 h,
  más la media de la misma hora en los últimos siete días.
- **Exógenas de mercado**: mezcla de generación por tecnología, margen de
  reserva, brecha de generación, coste de restricciones por kWh, distancia al
  precio de escasez, aportes frente a su media histórica y tendencia del embalse
  a 7 y 30 días.
- **Clima y ENSO**: temperatura, grados-día de refrigeración, precipitación
  acumulada e índice ONI.

### Métricas

| Métrica | Por qué está |
|---|---|
| **MAE** | En la unidad del objetivo, directamente interpretable. |
| **RMSE** | Penaliza los errores grandes. Es el criterio de selección por defecto. |
| **MAPE** | Adimensional, comparable entre periodos con niveles distintos. |
| **sMAPE** | Corrige la asimetría del MAPE, que favorece a los modelos que subestiman. |
| **MASE** | Error dividido por el del pronóstico ingenuo **del mismo horizonte**. Es la única que responde a si el modelo aporta algo sobre repetir el pasado. |
| **R²** | Bondad de ajuste, como referencia. |

### Banda de predicción

La banda que acompaña a cada pronóstico son los cuantiles 10 y 90 de los
residuos del modelo **sobre el conjunto de prueba**, no sobre el de
entrenamiento: los residuos de entrenamiento están sistemáticamente
subestimados —el modelo ya vio esos datos— y producirían una banda demasiado
estrecha, que es la peor clase de error en un intervalo de confianza porque
transmite una seguridad que no existe.

`python -m scripts.evaluar_produccion` mide después qué porcentaje de los valores
reales cayó dentro de la banda declarada.

### Validez metodológica

Cuatro salvaguardas, todas cubiertas por pruebas automáticas:

- **Sin fuga de información**: todos los rezagos usan `shift()` hacia el pasado
  y las ventanas móviles se calculan sobre series ya desplazadas. Ninguna
  variable del instante *t* entra en la predicción de *t*.
- **Exclusiones por objetivo**: al predecir demanda quedan fuera la demanda
  comercial, la regulada, la no regulada y la generación total, que son
  prácticamente la misma serie y darían un R² espectacular y un modelo inútil.
- **Partición cronológica**: el conjunto de prueba es siempre el tramo final de
  la serie. Un `train_test_split` aleatorio metería futuro en el entrenamiento y
  produciría métricas optimistas que no se sostienen en producción.
- **Comparación dentro de un mismo lote**: cada entrenamiento etiqueta sus filas
  con un identificador, y la tabla comparativa solo mezcla modelos del mismo
  lote —entrenados con los mismos datos y el mismo corte.

---

## Resultados obtenidos

Ejecución real sobre datos de XM de enero de 2023 a agosto de 2026 (32.136
registros horarios, 34 variables), partición cronológica 80/20 y modelos de
producción. **MASE < 1 significa que el modelo le gana al pronóstico ingenuo del
mismo horizonte**; es la lectura que decide si aporta algo.

### Precio de bolsa (COP/kWh)

| Horizonte | Ganador | MAE | RMSE | MAPE | MASE | R² |
|---|---|---|---|---|---|---|
| 24 h | XGBoost | 66,01 | **102,11** | 21,1 % | 0,958 | 0,894 |
| 7 días | Random Forest | 131,73 | **170,17** | 43,6 % | 0,876 | 0,706 |
| 30 días | Random Forest | 171,46 | **219,28** | 50,5 % | 0,649 | 0,518 |

### Demanda real (kWh)

| Horizonte | Ganador | MAE | RMSE | MAPE | MASE | R² |
|---|---|---|---|---|---|---|
| 24 h | LightGBM | 284.352 | **357.609** | 2,8 % | 0,627 | 0,901 |
| 7 días | Random Forest | 366.586 | **486.907** | 3,6 % | 1,164 | 0,817 |
| 30 días | Random Forest | 571.470 | **706.548** | 5,6 % | 0,778 | 0,615 |

Variables más influyentes del ganador a 24 h de precio, por permutación:
`objetivo_media_720h`, `volumen_util_embalse`, `objetivo_media_misma_hora_7d`,
`capacidad_util_energia` y `ratio_precio_escasez`.

### Lectura honesta de estos números

Conviene discutirlos en el trabajo en lugar de presentarlos sin más:

- **El R² de precio a 24 h subió de 0,33 a 0,89** al pasar de 9 a 34 variables e
  incorporar el desglose de generación por tecnología. La mejora no viene de los
  modelos, viene de los datos: la hidrología y la mezcla de generación aparecen
  ahora entre las variables más influyentes, justo donde la hipótesis inicial
  del trabajo decía que estarían.
- **La demanda se pronostica mucho mejor que el precio.** Un MAPE del 2,8 % a 24
  horas frente al 21 % del precio. Tiene sentido: la demanda la gobierna el
  calendario —hora, día de la semana, festivos—, mientras que el precio depende
  además de decisiones de oferta que no están en los datos.
- **Cinco de las seis combinaciones superan al pronóstico ingenuo.** La
  excepción es la demanda a 7 días (MASE 1,164), y el motivo es interesante: el
  ciclo semanal de la demanda es tan regular que "lo mismo que este día la semana
  pasada" es un rival muy duro a ese horizonte concreto.
- **A 7 y 30 días de precio, Random Forest gana con claridad y los de *boosting*
  se hunden** (MASE 1,24 y 1,10). El promediado de árboles independientes
  generaliza mejor cuando la señal es débil; el *boosting*, que ajusta cada árbol
  al error del anterior, sobreajusta el ruido.
- **El R² negativo de LightGBM y XGBoost a 30 días** no es un fallo: significa
  literalmente que predecir la media habría salido mejor. Está en la tabla
  porque es el resultado.

Vías de mejora razonables: ampliar el histórico para cubrir un ciclo ENSO
completo, incorporar la disponibilidad declarada de las plantas térmicas, y
probar horizontes cortos (1-6 horas), donde la autocorrelación es mucho mayor.

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
