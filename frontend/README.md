# Frontend — Precio de bolsa

Capa de presentación del sistema. React + Vite, consume la API REST del backend.

## Cómo ejecutarlo

Necesitas **dos terminales**: el backend y el frontend.

```bash
# Terminal 1 — backend (desde la raíz del proyecto)
cd energia-tda
.venv\Scripts\activate
uvicorn src.api.main:app --reload

# Terminal 2 — frontend
cd energia-tda\frontend
npm install        # solo la primera vez
npm run dev
```

Se abre solo en **http://localhost:5173**.

> Usa `localhost`, no `127.0.0.1`. Vite escucha en el nombre, no en la IP.

Entra con cualquiera de las cuentas de prueba, que aparecen listadas en la
propia pantalla de acceso (un clic las rellena):

| Rol | Correo | Contraseña |
|---|---|---|
| Administrador | `admin@tda.edu.co` | `Admin123*` |
| Analista | `analista@tda.edu.co` | `Analista123*` |
| Institucional | `consulta@tda.edu.co` | `Consulta123*` |

## Qué muestra

**La costura** es el elemento central: el punto exacto donde los datos medidos
se acaban y empieza la inferencia del modelo.

- A la izquierda, el último precio **observado** por XM: cifra turquesa, línea
  sólida en la gráfica.
- A la derecha, el precio **estimado** a 24 horas: cifra ámbar con subrayado
  discontinuo, línea de puntos sobre una trama diagonal.

El color codifica el dominio, no decora: frío es hidráulico, medido y barato;
cálido es térmico, inferido y caro. La trama diagonal dice, sin palabras, que
esa región no se midió.

Debajo, la comparación de los cuatro modelos con sus métricas, y el estado del
sistema con el nivel de los embalses y el fenómeno ENSO vigente — que es lo que
explica la forma de la curva de arriba.

## Acciones disponibles

| Botón | Endpoint | Rol necesario |
|---|---|---|
| Predecir 24 horas | `POST /predicciones` | Institucional |
| Descargar datos | `POST /datos/ingestar` | Analista |
| Entrenar modelos | `POST /entrenar` | Analista |

Al entrar como **Institucional**, los dos últimos aparecen deshabilitados con
una nota explicando por qué. Es la misma restricción que aplica el backend: la
interfaz la refleja, no la sustituye.

## Estructura

```
frontend/
├── index.html              tipografías: Archivo + IBM Plex Mono
├── vite.config.js          proxy /api → http://127.0.0.1:8000
└── src/
    ├── main.jsx
    ├── App.jsx             estado, carga y acciones
    ├── api.js              cliente HTTP y manejo del token
    ├── formato.js          números y fechas (ver nota de zona horaria)
    ├── estilos.css         sistema de diseño
    └── componentes/
        ├── Acceso.jsx          pantalla de entrada
        ├── Costura.jsx         los dos números: medido vs inferido
        ├── GraficaCostura.jsx  la gráfica y su costura
        ├── TablaModelos.jsx    comparación de modelos
        └── PanelEstado.jsx     estado del sistema y acciones
```

## Decisiones técnicas

**Proxy en vez de CORS.** Vite reenvía `/api` al backend, así que el navegador
solo habla con un origen. Elimina CORS como fuente de problemas y refleja cómo
funcionaría en producción detrás de un nginx.

**Todo dato numérico en monoespaciada.** Cuando se comparan cuatro modelos
columna a columna, la alineación tabular es funcional, no estética: permite leer
las diferencias de magnitud de un vistazo.

**Fechas formateadas en UTC.** Las marcas de tiempo de XM son hora local de
Colombia y el backend las trata como ingenuas. Al guardarse en una columna
`TIMESTAMPTZ`, PostgreSQL las etiqueta como UTC. Si el navegador las convirtiera
a hora local mostraría un dato de las 00:00 como las 19:00 del día anterior. Ver
la nota completa en [`src/formato.js`](src/formato.js).

**Ventana de una semana en la gráfica.** Con dos semanas, las 24 horas predichas
ocupaban un 7 % del ancho y la costura quedaba aplastada contra el borde.

## Compilar para producción

```bash
npm run build      # genera dist/
npm run preview    # sirve dist/ para comprobarlo
```

El `dist/` resultante son archivos estáticos: se pueden servir desde nginx, o
montarlos en el propio FastAPI con `StaticFiles`. En producción hay que sustituir
el proxy de Vite por la configuración equivalente del servidor web.
