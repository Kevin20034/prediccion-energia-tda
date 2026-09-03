import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { decimales, marcaTemporal } from "../../formato";
import { COLOR, EJE, OTRAS_TECNOLOGIAS, TECNOLOGIAS } from "../../tokens";

/**
 * Mezcla de generación por tecnología, en porcentaje apilado.
 *
 * Se muestra la **proporción** y no la energía absoluta porque lo que explica
 * el precio no es cuánto se generó, sino de dónde salió: el mismo consumo
 * cubierto con agua o cubierto con gas da precios de bolsa completamente
 * distintos. En porcentaje, el desplazamiento hacia lo térmico durante El Niño
 * se ve de un vistazo; en kWh queda escondido bajo la variación de la demanda.
 *
 * Eólica y cogeneración se agrupan en "otras": juntas no llegan al 3 % del
 * sistema, y darles una banda propia gastaría dos colores de la paleta en
 * franjas invisibles.
 */

const ALTO = 240;

export default function GraficaMezcla({ datos = [], resolucion = "dia" }) {
  const serie = useMemo(() => aPorcentajes(datos), [datos]);

  if (serie.length < 2) return <div className="cargando">sin datos de generación</div>;

  return (
    <div className="grafica">
      <div className="leyenda">
        {TECNOLOGIAS.map((tec) => (
          <span className="leyenda__clave" key={tec.clave}>
            <i
              className="leyenda__cuadro"
              style={{ background: tec.color }}
              aria-hidden="true"
            />
            {tec.etiqueta}
          </span>
        ))}
      </div>

      <ResponsiveContainer width="100%" height={ALTO}>
        <AreaChart data={serie} margin={{ top: 6, right: 20, bottom: 4, left: 6 }}>
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
            width={44}
            domain={[0, 100]}
            ticks={[0, 25, 50, 75, 100]}
            tickFormatter={(v) => `${v} %`}
            tick={EJE}
            stroke={COLOR.linea}
          />
          <Tooltip content={<Pista resolucion={resolucion} />} />

          {TECNOLOGIAS.map((tec) => (
            <Area
              key={tec.clave}
              type="monotone"
              dataKey={tec.clave}
              stackId="mezcla"
              stroke={COLOR.panel}
              /* Un filete del color del fondo entre bandas contiguas: separa
                 las franjas sin introducir una línea de otro color. */
              strokeWidth={1}
              fill={tec.color}
              fillOpacity={0.88}
              isAnimationActive={false}
              name={tec.etiqueta}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function Pista({ active, payload, label, resolucion }) {
  if (!active || !payload?.length) return null;
  const etiquetas = new Map(TECNOLOGIAS.map((t) => [t.clave, t]));

  return (
    <div className="pista">
      <div className="pista__momento">{marcaTemporal(label, resolucion)}</div>
      {[...payload].reverse().map((fila) => (
        <div className="pista__linea" key={fila.dataKey}>
          <span className="pista__nombre">
            <i
              className="pista__punto"
              style={{ background: etiquetas.get(fila.dataKey)?.color }}
              aria-hidden="true"
            />
            {etiquetas.get(fila.dataKey)?.etiqueta}
          </span>
          <span className="pista__valor">{decimales(fila.value, 1)} %</span>
        </div>
      ))}
    </div>
  );
}

/**
 * Normaliza cada instante a 100 %.
 *
 * Las horas sin ningún dato de generación se descartan en vez de dibujarse
 * como 0 %: un hueco de datos y un sistema apagado no son lo mismo, y en un
 * área apilada el segundo se ve como un desplome del sistema eléctrico.
 */
function aPorcentajes(datos) {
  const salida = [];

  for (const punto of datos) {
    const componentes = {};
    let total = 0;

    for (const tec of TECNOLOGIAS) {
      const valor =
        tec.clave === "generacion_otras"
          ? OTRAS_TECNOLOGIAS.reduce((suma, c) => suma + (punto[c] ?? 0), 0)
          : punto[tec.clave] ?? 0;
      componentes[tec.clave] = valor;
      total += valor;
    }

    if (total <= 0) continue;

    salida.push({
      t: new Date(punto.fecha_hora).getTime(),
      ...Object.fromEntries(
        Object.entries(componentes).map(([clave, valor]) => [clave, (valor / total) * 100])
      ),
    });
  }

  return salida.sort((a, b) => a.t - b.t);
}
