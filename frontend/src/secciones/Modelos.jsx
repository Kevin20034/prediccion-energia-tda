import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import * as api from "../api";
import { Cargando, Conmutador, Panel, Vacio, Veredicto } from "../componentes/ui";
import { decimales, fechaHora } from "../formato";
import { COLOR, EJE, FAMILIAS } from "../tokens";

const OBJETIVOS = [
  { valor: "precio_bolsa", etiqueta: "Precio de bolsa" },
  { valor: "demanda_real", etiqueta: "Demanda" },
];

const HORIZONTES = [
  { valor: 24, etiqueta: "24 h" },
  { valor: 168, etiqueta: "7 días" },
  { valor: 720, etiqueta: "30 días" },
];

const BASELINE = "baseline_estacional";

export default function Modelos({ puedeOperar, alFallar, alAvisar }) {
  const [objetivo, setObjetivo] = useState("precio_bolsa");
  const [horizonte, setHorizonte] = useState(24);
  const [comparacion, setComparacion] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [entrenando, setEntrenando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      setComparacion(await api.comparacionModelos(objetivo));
    } catch (error) {
      alFallar(error);
      setComparacion(null);
    } finally {
      setCargando(false);
    }
  }, [objetivo, alFallar]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const filas = useMemo(
    () =>
      (comparacion?.filas ?? [])
        .filter((f) => f.horizonte_horas === horizonte)
        .sort((a, b) => a.rmse - b.rmse),
    [comparacion, horizonte]
  );

  const ganador = (comparacion?.ganadores ?? []).find(
    (g) => g.horizonte_horas === horizonte && g.objetivo === objetivo
  );

  const referencia = filas.find((f) => f.nombre_modelo === BASELINE);
  const importancia = Object.entries(comparacion?.importancia_ganador ?? {}).slice(0, 14);

  async function entrenar() {
    setEntrenando(true);
    try {
      const resultado = await api.entrenar({ objetivo, horizonte, criterio: "rmse" });
      alAvisar({
        tipo: "ok",
        texto: `Entrenamiento completado. Mejor modelo a ${horizonte} h: ${resultado.mejor_modelo}.`,
      });
      await cargar();
    } catch (error) {
      alFallar(error);
    } finally {
      setEntrenando(false);
    }
  }

  return (
    <div className="seccion">
      <header className="seccion__cabecera">
        <div>
          <div className="rotulo">Analítica predictiva</div>
          <h1 className="seccion__titulo">Comparación de modelos</h1>
          <p className="seccion__nota">
            Nueve modelos de cinco familias compiten en cada horizonte. La fila de
            referencia es el <b>pronóstico ingenuo estacional</b>, que se limita a repetir
            el ciclo anterior: un modelo que no le gane no justifica su complejidad, por
            alto que sea su R².
          </p>
        </div>

        <div className="fila">
          <Conmutador
            etiqueta="Variable"
            opciones={OBJETIVOS}
            valor={objetivo}
            alCambiar={setObjetivo}
          />
          <Conmutador
            etiqueta="Horizonte"
            opciones={HORIZONTES}
            valor={horizonte}
            alCambiar={setHorizonte}
          />
        </div>
      </header>

      {ganador && (
        <div style={{ marginBottom: 16 }}>
          <Veredicto
            texto={ganador.veredicto}
            sinVentaja={(ganador.mejora_sobre_baseline ?? 0) <= 0}
          />
        </div>
      )}

      <div className="rejilla rejilla--dos">
        <div className="pila">
          <Panel
            rotulo={`${filas.length} modelos · horizonte ${horizonte} h`}
            titulo="Error en el conjunto de prueba"
            acciones={
              puedeOperar && (
                <button
                  className="boton boton--solido"
                  onClick={entrenar}
                  disabled={entrenando}
                  style={{ width: "auto" }}
                >
                  {entrenando ? "Entrenando…" : "Reentrenar este horizonte"}
                </button>
              )
            }
            pie="RMSE penaliza más los errores grandes que el MAE: en un mercado con picos de escasez, equivocarse mucho una vez cuesta más que equivocarse poco muchas veces. Por eso es el criterio de selección."
          >
            {cargando ? (
              <Cargando texto="consultando entrenamientos" />
            ) : filas.length === 0 ? (
              <Vacio
                titulo="Sin entrenamientos para este horizonte"
                texto={
                  puedeOperar
                    ? "Entrena este horizonte para poblar la tabla comparativa."
                    : "Un usuario con rol Analista debe entrenar primero este horizonte."
                }
              />
            ) : (
              <TablaModelos filas={filas} referencia={referencia} />
            )}
          </Panel>

          {filas.length > 0 && (
            <Panel
              rotulo="Lectura visual"
              titulo="RMSE por modelo"
              ajustado
              pie="La línea vertical marca el error del pronóstico ingenuo. Todo lo que quede a su izquierda aporta; lo que quede a su derecha, no."
              >
              <GraficaRmse filas={filas} referencia={referencia} />
            </Panel>
          )}
        </div>

        <div className="pila">
          <Panel rotulo="Conclusión" titulo="Ganador por horizonte">
            {(comparacion?.ganadores ?? [])
              .filter((g) => g.objetivo === objetivo)
              .map((g) => (
                <div className="lectura" key={g.horizonte_horas}>
                  <span className="rotulo">{g.etiqueta}</span>
                  <span className="lectura__valor">
                    {g.nombre_modelo}
                    <span style={{ color: COLOR.tinta3, marginLeft: 8 }}>
                      {g.mejora_sobre_baseline == null
                        ? ""
                        : `${g.mejora_sobre_baseline > 0 ? "−" : "+"}${Math.abs(
                            g.mejora_sobre_baseline
                          ).toFixed(1)} % error`}
                    </span>
                  </span>
                </div>
              ))}
            <p className="acciones__nota">{comparacion?.recomendacion}</p>
          </Panel>

          {importancia.length > 0 && (
            <Panel
              rotulo="Modelo ganador"
              titulo="Variables más influyentes"
              pie="Importancia por permutación: cuánto empeora el error real al barajar cada variable. No tiene el sesgo hacia variables de muchos valores distintos que arrastran las importancias internas de los árboles."
            >
              <GraficaImportancia importancia={importancia} />
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}

function TablaModelos({ filas, referencia }) {
  const peor = Math.max(...filas.map((f) => f.rmse));

  return (
    <div className="envoltura-tabla">
      <table className="tabla">
        <caption className="oculto-visual">
          Métricas de error de cada modelo en el conjunto de prueba
        </caption>
        <thead>
          <tr>
            <th scope="col">Modelo</th>
            <th scope="col">Familia</th>
            <th scope="col">RMSE</th>
            <th scope="col">MAE</th>
            <th scope="col">MAPE</th>
            <th scope="col">MASE</th>
            <th scope="col">R²</th>
            <th scope="col">vs. ingenuo</th>
            <th scope="col">seg.</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((fila) => {
            const esReferencia = fila.nombre_modelo === "baseline_estacional";
            const gana = fila.es_mejor && !esReferencia;
            return (
              <tr
                key={`${fila.nombre_modelo}-${fila.horizonte_horas}`}
                className={
                  esReferencia
                    ? "tabla__fila--referencia"
                    : gana
                      ? "tabla__fila--gana"
                      : undefined
                }
              >
                <td>
                  <span className="tabla__nombre">
                    {gana && <span className="tabla__marca">▸</span>}
                    {fila.nombre_modelo}
                  </span>
                  <span className="barra-celda">
                    <span
                      className="barra-celda__relleno"
                      style={{
                        transform: `scaleX(${peor ? fila.rmse / peor : 0})`,
                        background: FAMILIAS[fila.familia]?.color ?? COLOR.observado,
                      }}
                    />
                  </span>
                </td>
                <td>{FAMILIAS[fila.familia]?.etiqueta ?? fila.familia}</td>
                <td>{decimales(fila.rmse, 2)}</td>
                <td>{decimales(fila.mae, 2)}</td>
                <td>{decimales(fila.mape, 1)} %</td>
                <td>{decimales(fila.mase, 3)}</td>
                <td>{decimales(fila.r2, 3)}</td>
                <td>
                  {esReferencia
                    ? "referencia"
                    : fila.mejora_sobre_baseline == null
                      ? "—"
                      : `${fila.mejora_sobre_baseline > 0 ? "−" : "+"}${Math.abs(
                          fila.mejora_sobre_baseline
                        ).toFixed(1)} %`}
                </td>
                <td>{decimales(fila.duracion_segundos, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {referencia && (
        <p className="acciones__nota" style={{ padding: "10px 14px 0" }}>
          Última ejecución de cada modelo · {fechaHora(filas[0]?.ejecutado_en)}
        </p>
      )}
    </div>
  );
}

function GraficaRmse({ filas, referencia }) {
  const datos = filas
    .filter((f) => f.nombre_modelo !== "baseline_estacional")
    .map((f) => ({
      nombre: f.nombre_modelo,
      rmse: f.rmse,
      color: FAMILIAS[f.familia]?.color ?? COLOR.observado,
    }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(180, datos.length * 30 + 40)}>
      <BarChart data={datos} layout="vertical" margin={{ top: 6, right: 46, bottom: 4, left: 6 }}>
        <CartesianGrid stroke={COLOR.linea} horizontal={false} />
        <XAxis type="number" tick={EJE} stroke={COLOR.linea} />
        <YAxis
          type="category"
          dataKey="nombre"
          width={132}
          tick={{ ...EJE, fill: COLOR.tinta2 }}
          stroke={COLOR.linea}
        />
        <Tooltip
          cursor={{ fill: COLOR.hundido }}
          content={({ active, payload }) =>
            active && payload?.length ? (
              <div className="pista">
                <div className="pista__momento">{payload[0].payload.nombre}</div>
                <div className="pista__linea">
                  <span className="pista__nombre">RMSE</span>
                  <span className="pista__valor">{decimales(payload[0].value, 2)}</span>
                </div>
              </div>
            ) : null
          }
        />
        <Bar dataKey="rmse" radius={[0, 4, 4, 0]} isAnimationActive={false} barSize={13}>
          {datos.map((d) => (
            <Cell key={d.nombre} fill={d.color} />
          ))}
        </Bar>
        {/* La línea del ingenuo tiene que ser hija directa del gráfico:
            Recharts recorre sus `children` para colocar los elementos en el
            sistema de coordenadas, y un envoltorio propio no lo atraviesa. */}
        {referencia && (
          <ReferenceLine
            x={referencia.rmse}
            stroke={COLOR.tinta2}
            strokeDasharray="4 3"
            label={{
              value: "ingenuo",
              position: "top",
              fontSize: 9,
              fontFamily: "IBM Plex Mono, monospace",
              fill: COLOR.tinta2,
            }}
          />
        )}
      </BarChart>
    </ResponsiveContainer>
  );
}

function GraficaImportancia({ importancia }) {
  const maximo = Math.max(...importancia.map(([, v]) => Math.abs(v))) || 1;

  return (
    <div className="ranking">
      {importancia.map(([nombre, valor]) => (
        <div className="ranking__fila" key={nombre} style={{ cursor: "default" }}>
          <span className="ranking__nombre">
            <span title={nombre}>{nombre}</span>
          </span>
          <span className="ranking__pista">
            <span
              className="ranking__relleno"
              style={{ transform: `scaleX(${Math.abs(valor) / maximo})` }}
            />
          </span>
          <span className="ranking__valor">{decimales(valor, 3)}</span>
        </div>
      ))}
    </div>
  );
}
