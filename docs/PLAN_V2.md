# Plan V2 — Plataforma de pronóstico energético (TdeA)

Estado: en ejecución · Rama `v2-plataforma`

## Hallazgos de la exploración de la API de XM (verificados en vivo)

| Hallazgo | Consecuencia |
|---|---|
| `DemaCome` / `MercadoComercializacion` → 29 mercados geográficos con demanda **horaria** | El mapa por departamento se alimenta de datos oficiales, no simulados |
| `ListadoRecursos` expone `Type` (HIDRAULICA/TERMICA/SOLAR/EOLICA/COGENERADOR) por planta | Cruzado con `Gene`/`Recurso` llena `generacion_hidraulica` y `generacion_termica`, hoy **vacías**, y añade solar/eólica |
| `EscDemUPMEAlto/Medio/Bajo` (mensual) | Proyección oficial UPME como contraste del pronóstico a 1 mes |
| `DispoReal`/`Recurso` | Llena `disponibilidad_real`, hoy vacía |
| El listado tiene 193 métricas; el proyecto usa 9 | Margen enorme de variables explicativas |
| No existe entidad "Departamento" en la API | El reparto mercado→departamento se hace con una tabla de pesos **documentada y visible en la UI** |
| Amazonas, Guainía, Vaupés, Vichada y San Andrés no aparecen | Son Zonas No Interconectadas (ZNI): el mapa debe decirlo, no inventar el dato |

## Fase 1 — Ingesta ampliada

1. `xm_client.py`: subir de 9 a ~30 métricas verificadas (horarias y diarias).
2. Generación por tecnología: `Gene`/`Recurso` agregada por `Type` de `ListadoRecursos`.
3. `xm_departamentos.py`: `DemaCome`/`MercadoComercializacion` + tabla de reparto a departamentos DANE.
4. `xm_upme.py`: escenarios UPME mensuales.
5. Modelo de datos: columnas nuevas en `datos_historicos`, tablas `demanda_departamento` y `proyeccion_upme`; migración Alembic.
6. Scripts de ingesta.

## Fase 2 — Motor predictivo y series de tiempo

7. Catálogo ampliado: baseline estacional, Ridge, ElasticNet, Random Forest, XGBoost, LightGBM, SARIMAX, Holt-Winters, LSTM.
8. Objetivo configurable: `precio_bolsa` o `demanda_real`.
9. Multihorizonte *direct multi-step*: 24 h, 168 h (1 semana), 720 h (1 mes).
10. Validación *walk-forward* (`TimeSeriesSplit`) e intervalos de predicción por cuantiles de residuos.
11. Métricas ampliadas: MAE, RMSE, MAPE, sMAPE, R², **MASE** (contra el baseline) y tiempo.
12. Importancia de variables por permutación.

## Fase 3 — API

13. `POST/GET /pronostico` con horizonte y banda de incertidumbre.
14. `GET /departamentos`, `/departamentos/{codigo}/serie`, `/departamentos/ranking`.
15. `GET /modelos/comparacion` — ganador por horizonte y recomendación.
16. `GET /datos/series`, `/datos/perfil-horario`, `/upme/escenarios`.

## Fase 4 — Frontend

17. Sistema de diseño nuevo (tema oscuro de sala de control + claro), tokens, tipografía, motion.
18. Login animado: red eléctrica viva en canvas, entrada escalonada, campos flotantes, transición al tablero.
19. Navegación por secciones: Pronóstico · Mapa · Modelos · Datos.
20. Gráficas dinámicas: horizonte conmutable, brush/zoom, banda de confianza, series múltiples, export.
21. Mapa coroplético interactivo de Colombia con panel de detalle por departamento.
22. Panel de comparación de modelos con importancia de variables.

## Fase 5 — Verificación

23. Pruebas nuevas + existentes, `ruff`, build del frontend e ingesta real de punta a punta.
