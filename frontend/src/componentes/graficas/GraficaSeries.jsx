import { useMemo, useRef } from "react";
import {
  Brush,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { decimales, marcaTemporal } from "../../formato";
import { descargarGrafica, descargarTexto, nombreConFecha } from "../../descargas";
import { COLOR, EJE, PALETA_SERIES } from "../../tokens";

/**
 * Series temporales conmutables.
 *
 * **Un eje por gráfica, siempre.** Cuando el usuario activa variables de
 * unidades distintas —precio en COP/kWh y demanda en kWh, por ejemplo— no se
 * dibuja un segundo eje a la derecha: se dibuja una gráfica por unidad, una
 * debajo de otra y compartiendo el eje temporal. Superponer dos escalas
 * distintas en un mismo marco permite que dos curvas se crucen donde el
 * modelador quiera con solo mover el rango, y esa es la manera más fácil de
 * sugerir una correlación que no existe.
 *
 * El `Brush` inferior recorta el rango en el cliente. Cambiar la resolución
 * (hora / día / semana / mes) es otra cosa: eso vuelve a pedir los datos ya
 * agregados al servidor, que es donde agregar es barato.
 */

const ALTO = 250;

export default function GraficaSeries({
  respuesta,
  resolucion = "hora",
  cargando,
  alFallar,
  informe,
}) {
  const datos = useMemo(() => prepararComparacion(respuesta), [respuesta]);
  const nodo = useRef(null);

  if (cargando) return <div className="cargando">consultando series</div>;
  if (!datos.series.length) {
    return <div className="cargando">elige al menos una variable</div>;
  }

  return (
    <div className="grafica" ref={nodo}>
          <div className="leyenda">
            {datos.series.map((serie) => (
              <span className="leyenda__clave" key={serie.variable}>
                <i
                  className="leyenda__trazo"
                  style={{ color: serie.color }}
                  aria-hidden="true"
                />
                {serie.etiqueta}
              </span>
            ))}
            <span className="hueco" />
            <span className="leyenda__clave">índice base 100</span>
            <button
              type="button"
              className="boton boton--fantasma grafica__descargar"
              onClick={() =>
                descargarGrafica(
                  nodo.current,
                  nombreConFecha("comparacion-series")
                ).catch(alFallar)
              }
              title="Descargar esta gráfica como PNG"
            >
              Descargar gráfico
            </button>
            <button
              type="button"
              className="boton boton--fantasma grafica__descargar"
              onClick={() => descargarTexto(informe, nombreConFecha("informe-series"))}
              title="Descargar el informe de la comparación"
            >
              Descargar informe
            </button>
          </div>

          <ResponsiveContainer width="100%" height={ALTO}>
            <LineChart data={datos.filas} margin={{ top: 8, right: 26, bottom: 4, left: 6 }}>
              <CartesianGrid stroke={COLOR.linea} vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => marcaTemporal(t, resolucion)}
                tick={EJE}
                stroke={COLOR.linea}
                minTickGap={56}
              />
              <YAxis
                width={62}
                tick={EJE}
                stroke={COLOR.linea}
                tickFormatter={(v) => compacto(v)}
                domain={["auto", "auto"]}
              />
              <Tooltip
                content={<Pista series={datos.series} resolucion={resolucion} />}
                cursor={{ stroke: COLOR.lineaFuerte, strokeDasharray: "3 3" }}
              />
              {datos.series.map((serie) => (
                <Line
                  key={serie.variable}
                  type="monotone"
                  dataKey={serie.variable}
                  stroke={serie.color}
                  strokeWidth={2}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                  name={serie.etiqueta}
                />
              ))}
              {/* Solo la última gráfica lleva selector de rango: las de arriba
                  comparten eje temporal y arrastrarlo en dos sitios distintos
                  sería una fuente de confusión, no de control. */}
              {datos.filas.length > 40 && (
                <Brush
                  dataKey="t"
                  height={22}
                  travellerWidth={8}
                  stroke={COLOR.lineaFuerte}
                  fill={COLOR.hundido}
                  tickFormatter={() => ""}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
    </div>
  );
}

function Pista({ active, payload, label, series, resolucion }) {
  if (!active || !payload?.length) return null;
  const porVariable = new Map(series.map((s) => [s.variable, s]));

  return (
    <div className="pista">
      <div className="pista__momento">{marcaTemporal(label, resolucion)}</div>
      {payload
        .filter((fila) => fila.value != null)
        .map((fila) => (
          <div className="pista__linea" key={fila.dataKey}>
            <span className="pista__nombre">
              <i
                className="pista__punto"
                style={{ background: porVariable.get(fila.dataKey)?.color }}
                aria-hidden="true"
              />
              {porVariable.get(fila.dataKey)?.etiqueta ?? fila.dataKey}
            </span>
            <span className="pista__valor">{decimales(fila.payload.originales?.[fila.dataKey], 1)}</span>
          </div>
        ))}
      <div className="pista__nota">valor original · escala comparativa base 100</div>
    </div>
  );
}

function prepararComparacion(respuesta) {
  if (!respuesta?.series?.length) return { series: [], filas: [] };

  const series = respuesta.series.map((serie, indice) => ({
    variable: serie.variable,
    etiqueta: serie.etiqueta,
    unidad: serie.unidad,
    color: PALETA_SERIES[indice % PALETA_SERIES.length],
  }));
  const filas = new Map();
  const bases = new Map();

  for (const serie of respuesta.series) {
    for (const punto of serie.puntos) {
      const t = new Date(punto.fecha_hora).getTime();
      if (!filas.has(t)) filas.set(t, { t, originales: {} });
      const fila = filas.get(t);
      fila.originales[serie.variable] = punto.valor;
      if (punto.valor != null && !bases.has(serie.variable) && punto.valor !== 0) {
        bases.set(serie.variable, punto.valor);
      }
      const base = bases.get(serie.variable);
      fila[serie.variable] = punto.valor == null || !base ? null : (punto.valor / base) * 100;
    }
  }

  return { series, filas: [...filas.values()].sort((a, b) => a.t - b.t) };
}

/**
 * Agrupa las series por unidad y funde cada grupo en una tabla ancha.
 *
 * La API devuelve una lista de puntos por serie; Recharts necesita una fila por
 * instante con una columna por serie. La fusión se hace por marca de tiempo,
 * así que una serie con huecos deja `undefined` en su columna y la línea se
 * corta ahí en vez de saltar el hueco con una recta inventada.
 */
function agruparPorUnidad(respuesta) {
  if (!respuesta?.series?.length) return [];

  const colorDe = new Map(
    respuesta.series.map((s, i) => [s.variable, PALETA_SERIES[i % PALETA_SERIES.length]])
  );

  const porUnidad = new Map();
  for (const serie of respuesta.series) {
    const clave = serie.unidad || "";
    if (!porUnidad.has(clave)) porUnidad.set(clave, []);
    porUnidad.get(clave).push(serie);
  }

  return [...porUnidad.entries()].map(([unidad, series]) => {
    const filas = new Map();
    for (const serie of series) {
      for (const punto of serie.puntos) {
        const t = new Date(punto.fecha_hora).getTime();
        if (!filas.has(t)) filas.set(t, { t });
        filas.get(t)[serie.variable] = punto.valor;
      }
    }
    return {
      unidad,
      series: series.map((s) => ({
        variable: s.variable,
        etiqueta: s.etiqueta,
        color: colorDe.get(s.variable),
      })),
      datos: [...filas.values()].sort((a, b) => a.t - b.t),
    };
  });
}

/** Notación compacta para los ejes: 8 500 000 se lee mal, 8,5 M se lee bien. */
function compacto(valor) {
  const abs = Math.abs(valor);
  if (abs >= 1e9) return `${decimales(valor / 1e9, 1)} G`;
  if (abs >= 1e6) return `${decimales(valor / 1e6, 1)} M`;
  if (abs >= 1e4) return `${decimales(valor / 1e3, 0)} k`;
  return decimales(valor, abs < 10 ? 1 : 0);
}
