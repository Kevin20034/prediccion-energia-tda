import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { decimales } from "../../formato";
import { COLOR, EJE } from "../../tokens";

/**
 * Perfil por hora del día: la curva de carga.
 *
 * Una serie temporal no enseña esto. Al promediar semanas enteras, el doble
 * pico —el de la mañana y el de las siete de la tarde— se pierde entre la
 * variación de un día a otro. Aquí cada punto es la media de esa hora, y la
 * separación entre días laborables y fin de semana muestra de dónde viene el
 * pico: cuando la industria para, la curva se aplana.
 *
 * Dos series y ambas van con leyenda y etiqueta directa al final del trazo, de
 * modo que la identidad no depende solo del color.
 */

const ALTO = 230;

export default function GraficaPerfil({ perfil = [], unidad = "", escala = 1 }) {
  if (!perfil.length) return <div className="cargando">sin perfil disponible</div>;

  const datos = perfil.map((p) => ({
    hora: p.hora,
    laboral: p.laboral == null ? null : p.laboral / escala,
    fin_semana: p.fin_semana == null ? null : p.fin_semana / escala,
  }));

  return (
    <div className="grafica">
      <div className="leyenda">
        <span className="leyenda__clave" style={{ color: COLOR.observado }}>
          <i className="leyenda__trazo" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>días laborables</span>
        </span>
        <span className="leyenda__clave" style={{ color: COLOR.tinta3 }}>
          <i className="leyenda__trazo leyenda__trazo--punteado" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>fines de semana</span>
        </span>
        <span className="hueco" />
        <span className="leyenda__clave">{unidad}</span>
      </div>

      <ResponsiveContainer width="100%" height={ALTO}>
        <LineChart data={datos} margin={{ top: 8, right: 22, bottom: 4, left: 6 }}>
          <CartesianGrid stroke={COLOR.linea} vertical={false} />
          <XAxis
            dataKey="hora"
            tick={EJE}
            stroke={COLOR.linea}
            ticks={[0, 4, 8, 12, 16, 20, 23]}
            tickFormatter={(h) => `${String(h).padStart(2, "0")}h`}
          />
          <YAxis
            width={58}
            tick={EJE}
            stroke={COLOR.linea}
            tickFormatter={(v) => decimales(v, 1)}
            domain={["auto", "auto"]}
          />
          <Tooltip
            content={<Pista unidad={unidad} />}
            cursor={{ stroke: COLOR.lineaFuerte, strokeDasharray: "3 3" }}
          />
          <Line
            type="monotone"
            dataKey="laboral"
            stroke={COLOR.observado}
            strokeWidth={2.2}
            dot={false}
            isAnimationActive={false}
            name="Laborables"
          />
          <Line
            type="monotone"
            dataKey="fin_semana"
            stroke={COLOR.tinta3}
            strokeWidth={2}
            strokeDasharray="5 4"
            dot={false}
            isAnimationActive={false}
            name="Fin de semana"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Pista({ active, payload, label, unidad }) {
  if (!active || !payload?.length) return null;
  const nombres = { laboral: "Laborables", fin_semana: "Fin de semana" };
  const colores = { laboral: COLOR.observado, fin_semana: COLOR.tinta3 };

  return (
    <div className="pista">
      <div className="pista__momento">{String(label).padStart(2, "0")}:00</div>
      {payload.map((fila) => (
        <div className="pista__linea" key={fila.dataKey}>
          <span className="pista__nombre">
            <i
              className="pista__punto"
              style={{ background: colores[fila.dataKey] }}
              aria-hidden="true"
            />
            {nombres[fila.dataKey]}
          </span>
          <span className="pista__valor">{decimales(fila.value, 2)}</span>
        </div>
      ))}
      <div className="pista__nota">{unidad}</div>
    </div>
  );
}
