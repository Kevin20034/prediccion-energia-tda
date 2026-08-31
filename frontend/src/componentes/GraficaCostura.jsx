import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { cop, hora } from "../formato";

/**
 * La gráfica de la costura.
 *
 * Es el elemento central de toda la interfaz: muestra el punto exacto donde
 * los datos medidos se acaban y empieza la inferencia del modelo.
 *
 *   izquierda  → línea sólida turquesa   → observado (hidráulico, conocido)
 *   derecha    → línea discontinua ámbar → predicho  (térmico, inferido)
 *   fondo      → trama diagonal          → "esta región no está medida"
 *
 * El color no decora: codifica el estado epistémico del dato.
 */
export default function GraficaCostura({ observado, predicho }) {
  const serie = combinar(observado, predicho);

  if (serie.length < 2) {
    return (
      <div className="cargando">sin datos suficientes para trazar</div>
    );
  }

  const costura = predicho.length ? new Date(observado.at(-1).fecha_hora).getTime() : null;
  const finPredicho = serie.at(-1).t;

  return (
    <div className="gráfica">
      <div className="grafica__leyenda">
        <span className="grafica__clave">
          <i className="grafica__trazo" aria-hidden="true" />
          observado · XM
        </span>
        <span className="grafica__clave">
          <i className="grafica__trazo grafica__trazo--inferido" aria-hidden="true" />
          estimado · modelo
        </span>
      </div>

      <ResponsiveContainer width="100%" height={264}>
        {/* Margen superior para que quepa la etiqueta "ahora"; derecho, para que
            la última marca del eje no se corte contra el borde del panel. */}
        <LineChart data={serie} margin={{ top: 18, right: 38, bottom: 4, left: 4 }}>
          <defs>
            {/* La trama marca visualmente la región no medida. */}
            <pattern
              id="hachurado"
              width="7"
              height="7"
              patternTransform="rotate(45)"
              patternUnits="userSpaceOnUse"
            >
              <line x1="0" y1="0" x2="0" y2="7" stroke="#b45309" strokeWidth="1" opacity="0.14" />
            </pattern>
          </defs>

          <CartesianGrid stroke="#e3e9ee" vertical={false} />

          {costura && (
            <ReferenceArea x1={costura} x2={finPredicho} fill="url(#hachurado)" strokeOpacity={0} />
          )}

          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={hora}
            tick={{ fontSize: 10, fontFamily: "IBM Plex Mono, monospace", fill: "#7a8ea0" }}
            stroke="#cfd8e0"
            minTickGap={54}
          />
          <YAxis
            width={52}
            tick={{ fontSize: 10, fontFamily: "IBM Plex Mono, monospace", fill: "#7a8ea0" }}
            stroke="#cfd8e0"
            tickFormatter={(v) => Math.round(v)}
            domain={["auto", "auto"]}
          />

          <Tooltip content={<Pista />} cursor={{ stroke: "#a3b3c1", strokeDasharray: "3 3" }} />

          {costura && (
            <ReferenceLine
              x={costura}
              stroke="#45596b"
              strokeWidth={1}
              label={{
                value: "ahora",
                position: "top",
                fontSize: 9,
                fontFamily: "IBM Plex Mono, monospace",
                fill: "#45596b",
                letterSpacing: "0.14em",
              }}
            />
          )}

          <Line
            type="monotone"
            dataKey="observado"
            stroke="#0d6e6e"
            strokeWidth={1.6}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            name="Observado"
          />
          <Line
            type="monotone"
            dataKey="estimado"
            stroke="#b45309"
            strokeWidth={1.8}
            strokeDasharray="5 4"
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
            name="Estimado"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Pista({ active, payload }) {
  if (!active || !payload?.length) return null;

  const punto = payload[0].payload;
  const esEstimado = punto.estimado != null && punto.observado == null;
  const valor = esEstimado ? punto.estimado : punto.observado;

  return (
    <div className="pista">
      <div className="pista__momento">{hora(punto.t)}</div>
      <div className="pista__valor" style={{ color: esEstimado ? "#b45309" : "#095353" }}>
        {cop(valor)} <span style={{ fontWeight: 400, fontSize: 10 }}>COP/kWh</span>
      </div>
      <div className="pista__momento" style={{ marginTop: 3, marginBottom: 0 }}>
        {esEstimado ? "estimado" : "observado"}
      </div>
    </div>
  );
}

/**
 * Une las dos series en un solo array para Recharts.
 *
 * El último punto observado lleva TAMBIÉN el valor `estimado`, para que las
 * dos líneas se toquen en la costura en vez de dejar un salto visual.
 */
function combinar(observado, predicho) {
  const puntos = observado.map((d) => ({
    t: new Date(d.fecha_hora).getTime(),
    observado: d.precio_bolsa,
    estimado: null,
  }));

  if (puntos.length && predicho.length) {
    puntos.at(-1).estimado = puntos.at(-1).observado;
  }

  for (const p of predicho) {
    puntos.push({
      t: new Date(p.fecha_objetivo).getTime(),
      observado: null,
      estimado: p.precio_estimado,
    });
  }

  return puntos.sort((a, b) => a.t - b.t);
}
