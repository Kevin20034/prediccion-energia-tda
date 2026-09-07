# Fenómeno del Niño, actualización continua y explicación de modelos

**Fecha:** 7 de septiembre de 2026
**Estado:** aprobado, pendiente de implementación

Cuatro cambios pedidos sobre la plataforma existente. Dos son acotados (fase 1)
y dos añaden subsistemas nuevos (fases 2 y 3).

---

## Contexto verificado antes de diseñar

Comprobaciones hechas contra el repositorio y la base de datos real, no supuestas:

| Hecho | Consecuencia para el diseño |
|---|---|
| `ClimaClient.__init__` ya acepta `latitud`/`longitud` | Bajar clima por departamento es recorrer coordenadas, no reescribir el cliente. |
| Solo se guarda un punto de clima (Medellín, `settings.CLIMA_*`) | **No existe** temperatura por departamento. Hay que crearla. |
| `clasificar_fenomeno()` y el parseo del ONI ya existen | La clasificación ENSO está hecha; falta exponerla. |
| `datos_historicos` ya tiene `indice_oni` y `fenomeno_climatico`, con 32.136 filas pobladas | El efecto de ENSO se calcula sobre datos que ya están; no requiere ingesta nueva. |
| Último dato: 2026-08-31; hoy: 2026-09-07 | La ingesta lleva una semana sin correr. Es el problema real detrás de "tiempo real". |
| `Departamento` es un `dataclass(frozen=True)` sin coordenadas | Añadir lat/lon obliga a tocar sus pruebas. |
| El GeoJSON se sirve estático desde `frontend/public/colombia-departamentos.json` | El mapa nuevo reutiliza geometría; no hay que descargar nada. |
| `URL_OPEN_METEO` apunta al *archive* | El archivo tiene ~5 días de retraso: para los días recientes hace falta además el endpoint de pronóstico. |

### El hallazgo que define la sección del Niño

Consulta sobre `datos_historicos` agrupando por `fenomeno_climatico`:

| Fase | Horas | Precio medio (COP/kWh) | Demanda media (kWh) | Temp. media (°C) |
|---|---:|---:|---:|---:|
| El Niño | 9.504 | 635,3 | 9.429.334 | 21,25 |
| Neutro | 19.680 | 442,9 | 9.447.625 | 20,65 |
| La Niña | 2.952 | 259,5 | 9.444.726 | 20,03 |

**El Niño multiplica el precio por 2,4 frente a La Niña y lo sube un 43 % sobre
lo normal, mientras la demanda varía un 0,2 % entre fases.** La sección debe
contar eso —el fenómeno golpea el precio, no el consumo, porque sin agua entra
la térmica— y no la intuición de "más calor, más consumo, más precio", que estos
datos no sostienen.

**Limitación a declarar en pantalla:** La Niña son 123 días y el ONI apenas baja
a −0,61, rozando el umbral de −0,5. Esa columna se etiqueta como de evidencia
débil; no se presenta con la misma firmeza que El Niño.

---

## Fase 1 — Título y explicación de modelos

### Título

La aplicación pasa a llamarse **«Predicción Energía TdeA»** y nada más. Se
unifica en los cuatro sitios donde hoy hay dos nombres distintos conviviendo:

- `frontend/index.html` → `<title>`
- `App.jsx`: la barra pierde el `SIN` y el subtítulo `Pronóstico energético`
- `Acceso.jsx`: el encabezado «Sistema Interconectado Nacional»
- La cabecera de informe impreso (`estilos/informe.css` / `Inicio.jsx`)

### Explicación de los modelos

Bloque nuevo sobre la tabla comparativa de la sección Modelos, en lenguaje llano
y sin fórmulas. Cubre:

1. **Qué entra y qué sale**: 109 variables de una hora → el valor estimado a
   24 h, 7 d o 30 d, más la banda.
2. **Cómo aprende cada familia**: el ingenuo repite la misma hora de ayer;
   Random Forest hace votar árboles construidos sobre muestras distintas;
   XGBoost y LightGBM encadenan árboles donde cada uno corrige el error del
   anterior.
3. **Por qué la partición es por fecha y no al azar**: partir al azar mete
   futuro en el entrenamiento y produce métricas que no se sostienen.
4. **Un esquema** del recorrido `XM → limpieza → 109 variables → modelo →
   pronóstico + banda`.

No cambia ningún cálculo. Es contenido; se alimenta de los modelos realmente
presentes en el lote, no de una lista escrita a mano.

---

## Fase 2 — Actualización continua

XM publica con días de retraso: "tiempo real" al segundo no existe en la fuente.
El objetivo real es que el sistema esté **tan al día como la fuente permita**, que
es lo que hoy no ocurre.

### Servidor

Un planificador arranca en el `lifespan` de FastAPI y cada intervalo configurable
reejecuta la ingesta de XM, clima y ONI. La escritura ya es idempotente, así que
reejecutar un rango es seguro por construcción.

Guardas necesarias:

- Detrás de `INGESTA_AUTOMATICA` (por defecto apagada), para que no se dispare en
  las pruebas ni al ejecutar scripts.
- Guarda por marca de tiempo de la última ejecución, para que `--reload` o varios
  procesos no ingieran a la vez.
- Los fallos de red se registran y no tumban la aplicación: una fuente caída deja
  el dato viejo, no la API muerta.

### Endpoint

`GET /estado-datos` → por fuente: última hora publicada, cuándo corrió la última
revisión, cuándo es la próxima.

### Interfaz

Refresco automático **solo mientras la pestaña está visible** —refrescar una
pestaña que nadie mira es gasto puro— y un indicador que separa dos cosas que no
son lo mismo:

- «XM publicó hasta las 23:00 del 31 de ago» → edad del dato
- «revisado hace 4 min» → edad de la comprobación

Decir la edad real es preferible a insinuar que el dato es del segundo actual.

---

## Fase 3 — Fenómeno del Niño

### Datos

- Coordenada de la capital para los 33 departamentos, en `departamentos.py`.
- Recolector `clima_departamentos.py`, que reutiliza `ClimaClient` por
  coordenada y paraleliza como ya hace `xm_api`.
- **Dos endpoints de Open-Meteo**: *archive* para los 3 años de historia,
  *forecast* para los días recientes que el archivo aún no publica.
- Tabla `clima_departamento`, horaria, para casar con `demanda_departamento`,
  que ya está a esa resolución. ~1,06 M filas para 3 años × 33 departamentos.

### Análisis

- **Anomalía**: temperatura del departamento frente a la media de ese mismo mes
  en su propia historia. Por eso hacían falta los 3 años: comparar contra un solo
  año no distingue un mes caliente de un año caliente.
- **Efecto**: agregación por `fenomeno_climatico` sobre `datos_historicos`, que
  ya tiene las columnas. Devuelve las cifras reales de la tabla de arriba.

### Endpoints

| Ruta | Devuelve |
|---|---|
| `GET /nino/estado` | ONI actual, fase, intensidad y serie reciente |
| `GET /nino/mapa` | Por departamento: temperatura, anomalía y su demanda |
| `GET /nino/efecto` | Precio y demanda medios por fase, con el tamaño de muestra |

### Sección

Pestaña propia, `acceso: "todos"`. Tres bloques: estado ENSO actual, mapa por
anomalía, y el efecto medido sobre precio y demanda.

El mapa usa **escala divergente frío/calor**, no la rampa secuencial del mapa de
demanda: una anomalía tiene un cero con significado —lo normal— y dos direcciones,
y una rampa secuencial lo escondería. Se valida para daltonismo como el resto de
la paleta; el par azul/naranja es seguro, el rojo/verde no.

---

## Orden y riesgos

**Orden: 1 → 2 → 3.** La fase 2 va antes que la 3 a propósito: un mapa de
temperaturas alimentado por datos de hace una semana no es un mapa de
temperaturas.

| Riesgo | Mitigación |
|---|---|
| Ingesta inicial de clima de 15-25 min | Corre una sola vez, por script, fuera del arranque de la API. |
| `Departamento` congelado se usa en varios sitios | Coordenadas con valor por defecto; actualizar `test_territorio.py`. |
| El planificador se duplica con `--reload` o varios workers | Apagado por defecto + guarda por marca de tiempo. |
| Open-Meteo limita peticiones | Reutilizar el paralelismo acotado de `xm_api`, no 33 peticiones simultáneas. |
| La Niña tiene muestra corta | Etiquetado explícito de evidencia débil en la interfaz. |
