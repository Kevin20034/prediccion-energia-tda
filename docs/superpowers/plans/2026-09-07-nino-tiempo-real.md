# Fenómeno del Niño, actualización continua y explicación de modelos — Plan de implementación

> **Para quien ejecute esto:** usar `superpowers:subagent-driven-development` o
> `superpowers:executing-plans`. Los pasos llevan casilla (`- [ ]`) para ir marcando.

**Objetivo:** renombrar la aplicación, explicar cómo funcionan los modelos, mantener
los datos al día de forma automática, y añadir una sección «Fenómeno del Niño» con
temperatura por departamento y su efecto medido sobre precio y demanda.

**Arquitectura:** se respetan las capas existentes. La recolección nueva
(`clima_departamentos.py`) copia el patrón de `xm_departamentos.py`; la persistencia
reutiliza `_guardar`, que ya es idempotente; los endpoints nuevos son un router más;
la sección nueva reutiliza el componente `MapaColombia` con otra escala de color.

**Stack:** FastAPI, SQLAlchemy 2.0, Alembic, pandas, React 18 + Vite 6 + Recharts.

**Spec:** `docs/superpowers/specs/2026-09-07-nino-tiempo-real-design.md`

## Restricciones globales

- El nombre de la aplicación es exactamente **`Predicción Energía TdeA`**. Sin
  «SIN», sin «Sistema Interconectado Nacional», sin subtítulos añadidos.
- Todo el código, comentarios, docstrings y textos de interfaz van **en español**,
  siguiendo el estilo del repositorio.
- Los commits llevan **solo a Kevin como autor**, sin `Co-Authored-By`.
- Se trabaja en la rama `main`. No se crean ramas.
- `ruff check src scripts tests` debe pasar limpio antes de cada commit.
- Las pruebas corren sobre SQLite en memoria: nada de tipos exclusivos de PostgreSQL.
- Ninguna credencial entra en git. `.env` sigue ignorado.
- La ingesta automática va **apagada por defecto** (`INGESTA_AUTOMATICA=false`).

---

# FASE 1 — Título y explicación de modelos

## Task 1: Renombrar la aplicación

**Archivos:**
- Modificar: `frontend/index.html` (etiqueta `<title>`)
- Modificar: `frontend/src/App.jsx:155-159` (bloque `barra__marca`)
- Modificar: `frontend/src/componentes/Acceso.jsx` (encabezado)
- Modificar: `frontend/src/secciones/Inicio.jsx` (cabecera del informe impreso)
- Modificar: `src/api/main.py:112` (`title=` de OpenAPI)

**Interfaces:**
- Consume: nada.
- Produce: nada que otras tareas usen. Es un cambio de textos.

- [ ] **Paso 1: Localizar todos los nombres vivos**

```bash
grep -rn "Sistema Interconectado\|Pronóstico energético\|>SIN<\|SIN ·" \
  frontend/src frontend/index.html src/api/main.py
```

Anotar cada aparición. Deben quedar cero al terminar, salvo las que se refieran al
Sistema Interconectado Nacional **como concepto del dominio** (por ejemplo el
glosario o el texto «demanda del SIN»), que no son el nombre de la aplicación y se
conservan.

- [ ] **Paso 2: Cambiar el título del documento**

En `frontend/index.html`:

```html
<title>Predicción Energía TdeA</title>
```

- [ ] **Paso 3: Cambiar la marca de la barra**

En `frontend/src/App.jsx`, sustituir el bloque `barra__marca` por:

```jsx
<span className="barra__marca">
  <i className="barra__pulso" aria-hidden="true" />
  Predicción Energía TdeA
</span>
```

Se elimina el `<span className="barra__sitio">`. Si `barra__sitio` deja de usarse en
todo el proyecto, borrar también su regla en `frontend/src/estilos/base.css`: dejar
CSS muerto es deuda que el siguiente lector tiene que descartar a mano.

- [ ] **Paso 4: Cambiar el encabezado del acceso**

En `frontend/src/componentes/Acceso.jsx`, el `<h1>` pasa a `Predicción Energía TdeA`.
Mantener el resaltado en verde de una parte del nombre si ya existía ese efecto, pero
sobre el nombre nuevo: resaltar `Energía`.

- [ ] **Paso 5: Cambiar la cabecera del informe impreso y el título de la API**

En `Inicio.jsx`, la `.cabecera-informe` usa el nombre nuevo. En `src/api/main.py:112`:

```python
    title="API — Predicción Energía TdeA",
```

- [ ] **Paso 6: Verificar que no queda ningún nombre viejo**

```bash
grep -rn "Pronóstico energético" frontend/src frontend/index.html src/
```

Esperado: sin resultados.

- [ ] **Paso 7: Comprobar que compila y se ve**

```bash
cd frontend && npm run build
```

Esperado: build correcto. Después levantar la aplicación y comprobar visualmente la
barra y el acceso (ver «Verificación visual» al final del plan).

- [ ] **Paso 8: Commit**

```bash
git add frontend/index.html frontend/src src/api/main.py
git commit -m "Renombrar la aplicacion a Prediccion Energia TdeA"
```

---

## Task 2: Explicar cómo funcionan los modelos

**Archivos:**
- Crear: `frontend/src/componentes/ComoFuncionan.jsx`
- Modificar: `frontend/src/secciones/Modelos.jsx` (montar el componente sobre la tabla)
- Modificar: `frontend/src/estilos/base.css` (estilos del bloque y del esquema)

**Interfaces:**
- Consume: la lista de modelos del lote que `Modelos.jsx` ya recibe de
  `GET /modelos/comparacion`, para no escribir a mano una lista que puede quedar
  desfasada.
- Produce: `<ComoFuncionan modelos={...} />`, donde `modelos` es el arreglo de
  objetos con al menos `{ nombre_modelo }`.

- [ ] **Paso 1: Leer la forma real de los datos que ya llegan**

```bash
grep -n "comparacion\|modelos\|familia" frontend/src/secciones/Modelos.jsx | head -30
```

Anotar el nombre exacto del estado que guarda la comparación y la forma de cada fila.
El componente nuevo debe consumir eso, no una forma inventada.

- [ ] **Paso 2: Crear el componente explicativo**

Crear `frontend/src/componentes/ComoFuncionan.jsx`. Contenido obligatorio:

1. **Qué entra y qué sale.** 109 variables de una hora concreta → el valor estimado a
   24 h, 7 d o 30 d, más la banda de incertidumbre.
2. **Cómo aprende cada familia**, en una frase por familia y sin fórmulas:
   - *Referencia (ingenuo estacional)*: repite lo que pasó a la misma hora del ciclo
     anterior. No aprende nada; está para saber si los demás aportan algo.
   - *Bosque aleatorio*: construye muchos árboles sobre muestras distintas de los
     datos y promedia su voto. Al promediar árboles independientes, los errores de
     unos compensan los de otros.
   - *Potenciación por gradiente (XGBoost, LightGBM)*: encadena árboles, y cada uno
     se entrena sobre el error que dejó el anterior. Afina más, pero si la señal es
     débil termina aprendiendo el ruido — que es justo lo que se ve a 30 días.
3. **Por qué la partición es por fecha y no al azar**: repartir al azar deja horas
   del futuro dentro del entrenamiento, y las métricas salen buenas por un motivo
   que no se repite en producción.
4. **El esquema del recorrido**, como SVG en línea (sin librerías):
   `datos de XM → limpieza → 109 variables → modelo → pronóstico + banda`.

El esquema debe llevar `role="img"` y un `<title>` descriptivo dentro del SVG, y usar
`currentColor` o variables CSS para los trazos, de modo que siga legible si cambia el
tema. Usar los tokens de `src/tokens.js`; no escribir colores a mano.

- [ ] **Paso 3: Montarlo en la sección Modelos**

En `frontend/src/secciones/Modelos.jsx`, insertar `<ComoFuncionan modelos={...} />`
**encima** de la tabla comparativa: la explicación va antes que los números, porque es
lo que permite leerlos.

- [ ] **Paso 4: Comprobar que compila y se ve**

```bash
cd frontend && npm run build
```

Después revisar la sección Modelos con el conductor (ver «Verificación visual»).
Comprobar que el esquema SVG no desborda a lo ancho en pantalla estrecha.

- [ ] **Paso 5: Commit**

```bash
git add frontend/src
git commit -m "Explicar en la seccion Modelos como aprende cada familia"
```

---

# FASE 2 — Actualización continua

## Task 3: Endpoint de estado de los datos

**Archivos:**
- Crear: `src/api/routers/estado.py`
- Modificar: `src/api/main.py` (registrar el router)
- Probar: `tests/test_estado_datos.py`

**Interfaces:**
- Consume: `SesionBD`, `UsuarioActual` de `src/api/dependencias.py` (mismos nombres
  que usan los routers existentes; confirmarlos leyendo `src/api/routers/datos.py`).
- Produce: `GET /estado-datos` →
  ```python
  {
    "fuentes": [
      {"nombre": "XM", "ultimo_dato": "2026-08-31T23:00:00Z", "horas_de_retraso": 168.0},
      {"nombre": "Departamentos", "ultimo_dato": "...", "horas_de_retraso": 0.0},
    ],
    "ultima_revision": "2026-09-07T15:00:00Z" | None,
    "proxima_revision": "2026-09-07T16:00:00Z" | None,
    "ingesta_automatica": False,
  }
  ```
  La sección de interfaz de la Task 5 depende de estos nombres exactos.

- [ ] **Paso 1: Escribir la prueba que falla**

Crear `tests/test_estado_datos.py`:

```python
"""El endpoint de estado debe decir la verdad sobre la edad del dato."""
from datetime import datetime, timedelta, timezone

from src.database.models import DatoHistorico


def test_estado_datos_reporta_el_retraso_real(cliente, sesion, cabecera_admin):
    """La edad del dato se mide contra el reloj, no contra la última ingesta."""
    hace_dos_dias = datetime.now(timezone.utc) - timedelta(days=2)
    sesion.add(DatoHistorico(fecha_hora=hace_dos_dias, precio_bolsa=500.0))
    sesion.commit()

    r = cliente.get("/estado-datos", headers=cabecera_admin)

    assert r.status_code == 200
    xm = next(f for f in r.json()["fuentes"] if f["nombre"] == "XM")
    assert 47 < xm["horas_de_retraso"] < 49


def test_estado_datos_sin_datos_no_revienta(cliente, cabecera_admin):
    """Una base recién creada devuelve None, no un error."""
    r = cliente.get("/estado-datos", headers=cabecera_admin)

    assert r.status_code == 200
    xm = next(f for f in r.json()["fuentes"] if f["nombre"] == "XM")
    assert xm["ultimo_dato"] is None
```

Usar los *fixtures* que ya existan en `tests/conftest.py`. Si los nombres son otros
(`client`, `db`, `auth_admin`...), adaptarlos: **leer `conftest.py` primero** y no
inventar nombres.

- [ ] **Paso 2: Ejecutar y ver que falla**

```bash
pytest tests/test_estado_datos.py -v
```

Esperado: FALLA con 404, porque la ruta no existe.

- [ ] **Paso 3: Implementar el router**

Crear `src/api/routers/estado.py`. Puntos que no se pueden omitir:

- La edad del dato se calcula contra `datetime.now(timezone.utc)`, no contra la
  última ingesta: son cosas distintas y confundirlas es el error que hace que un
  sistema parezca al día cuando lleva una semana parado.
- Si la tabla está vacía, `ultimo_dato` es `None` y `horas_de_retraso` es `None`.
  No devolver `0`, que se leería como «al día».
- Las marcas de tiempo salen en UTC con `Z`, como el resto de la API.

- [ ] **Paso 4: Registrar el router**

En `src/api/main.py`, junto a los demás:

```python
app.include_router(estado.router)
```

Añadir el import correspondiente en el bloque de imports de routers.

- [ ] **Paso 5: Ejecutar las pruebas**

```bash
pytest tests/test_estado_datos.py -v
```

Esperado: PASAN las dos.

- [ ] **Paso 6: Commit**

```bash
git add src/api/routers/estado.py src/api/main.py tests/test_estado_datos.py
git commit -m "Anadir el endpoint de estado de los datos"
```

---

## Task 4: Planificador de ingesta automática

**Archivos:**
- Crear: `src/api/planificador.py`
- Modificar: `src/core/config.py` (ajustes nuevos)
- Modificar: `src/api/main.py:86-110` (arrancarlo en el `lifespan`)
- Modificar: `.env.example` (documentar los ajustes)
- Probar: `tests/test_planificador.py`

**Interfaces:**
- Consume: las funciones de ingesta que ya usan los scripts. **Leer
  `scripts/ingestar_datos.py` y `scripts/ingestar_territorio.py`** para reutilizar
  sus funciones en vez de duplicar la lógica de descarga.
- Produce:
  ```python
  class Planificador:
      def __init__(self, intervalo_minutos: int, trabajos: list[Trabajo]) -> None: ...
      def debe_correr(self, ahora: datetime) -> bool: ...
      async def ciclo(self) -> None: ...
      def estado(self) -> dict           # {"ultima_revision", "proxima_revision"}
  Trabajo = tuple[str, Callable[[], tuple[int, int]]]
  ```
  La Task 3 consume `estado()` y la Task 12 registra un `Trabajo` más.

- [ ] **Paso 1: Añadir los ajustes de configuración**

En `src/core/config.py`, junto a los existentes:

```python
    INGESTA_AUTOMATICA: bool = False
    INGESTA_INTERVALO_MINUTOS: int = 60
```

Apagada por defecto **a propósito**: si estuviera encendida, cada `pytest`, cada
script y cada arranque con `--reload` dispararía descargas contra XM.

Documentarlos en `.env.example` con esa explicación.

- [ ] **Paso 2: Escribir la prueba que falla**

Crear `tests/test_planificador.py`:

```python
"""La guarda del planificador: nunca dos ingestas solapadas."""
from datetime import datetime, timedelta, timezone

from src.api.planificador import Planificador


def _plan(intervalo=60):
    return Planificador(intervalo_minutos=intervalo, trabajos=[])


def test_la_primera_vez_debe_correr():
    assert _plan().debe_correr(datetime.now(timezone.utc)) is True


def test_no_repite_antes_del_intervalo():
    """Con --reload o varios workers, dos procesos piden correr casi a la vez."""
    p = _plan(intervalo=60)
    ahora = datetime.now(timezone.utc)
    p.marcar_ejecucion(ahora)

    assert p.debe_correr(ahora + timedelta(minutes=5)) is False
    assert p.debe_correr(ahora + timedelta(minutes=61)) is True


def test_un_trabajo_que_falla_no_tumba_el_ciclo():
    """Una fuente caída deja el dato viejo; no mata la API."""
    llamadas = []

    def revienta():
        raise RuntimeError("XM no responde")

    def funciona():
        llamadas.append("ok")
        return (1, 0)

    p = Planificador(
        intervalo_minutos=60,
        trabajos=[("XM", revienta), ("Clima", funciona)],
    )
    resultado = p.ejecutar_una_vez()

    assert llamadas == ["ok"]                      # el segundo corrió igual
    assert resultado["XM"]["error"] is not None
    assert resultado["Clima"]["insertados"] == 1
```

- [ ] **Paso 3: Ejecutar y ver que falla**

```bash
pytest tests/test_planificador.py -v
```

Esperado: FALLA con `ModuleNotFoundError: No module named 'src.api.planificador'`.

- [ ] **Paso 4: Implementar el planificador**

Crear `src/api/planificador.py` con `Planificador`, `debe_correr`, `marcar_ejecucion`,
`ejecutar_una_vez`, `ciclo` (bucle `async` con `asyncio.sleep`) y `estado`.

Requisitos que las pruebas no capturan pero el diseño exige:

- Cada trabajo se ejecuta dentro de su propio `try/except`, se registra el fallo con
  `log.exception` y el ciclo continúa con el siguiente.
- El trabajo corre en un hilo aparte (`asyncio.to_thread`): la ingesta es bloqueante
  y colgaría el bucle de eventos de FastAPI, dejando la API sin responder mientras
  descarga.
- `ciclo()` captura `asyncio.CancelledError` y sale limpiamente al apagar.

- [ ] **Paso 5: Ejecutar las pruebas**

```bash
pytest tests/test_planificador.py -v
```

Esperado: PASAN las tres.

- [ ] **Paso 6: Arrancarlo en el `lifespan`**

En `src/api/main.py`, dentro de `lifespan`, después de `_precargar_modelos()`:

```python
    tarea = None
    if settings.INGESTA_AUTOMATICA:
        tarea = asyncio.create_task(planificador.ciclo())
        log.info("Ingesta automatica activada cada %d min", settings.INGESTA_INTERVALO_MINUTOS)

    yield

    if tarea is not None:
        tarea.cancel()
```

- [ ] **Paso 7: Comprobar que la API sigue arrancando con la ingesta apagada**

```bash
pytest -q
uvicorn src.api.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/salud
```

Esperado: pruebas en verde y `/salud` responde.

- [ ] **Paso 8: Commit**

```bash
git add src/api/planificador.py src/api/main.py src/core/config.py .env.example tests/test_planificador.py
git commit -m "Anadir ingesta automatica programada, apagada por defecto"
```

---

## Task 5: Refresco y frescura del dato en la interfaz

**Archivos:**
- Crear: `frontend/src/componentes/Frescura.jsx`
- Crear: `frontend/src/useRefresco.js`
- Modificar: `frontend/src/api.js` (función `estadoDatos()`)
- Modificar: `frontend/src/App.jsx` (montar `<Frescura />` en la barra)

**Interfaces:**
- Consume: `GET /estado-datos` con la forma exacta de la Task 3.
- Produce: `useRefresco(callback, minutos)`, que solo dispara mientras
  `document.visibilityState === "visible"`.

- [ ] **Paso 1: Añadir la llamada a la API**

En `frontend/src/api.js`, siguiendo el patrón de las funciones vecinas:

```js
export const estadoDatos = () => pedir("/estado-datos");
```

Comprobar cómo se llama realmente el ayudante de `fetch` en ese archivo antes de
escribir esto; el nombre `pedir` es orientativo.

- [ ] **Paso 2: Crear el hook de refresco**

Crear `frontend/src/useRefresco.js`:

```js
import { useEffect, useRef } from "react";

/**
 * Ejecuta `accion` cada `minutos`, pero solo mientras la pestaña está visible.
 *
 * Refrescar una pestaña que nadie mira gasta batería, cuota de la API y, si el
 * portátil está suspendido, despierta la red para nada. Al volver a la pestaña se
 * dispara una vez de inmediato, que es cuando el usuario sí quiere el dato fresco.
 */
export function useRefresco(accion, minutos = 5) {
  const guardada = useRef(accion);
  guardada.current = accion;

  useEffect(() => {
    let id = null;

    const activo = () => document.visibilityState === "visible";
    const disparar = () => { if (activo()) guardada.current(); };

    const arrancar = () => {
      parar();
      id = setInterval(disparar, minutos * 60_000);
    };
    const parar = () => { if (id) { clearInterval(id); id = null; } };

    const alCambiarVisibilidad = () => {
      if (activo()) { disparar(); arrancar(); } else { parar(); }
    };

    arrancar();
    document.addEventListener("visibilitychange", alCambiarVisibilidad);
    return () => { parar(); document.removeEventListener("visibilitychange", alCambiarVisibilidad); };
  }, [minutos]);
}
```

- [ ] **Paso 3: Crear el indicador de frescura**

Crear `frontend/src/componentes/Frescura.jsx`. Debe mostrar **dos cosas separadas**,
nunca fundidas en una:

- `XM publicó hasta el 31 de ago, 23:00` → edad del dato
- `revisado hace 4 min` → edad de la comprobación

Si `horas_de_retraso` supera 48, marcarlo visualmente con el color de aviso (ámbar):
un dato de hace más de dos días es una señal, no un detalle. Si `ultimo_dato` es
`null`, mostrar `sin datos`, nunca `hace 0 min`.

- [ ] **Paso 4: Montarlo en la barra**

En `frontend/src/App.jsx`, añadir `<Frescura />` en `barra__fila`, a la derecha, antes
del bloque del usuario.

- [ ] **Paso 5: Comprobar que compila y se ve**

```bash
cd frontend && npm run build
```

Comprobar con el conductor que el indicador aparece y dice una fecha real, no
`Invalid Date`.

- [ ] **Paso 6: Commit**

```bash
git add frontend/src
git commit -m "Mostrar la frescura del dato y refrescar mientras la pestana este visible"
```

---

# FASE 3 — Fenómeno del Niño

## Task 6: Coordenadas de los departamentos

**Archivos:**
- Modificar: `src/data_collection/departamentos.py:52-96`
- Probar: `tests/test_territorio.py`

**Interfaces:**
- Produce: `Departamento.latitud: float`, `Departamento.longitud: float`.
  Las Tasks 7 y 9 las consumen.

- [ ] **Paso 1: Escribir la prueba que falla**

Añadir a `tests/test_territorio.py`:

```python
def test_todos_los_departamentos_tienen_coordenadas():
    """Sin coordenada no hay clima: Open-Meteo se consulta por lat/lon."""
    for d in DEPARTAMENTOS:
        assert d.latitud is not None, f"{d.nombre} sin latitud"
        assert d.longitud is not None, f"{d.nombre} sin longitud"


def test_las_coordenadas_caen_dentro_de_colombia():
    """Una cifra tecleada al revés (lat/lon cambiadas) cae fuera y se detecta aquí."""
    for d in DEPARTAMENTOS:
        assert -4.3 <= d.latitud <= 13.5, f"{d.nombre}: latitud {d.latitud} fuera de Colombia"
        assert -82.0 <= d.longitud <= -66.8, f"{d.nombre}: longitud {d.longitud} fuera de Colombia"
```

El rango incluye San Andrés (12,58 N / −81,70 O), que es el punto más al noroeste, y
Leticia (−4,21 S), el más al sur.

- [ ] **Paso 2: Ejecutar y ver que falla**

```bash
pytest tests/test_territorio.py -k coordenadas -v
```

Esperado: FALLA con `AttributeError: 'Departamento' object has no attribute 'latitud'`.

- [ ] **Paso 3: Añadir los campos y los 33 valores**

En `departamentos.py`, ampliar el dataclass:

```python
@dataclass(frozen=True)
class Departamento:
    """Un departamento colombiano según la codificación DANE."""

    codigo: str
    nombre: str
    #: `False` para las Zonas No Interconectadas, que no tienen demanda en el SIN.
    interconectado: bool = True
    #: Coordenadas de la capital. El clima de un departamento se toma en su
    #: capital porque es donde se concentra la demanda, no en su centroide
    #: geométrico, que en departamentos como Chocó cae en selva deshabitada.
    latitud: float = 0.0
    longitud: float = 0.0
```

Rellenar los 33 con la coordenada de su capital. `interconectado` va antes que las
coordenadas, así que las cinco ZNI que hoy pasan `False` posicionalmente siguen
funcionando sin tocarlas.

- [ ] **Paso 4: Ejecutar las pruebas**

```bash
pytest tests/test_territorio.py -v
```

Esperado: PASA todo, incluidas las pruebas de reparto que ya existían.

- [ ] **Paso 5: Commit**

```bash
git add src/data_collection/departamentos.py tests/test_territorio.py
git commit -m "Anadir la coordenada de la capital a cada departamento"
```

---

## Task 7: Recolector de clima por departamento

**Archivos:**
- Crear: `src/data_collection/clima_departamentos.py`
- Probar: `tests/test_clima_departamentos.py`

**Interfaces:**
- Consume: `ClimaClient(latitud=..., longitud=...)` y su método
  `obtener(fecha_inicio: date, fecha_fin: date) -> pd.DataFrame`;
  `DEPARTAMENTOS` de la Task 6.
- Produce:
  ```python
  class ClimaDepartamentosClient(Recolector):
      nombre = "Clima-Departamentos"
      def obtener(self, fecha_inicio: date, fecha_fin: date) -> pd.DataFrame: ...
  def anomalia_mensual(clima: pd.DataFrame) -> pd.DataFrame: ...
  ```
  El `DataFrame` lleva `fecha_hora`, `codigo_dane`, `departamento`, `temperatura`,
  `precipitacion`, `humedad_relativa`. Las Tasks 8, 9 y 10 dependen de esos nombres.

- [ ] **Paso 1: Escribir la prueba que falla**

Crear `tests/test_clima_departamentos.py`:

```python
"""El recolector de clima por departamento y el cálculo de anomalía."""
import pandas as pd

from src.data_collection.clima_departamentos import anomalia_mensual


def test_la_anomalia_compara_contra_el_mismo_mes():
    """Un enero caliente se mide contra los eneros, no contra la media anual."""
    filas = []
    for anio in (2023, 2024, 2025):
        for mes, temp in ((1, 20.0), (7, 26.0)):
            filas.append(
                {"fecha_hora": pd.Timestamp(f"{anio}-{mes:02d}-15 12:00", tz="UTC"),
                 "codigo_dane": "05", "temperatura": temp}
            )
    # Enero de 2026 llega 2 grados por encima de los eneros anteriores.
    filas.append(
        {"fecha_hora": pd.Timestamp("2026-01-15 12:00", tz="UTC"),
         "codigo_dane": "05", "temperatura": 22.0}
    )

    r = anomalia_mensual(pd.DataFrame(filas))
    ultimo = r[r["fecha_hora"] == pd.Timestamp("2026-01-15 12:00", tz="UTC")].iloc[0]

    # Contra la media de eneros (20.0) la anomalía es +2, no contra la media
    # global (23.0), que daría -1 y contaría exactamente lo contrario.
    assert ultimo["anomalia"] == 2.0


def test_la_anomalia_es_por_departamento():
    """26 grados es normal en Barranquilla y altísimo en Bogotá."""
    filas = [
        {"fecha_hora": pd.Timestamp("2025-01-15 12:00", tz="UTC"), "codigo_dane": "08", "temperatura": 28.0},
        {"fecha_hora": pd.Timestamp("2026-01-15 12:00", tz="UTC"), "codigo_dane": "08", "temperatura": 28.0},
        {"fecha_hora": pd.Timestamp("2025-01-15 12:00", tz="UTC"), "codigo_dane": "11", "temperatura": 14.0},
        {"fecha_hora": pd.Timestamp("2026-01-15 12:00", tz="UTC"), "codigo_dane": "11", "temperatura": 16.0},
    ]
    r = anomalia_mensual(pd.DataFrame(filas))

    caribe = r[(r["codigo_dane"] == "08") & (r["fecha_hora"].dt.year == 2026)].iloc[0]
    andes = r[(r["codigo_dane"] == "11") & (r["fecha_hora"].dt.year == 2026)].iloc[0]

    assert caribe["anomalia"] == 0.0
    assert andes["anomalia"] == 1.0
```

- [ ] **Paso 2: Ejecutar y ver que falla**

```bash
pytest tests/test_clima_departamentos.py -v
```

Esperado: FALLA con `ModuleNotFoundError`.

- [ ] **Paso 3: Implementar el recolector**

Crear `src/data_collection/clima_departamentos.py`, copiando la estructura de
`xm_departamentos.py`. Puntos obligatorios:

- **Dos endpoints de Open-Meteo.** `URL_OPEN_METEO` (archivo) publica con ~5 días de
  retraso. Para los días recientes hace falta
  `https://api.open-meteo.com/v1/forecast` con `past_days`. Sin esto, el mapa de «la
  temperatura de ahora» mostraría siempre la de hace una semana, que es exactamente
  el problema que la fase 2 vino a arreglar.
- **Paralelismo acotado.** Reutilizar el patrón de `xm_api.ejecutar_todas`
  (`ThreadPoolExecutor`, concurrencia 6). No lanzar 33 peticiones a la vez: Open-Meteo
  limita por minuto y responde 429.
- **Un departamento que falle no cancela el resto**: se registra y se sigue.
- `anomalia_mensual` agrupa por `codigo_dane` y mes del año, calcula la media
  histórica de la temperatura y devuelve el `DataFrame` con las columnas
  `media_mensual` y `anomalia` añadidas.

- [ ] **Paso 4: Ejecutar las pruebas**

```bash
pytest tests/test_clima_departamentos.py -v
```

Esperado: PASAN las dos.

- [ ] **Paso 5: Commit**

```bash
git add src/data_collection/clima_departamentos.py tests/test_clima_departamentos.py
git commit -m "Anadir el recolector de clima por departamento"
```

---

## Task 8: Tabla `clima_departamento`

**Archivos:**
- Modificar: `src/database/models.py` (clase nueva tras `DemandaDepartamento`)
- Modificar: `src/database/persistencia.py` (`guardar_clima_departamento`)
- Crear: `alembic/versions/<hash>_clima_departamento.py`
- Probar: `tests/test_persistencia_clima.py`

**Interfaces:**
- Produce: `guardar_clima_departamento(db: Session, df: pd.DataFrame) -> tuple[int, int]`.
  La Task 9 la usa.

- [ ] **Paso 1: Escribir la prueba que falla**

Crear `tests/test_persistencia_clima.py`:

```python
"""La escritura de clima por departamento es idempotente, como el resto."""
import pandas as pd

from src.database.models import ClimaDepartamento
from src.database.persistencia import guardar_clima_departamento


def _muestra():
    return pd.DataFrame([{
        "fecha_hora": pd.Timestamp("2026-01-15 12:00", tz="UTC"),
        "codigo_dane": "05", "departamento": "Antioquia",
        "temperatura": 22.5, "precipitacion": 0.0, "humedad_relativa": 70.0,
    }])


def test_guardar_inserta(sesion):
    insertados, actualizados = guardar_clima_departamento(sesion, _muestra())
    assert (insertados, actualizados) == (1, 0)


def test_reejecutar_actualiza_en_vez_de_duplicar(sesion):
    """Reejecutar un rango ya descargado es lo normal, no un error."""
    guardar_clima_departamento(sesion, _muestra())

    corregido = _muestra()
    corregido.loc[0, "temperatura"] = 23.9
    insertados, actualizados = guardar_clima_departamento(sesion, corregido)

    assert (insertados, actualizados) == (0, 1)
    assert sesion.query(ClimaDepartamento).count() == 1
    assert sesion.query(ClimaDepartamento).one().temperatura == 23.9
```

- [ ] **Paso 2: Ejecutar y ver que falla**

```bash
pytest tests/test_persistencia_clima.py -v
```

Esperado: FALLA con `ImportError: cannot import name 'ClimaDepartamento'`.

- [ ] **Paso 3: Añadir el modelo**

En `src/database/models.py`, tras `DemandaDepartamento`, copiando su forma:

```python
class ClimaDepartamento(Base):
    """Clima horario en la capital de cada departamento.

    Se toma en la capital y no en el centroide geométrico porque es donde está la
    demanda: el centroide de Chocó cae en selva sin población, y su temperatura no
    explica ningún consumo.
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
```

- [ ] **Paso 4: Añadir la función de guardado**

En `src/database/persistencia.py`, junto a sus hermanas:

```python
def guardar_clima_departamento(db: Session, df: pd.DataFrame) -> tuple[int, int]:
    """Inserta o actualiza el clima horario por departamento."""
    if df.empty:
        return 0, 0
    return _guardar(db, df, ClimaDepartamento, ["fecha_hora", "codigo_dane"])
```

Añadir `ClimaDepartamento` al import de modelos de ese archivo.

- [ ] **Paso 5: Generar la migración**

```bash
alembic revision --autogenerate -m "clima por departamento"
```

Abrir el archivo generado y **leerlo antes de aplicarlo**: `--autogenerate` a veces
propone borrar cosas que no tocamos. Debe contener solo el `create_table` de
`clima_departamento` y sus índices.

```bash
alembic upgrade head
```

- [ ] **Paso 6: Ejecutar las pruebas**

```bash
pytest tests/test_persistencia_clima.py -v
```

Esperado: PASAN las dos.

- [ ] **Paso 7: Commit**

```bash
git add src/database alembic/versions tests/test_persistencia_clima.py
git commit -m "Anadir la tabla de clima por departamento"
```

---

## Task 9: Script de ingesta del clima departamental

**Archivos:**
- Crear: `scripts/ingestar_clima_departamentos.py`
- Modificar: `README.md` (documentar el comando)

**Interfaces:**
- Consume: `ClimaDepartamentosClient` (Task 7), `guardar_clima_departamento` (Task 8).
- Produce: el comando `python -m scripts.ingestar_clima_departamentos`.

- [ ] **Paso 1: Leer el script hermano para copiar su forma**

```bash
cat scripts/ingestar_territorio.py
```

Reutilizar su patrón de argumentos (`--inicio`, `--dias`), su registro y su manejo de
errores. No inventar una interfaz distinta para el mismo tipo de tarea.

- [ ] **Paso 2: Escribir el script**

Debe aceptar `--inicio` y `--dias`, trocear el rango por meses (tres años de golpe
para 33 departamentos es una petición que Open-Meteo corta), informar del avance por
departamento, y guardar por lotes.

- [ ] **Paso 3: Probarlo contra un rango corto de verdad**

```bash
python -m scripts.ingestar_clima_departamentos --dias 7
```

Esperado: 33 departamentos, 168 horas cada uno, ~5.544 filas insertadas, sin errores.
Comprobar en base de datos que hay 33 códigos distintos y que las temperaturas caen en
un rango físicamente posible para Colombia (aproximadamente 0-40 °C):

```bash
python -c "from sqlalchemy import text; from src.database.session import SessionLocal; s=SessionLocal(); print(s.execute(text('SELECT count(DISTINCT codigo_dane), min(temperatura), max(temperatura) FROM clima_departamento')).one())"
```

- [ ] **Paso 4: Lanzar la ingesta histórica completa**

```bash
python -m scripts.ingestar_clima_departamentos --inicio 2023-01-01
```

Tarda 15-25 minutos. Corre una sola vez.

- [ ] **Paso 5: Commit**

```bash
git add scripts/ingestar_clima_departamentos.py README.md
git commit -m "Anadir el script de ingesta de clima por departamento"
```

---

## Task 10: Endpoints del fenómeno del Niño

**Archivos:**
- Crear: `src/api/routers/nino.py`
- Modificar: `src/api/main.py` (registrar el router)
- Probar: `tests/test_nino.py`

**Interfaces:**
- Consume: `ClimaDepartamento`, `DatoHistorico`, `DemandaDepartamento`.
- Produce:
  - `GET /nino/estado` → `{"oni": 1.2, "fase": "EL_NINO", "intensidad": "moderado", "serie": [{"mes": "...", "oni": 1.2}]}`
  - `GET /nino/mapa` → `{"instante": "...", "departamentos": [{"codigo_dane": "05", "departamento": "Antioquia", "temperatura": 22.5, "anomalia": 1.3, "demanda_kwh": 123.0}]}`
  - `GET /nino/efecto` → `{"fases": [{"fase": "EL_NINO", "horas": 9504, "precio": 635.3, "demanda": 9429334, "temperatura": 21.25, "evidencia": "solida"}]}`

  La Task 11 depende de estos nombres exactos.

- [ ] **Paso 1: Escribir la prueba que falla**

Crear `tests/test_nino.py`:

```python
"""Los endpoints del fenómeno del Niño."""
from datetime import datetime, timezone

from src.database.models import DatoHistorico


def test_efecto_agrupa_por_fase_y_marca_la_evidencia(cliente, sesion, cabecera_admin):
    """La Niña tiene muestra corta y debe salir etiquetada como débil."""
    for i in range(100):
        sesion.add(DatoHistorico(
            fecha_hora=datetime(2024, 1, 1, tzinfo=timezone.utc).replace(hour=i % 24),
            precio_bolsa=600.0, demanda_real=9_000_000.0,
            fenomeno_climatico="EL_NINO", indice_oni=1.5,
        ))
    for i in range(5):
        sesion.add(DatoHistorico(
            fecha_hora=datetime(2025, 6, 1, tzinfo=timezone.utc).replace(hour=i),
            precio_bolsa=250.0, demanda_real=9_000_000.0,
            fenomeno_climatico="LA_NINA", indice_oni=-0.8,
        ))
    sesion.commit()

    r = cliente.get("/nino/efecto", headers=cabecera_admin)

    assert r.status_code == 200
    por_fase = {f["fase"]: f for f in r.json()["fases"]}
    assert por_fase["EL_NINO"]["precio"] == 600.0
    assert por_fase["EL_NINO"]["evidencia"] == "solida"
    # 5 horas no sostienen una afirmación: hay que decirlo, no esconderlo.
    assert por_fase["LA_NINA"]["evidencia"] == "debil"


def test_efecto_sin_datos_devuelve_lista_vacia(cliente, cabecera_admin):
    r = cliente.get("/nino/efecto", headers=cabecera_admin)
    assert r.status_code == 200
    assert r.json()["fases"] == []
```

- [ ] **Paso 2: Ejecutar y ver que falla**

```bash
pytest tests/test_nino.py -v
```

Esperado: FALLA con 404.

- [ ] **Paso 3: Implementar el router**

Crear `src/api/routers/nino.py`. Requisitos:

- `evidencia` es `"debil"` por debajo de `HORAS_EVIDENCIA_SOLIDA = 720` (un mes de
  horas) y `"solida"` por encima. La constante va nombrada y comentada, no como
  número suelto.
- `intensidad` sigue el criterio de la NOAA sobre el valor absoluto del ONI:
  débil 0,5-0,9; moderado 1,0-1,4; fuerte 1,5-1,9; muy fuerte ≥ 2,0.
- La anomalía del mapa se calcula con la misma función `anomalia_mensual` de la
  Task 7. **No reimplementarla en SQL**: dos definiciones de la misma cifra terminan
  divergiendo y nadie sabe cuál es la buena.
- Acceso: `UsuarioActual`, sin restricción de rol. Es una sección para todos.

- [ ] **Paso 4: Registrar el router y ejecutar las pruebas**

```bash
pytest tests/test_nino.py -v
```

Esperado: PASAN las dos.

- [ ] **Paso 5: Comprobar contra los datos reales**

```bash
curl -s "http://127.0.0.1:8000/nino/efecto" -H "Authorization: Bearer $TOKEN"
```

Esperado: las cifras del spec — El Niño ~635 COP/kWh, Neutro ~443, La Niña ~260.
Si no coinciden, la consulta está mal; no ajustar el spec para que encaje.

- [ ] **Paso 6: Commit**

```bash
git add src/api/routers/nino.py src/api/main.py tests/test_nino.py
git commit -m "Anadir los endpoints del fenomeno del Nino"
```

---

## Task 11: Sección «Fenómeno del Niño»

**Archivos:**
- Crear: `frontend/src/secciones/FenomenoNino.jsx`
- Modificar: `frontend/src/tokens.js` (rampa divergente)
- Modificar: `frontend/src/componentes/graficas/MapaColombia.jsx` (aceptar rampa y escala)
- Modificar: `frontend/src/App.jsx` (añadir la sección a `SECCIONES`)
- Modificar: `frontend/src/api.js` (tres funciones nuevas)

**Interfaces:**
- Consume: los tres endpoints de la Task 10 con sus nombres exactos.
- Produce: sección `{ clave: "nino", etiqueta: "Fenómeno del Niño", acceso: "todos" }`.

- [ ] **Paso 1: Cargar la guía de visualización antes de elegir colores**

**Obligatorio:** invocar la skill `dataviz` antes de escribir la rampa o cualquier
código de gráfica. La paleta debe pasar su validador.

- [ ] **Paso 2: Añadir la rampa divergente**

En `frontend/src/tokens.js`, junto a `RAMPA_MAPA`:

```js
/**
 * Escala divergente para la anomalía de temperatura.
 *
 * La anomalía tiene un cero con significado —lo normal— y dos direcciones, así que
 * una rampa secuencial como la de demanda escondería la mitad de la información.
 * El par frío/cálido es azul-naranja y no azul-rojo ni rojo-verde: rojo contra
 * verde es la confusión cromática más común y borraría justo la distinción que
 * este mapa existe para mostrar.
 */
export const RAMPA_ANOMALIA = [ /* ...validada con la skill dataviz... */ ];
```

- [ ] **Paso 3: Generalizar el mapa**

`MapaColombia.jsx` hoy asume la rampa de demanda y cortes por cuantiles. Añadir dos
props con valor por defecto igual al comportamiento actual, para no romper el mapa
existente:

```jsx
export default function MapaColombia({
  rampa = RAMPA_MAPA,
  escala = "cuantiles",   // "cuantiles" | "divergente"
  ...
})
```

En modo `divergente` los cortes son simétricos alrededor de cero: si no lo son, un
lugar medio grado por encima de lo normal se pinta del mismo color que uno tres
grados por encima, y el mapa miente.

- [ ] **Paso 4: Construir la sección**

Crear `frontend/src/secciones/FenomenoNino.jsx` con tres bloques en este orden:

1. **Estado actual**: fase, ONI e intensidad, en una frase legible
   («Ahora mismo: El Niño moderado, ONI 1,2»).
2. **Mapa de anomalía**, con leyenda que diga qué es la anomalía en una línea
   («cuánto se aparta la temperatura de lo normal en ese departamento para este mes»).
3. **El efecto medido**, que es lo que responde a la pregunta del usuario. Debe decir
   explícitamente las dos mitades del hallazgo:
   - El Niño sube el precio un ~43 % sobre lo normal y lo multiplica por 2,4 frente a
     La Niña.
   - La demanda apenas se mueve (~0,2 % entre fases).

   Y explicar por qué: sin agua entra la generación térmica, que es más cara. El
   consumo es casi el mismo; lo que cambia es lo que cuesta producirlo.

   Las cifras vienen del endpoint, no escritas a mano. Las fases con
   `evidencia: "debil"` se marcan visiblemente.

- [ ] **Paso 5: Registrar la sección**

En `App.jsx`, añadir a `SECCIONES` después de `mapa`:

```jsx
  { clave: "nino", etiqueta: "Fenómeno del Niño", Componente: FenomenoNino, acceso: "todos" },
```

- [ ] **Paso 6: Comprobar que compila y se ve**

```bash
cd frontend && npm run build
```

Revisar con el conductor: que el mapa pinte los 33 departamentos, que la leyenda sea
simétrica respecto a cero, y que las cifras del efecto coincidan con `/nino/efecto`.

- [ ] **Paso 7: Commit**

```bash
git add frontend/src
git commit -m "Anadir la seccion del fenomeno del Nino con el mapa de anomalia"
```

---

## Task 12: Cerrar el círculo — clima en el planificador y documentación

**Archivos:**
- Modificar: `src/api/planificador.py` (registrar el trabajo de clima)
- Modificar: `README.md`
- Modificar: `docs/` y la documentación del escritorio

- [ ] **Paso 1: Registrar el trabajo de clima departamental**

Añadir el trabajo a la lista del planificador, para que la fase 3 se mantenga al día
por el mecanismo de la fase 2. Sin esto, el mapa de temperaturas vuelve a envejecer y
el trabajo de la fase 2 no le sirve de nada.

- [ ] **Paso 2: Ejecutar la batería completa**

```bash
pytest -q
ruff check src scripts tests
cd frontend && npm run build
```

Esperado: todo verde. Anotar el número final de pruebas.

- [ ] **Paso 3: Actualizar la documentación**

- `README.md`: la sección nueva, el comando de ingesta de clima, las variables
  `INGESTA_AUTOMATICA` e `INGESTA_INTERVALO_MINUTOS`.
- La documentación HTML/PDF del escritorio: sección del Niño, tabla `clima_departamento`
  (pasan a ser 7 tablas), los endpoints nuevos (pasan a ser 31), el nombre nuevo de la
  aplicación, y el hallazgo del efecto de ENSO sobre el precio. Regenerar el PDF.

- [ ] **Paso 4: Commit final**

```bash
git add -A
git commit -m "Mantener el clima departamental al dia y actualizar la documentacion"
git push
```

---

## Verificación visual

Hay un conductor de navegador ya escrito, sin dependencias, que arranca Edge en modo
headless por CDP, entra con una cuenta real y captura cada sección:

```bash
node <scratchpad>/conducir.mjs <carpeta-de-salida>
```

Espera a que desaparezcan los carteles de carga antes de capturar. Si se añade una
sección nueva, la recorre sola: lee las pestañas de `nav.pestanas`.

**Mirar las capturas.** Una captura en negro o con «CALCULANDO» es un fallo, no una
sección que tardó.

## Autorrevisión del plan

- **Cobertura del spec:** título (T1), explicación de modelos (T2), endpoint de estado
  (T3), planificador (T4), refresco e indicador (T5), coordenadas (T6), recolector
  (T7), tabla (T8), ingesta (T9), endpoints (T10), sección y mapa divergente (T11),
  clima en el planificador y documentación (T12). Sin huecos.
- **Consistencia de nombres:** `codigo_dane`, `fecha_hora`, `temperatura`,
  `anomalia`, `fase`, `evidencia` se usan igual en las Tasks 7, 8, 10 y 11.
  `guardar_clima_departamento` y `anomalia_mensual` se definen una vez y se consumen
  con el mismo nombre.
- **Riesgo asumido:** los fixtures de `tests/conftest.py` (`cliente`, `sesion`,
  `cabecera_admin`) están escritos según la convención del repositorio pero **hay que
  confirmarlos leyendo el archivo** antes de la Task 3; si difieren, adaptar las
  pruebas, no el `conftest`.
