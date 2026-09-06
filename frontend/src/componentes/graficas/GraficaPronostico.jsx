import { useMemo } from "react";
import {
  Area,
  Bar,
  Brush,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { decimales, marcaTemporal } from "../../formato";
import { COLOR, EJE } from "../../tokens";
import { movimientoReducido } from "../animacion";

/**
 * La gráfica de la costura: el elemento central de toda la interfaz.
 *
 * Muestra el punto exacto donde los datos medidos se acaban y empieza la
 * inferencia del modelo.
 *
 *   izquierda → línea sólida turquesa      → observado (medido por XM)
 *   derecha   → línea discontinua ámbar    → pronosticado (inferido)
 *   sombra    → banda del 80 %             → hasta dónde puede equivocarse
 *   fondo     → trama diagonal             → "esta región no está medida"
 *
 * La banda no es un adorno. Un pronóstico a un mes dibujado como una línea
 * limpia transmite una precisión que no tiene; la banda es la forma honesta de
 * enseñar el mismo número.
 *
 * Implementación de la banda: dos áreas apiladas. La inferior va de cero al
 * límite bajo y es invisible; la superior tiene el espesor del intervalo y es
 * la que se pinta. Es más robusto que un área de rango, que en Recharts obliga
 * a que todos los puntos de la serie tengan pareja de valores —y los puntos
 * observados, por definición, no la tienen.
 */

const ALTO = 300;

export default function GraficaPronostico({
  observado = [],
  pronostico = [],
  unidad = "COP/kWh",
  conBrush = false,
  animar = false,
  forma = "linea",
}) {
  const serie = useMemo(() => combinar(observado, pronostico), [observado, pronostico]);
  const dominio = useMemo(() => dominioVertical(serie), [serie]);

  // La animación solo se ofrece en la vista de usuario. En el tablero técnico
  // se cambia de horizonte y de variable constantemente, y redibujar la serie
  // con un barrido cada vez convierte una herramienta de consulta en algo que
  // hay que esperar.
  const animacion = animar && !movimientoReducido();

  if (serie.length < 2) {
    return <div className="cargando">sin datos suficientes para trazar</div>;
  }

  const corte = pronostico.length && observado.length
    ? new Date(observado.at(-1).fecha_hora).getTime()
    : null;
  const fin = serie.at(-1).t;

  return (
    <div className="grafica">
      <div className="leyenda">
        <span className="leyenda__clave" style={{ color: COLOR.observado }}>
          <i className="leyenda__trazo" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>observado · XM</span>
        </span>
        <span className="leyenda__clave" style={{ color: COLOR.pronostico }}>
          <i className="leyenda__trazo leyenda__trazo--punteado" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>pronosticado · modelo</span>
        </span>
        <span className="leyenda__clave">
          <i
            className="leyenda__banda"
            style={{ background: COLOR.pronostico }}
            aria-hidden="true"
          />
          banda del 80 %
        </span>
      </div>

      <ResponsiveContainer width="100%" height={ALTO}>
        <ComposedChart
          data={serie}
          margin={{ top: 20, right: 34, bottom: conBrush ? 4 : 6, left: 6 }}
        >
          <defs>
            <pattern
              id="trama-futuro"
              width="7"
              height="7"
              patternTransform="rotate(45)"
              patternUnits="userSpaceOnUse"
            >
              <line
                x1="0"
                y1="0"
                x2="0"
                y2="7"
                stroke={COLOR.pronostico}
                strokeWidth="1"
                opacity="0.07"
              />
            </pattern>
          </defs>

          <CartesianGrid stroke={COLOR.linea} vertical={false} />

          {corte && (
            <ReferenceArea x1={corte} x2={fin} fill="url(#trama-futuro)" strokeOpacity={0} />
          )}

          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => marcaTemporal(t, resolucionDe(serie))}
            tick={EJE}
            stroke={COLOR.linea}
            minTickGap={56}
          />
          <YAxis
            width={58}
            tick={EJE}
            stroke={COLOR.linea}
            tickFormatter={(v) => decimales(v, 0)}
            domain={dominio}
            /* Imprescindible junto al dominio calculado. Recharts apila los
               nulos de la banda como ceros, así que sin esto ampliaría el
               dominio hasta el 0 para "caber" esos ceros fantasma y volvería a
               aplastar la serie contra el borde superior. Lo único que queda
               fuera del recorte es la base invisible de la banda. */
            allowDataOverflow
          />

          <Tooltip
            content={<Pista unidad={unidad} />}
            cursor={{ stroke: COLOR.lineaFuerte, strokeDasharray: "3 3" }}
          />

          {/* Banda: base invisible + espesor pintado. */}
          <Area
            dataKey="bandaBase"
            stackId="banda"
            stroke="none"
            fill="none"
            isAnimationActive={false}
            connectNulls={false}
            legendType="none"
            activeDot={false}
          />
          <Area
            dataKey="bandaEspesor"
            stackId="banda"
            stroke="none"
            fill={COLOR.pronosticoClaro}
            fillOpacity={0.24}
            /* La banda entra después de las líneas: primero se ve el trazo y
               luego crece la incertidumbre a su alrededor, que es el orden en
               que se lee la gráfica. */
            isAnimationActive={animacion}
            animationBegin={animacion ? 700 : 0}
            animationDuration={600}
            connectNulls={false}
            legendType="none"
            activeDot={false}
          />

          {corte && (
            <ReferenceLine
              x={corte}
              stroke={COLOR.tinta2}
              strokeWidth={1}
              label={{
                value: "ahora",
                position: "top",
                fontSize: 9,
                fontFamily: "IBM Plex Mono, monospace",
                fill: COLOR.tinta2,
                letterSpacing: "0.16em",
              }}
            />
          )}

          {/* La forma la elige quien mira: la línea enseña el recorrido, el
              área el volumen y las barras el valor de cada momento. Lo que no
              cambia nunca es el código de color ni el trazo discontinuo del
              pronóstico: eso es el dato, no la presentación. */}
          {forma === "barras" ? (
            <>
              <Bar
                dataKey="observado"
                fill={COLOR.observado}
                isAnimationActive={animacion}
                animationDuration={800}
                name="Observado"
              />
              <Bar
                dataKey="estimado"
                fill={COLOR.pronostico}
                fillOpacity={0.75}
                isAnimationActive={animacion}
                animationBegin={animacion ? 400 : 0}
                animationDuration={700}
                name="Pronosticado"
              />
            </>
          ) : forma === "area" ? (
            <>
              <Area
                type="monotone"
                dataKey="observado"
                stroke={COLOR.observado}
                strokeWidth={2}
                fill={COLOR.observado}
                fillOpacity={0.22}
                dot={false}
                connectNulls={false}
                isAnimationActive={animacion}
                animationDuration={800}
                name="Observado"
              />
              <Area
                type="monotone"
                dataKey="estimado"
                stroke={COLOR.pronostico}
                strokeWidth={2}
                strokeDasharray="5 4"
                fill={COLOR.pronostico}
                fillOpacity={0.18}
                dot={false}
                connectNulls={false}
                isAnimationActive={animacion}
                animationBegin={animacion ? 500 : 0}
                animationDuration={700}
                name="Pronosticado"
              />
            </>
          ) : (
            <>
              <Line
                type="monotone"
                dataKey="observado"
                stroke={COLOR.observado}
                strokeWidth={2}
                dot={false}
                connectNulls={false}
                isAnimationActive={animacion}
                animationDuration={800}
                name="Observado"
              />
              <Line
                type="monotone"
                dataKey="estimado"
                stroke={COLOR.pronostico}
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                connectNulls={false}
                isAnimationActive={animacion}
                animationBegin={animacion ? 500 : 0}
                animationDuration={700}
                name="Pronosticado"
              />
            </>
          )}

          {conBrush && (
            <Brush
              dataKey="t"
              height={22}
              travellerWidth={8}
              stroke={COLOR.lineaFuerte}
              fill={COLOR.hundido}
              tickFormatter={() => ""}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function Pista({ active, payload, unidad }) {
  if (!active || !payload?.length) return null;

  const punto = payload[0].payload;
  const esEstimado = punto.estimado != null && punto.observado == null;
  const valor = esEstimado ? punto.estimado : punto.observado;
  if (valor == null) return null;

  const color = esEstimado ? COLOR.pronosticoClaro : COLOR.observadoClaro;

  return (
    <div className="pista">
      <div className="pista__momento">{marcaTemporal(punto.t, "hora")}</div>
      <div className="pista__linea">
        <span className="pista__nombre">
          <i className="pista__punto" style={{ background: color }} aria-hidden="true" />
          {esEstimado ? "estimado" : "observado"}
        </span>
        <span className="pista__valor" style={{ color }}>
          {decimales(valor, 1)}
        </span>
      </div>
      {esEstimado && punto.bandaBase != null && (
        <div className="pista__nota">
          banda 80 %: {decimales(punto.bandaBase, 0)} –{" "}
          {decimales(punto.bandaBase + punto.bandaEspesor, 0)} {unidad}
        </div>
      )}
      {!esEstimado && <div className="pista__nota">{unidad}</div>}
    </div>
  );
}

/**
 * Une las dos series en un solo array para Recharts.
 *
 * El último punto observado lleva TAMBIÉN el valor estimado, para que las dos
 * líneas se toquen en la costura en vez de dejar un salto visual que se leería
 * como un cambio brusco del mercado.
 */
function combinar(observado, pronostico) {
  const puntos = observado.map((d) => ({
    t: new Date(d.fecha_hora).getTime(),
    observado: d.valor,
    estimado: null,
    bandaBase: null,
    bandaEspesor: null,
  }));

  if (puntos.length && pronostico.length) {
    const ultimo = puntos.at(-1);
    ultimo.estimado = ultimo.observado;
    ultimo.bandaBase = ultimo.observado;
    ultimo.bandaEspesor = 0;
  }

  for (const p of pronostico) {
    const base = p.limite_inferior;
    const techo = p.limite_superior;
    puntos.push({
      t: new Date(p.fecha_objetivo).getTime(),
      observado: null,
      estimado: p.valor_estimado,
      bandaBase: base ?? null,
      bandaEspesor: base != null && techo != null ? Math.max(0, techo - base) : null,
    });
  }

  return puntos.sort((a, b) => a.t - b.t);
}

/**
 * Rango vertical calculado a mano, y no `["auto", "auto"]`.
 *
 * La banda de incertidumbre se dibuja como dos áreas apiladas, y Recharts
 * incluye el cero en el dominio de cualquier serie apilada. El resultado era un
 * eje que empezaba en 0 con los datos comprimidos en la franja superior: en una
 * serie de precio que oscila entre 500 y 1 200 COP/kWh, eso convierte
 * variaciones grandes en una línea casi plana.
 *
 * Se toma el rango real de todo lo dibujado —observado, estimado y los dos
 * extremos de la banda— y se le añade un 6 % de aire arriba y abajo para que
 * los picos no toquen el borde del panel.
 */
function dominioVertical(serie) {
  const valores = [];
  for (const punto of serie) {
    if (punto.observado != null) valores.push(punto.observado);
    if (punto.estimado != null) valores.push(punto.estimado);
    if (punto.bandaBase != null) {
      valores.push(punto.bandaBase, punto.bandaBase + (punto.bandaEspesor ?? 0));
    }
  }
  if (!valores.length) return ["auto", "auto"];

  const minimo = Math.min(...valores);
  const maximo = Math.max(...valores);
  const aire = (maximo - minimo) * 0.06 || Math.abs(maximo) * 0.06 || 1;

  // Se redondea a un escalón legible. Con el dominio en crudo, Recharts
  // reparte las marcas sobre los extremos exactos y el eje acaba rotulado
  // 485 · 685 · 885, que nadie usa para estimar un valor de un vistazo.
  const paso = escalonLegible((maximo + aire - (minimo - aire)) / 4);
  return [
    Math.floor((minimo - aire) / paso) * paso,
    Math.ceil((maximo + aire) / paso) * paso,
  ];
}

/** Redondea un intervalo al 1, 2, 5 o 10 de su orden de magnitud. */
function escalonLegible(bruto) {
  if (!(bruto > 0)) return 1;
  const magnitud = 10 ** Math.floor(Math.log10(bruto));
  const normalizado = bruto / magnitud;
  const escalon = normalizado <= 1 ? 1 : normalizado <= 2 ? 2 : normalizado <= 5 ? 5 : 10;
  return escalon * magnitud;
}

/** Escoge el formato del eje según cuánto tiempo abarca la serie. */
function resolucionDe(serie) {
  const dias = (serie.at(-1).t - serie[0].t) / 86_400_000;
  if (dias > 120) return "mes";
  if (dias > 10) return "dia";
  return "hora";
}
