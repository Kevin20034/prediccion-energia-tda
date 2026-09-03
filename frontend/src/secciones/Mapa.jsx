import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import * as api from "../api";
import MapaColombia from "../componentes/graficas/MapaColombia";
import { Cargando, Cifra, Conmutador, Panel, Procedencia, Vacio } from "../componentes/ui";
import { energia, fechaHora, marcaTemporal, porcentaje, signo } from "../formato";
import { COLOR, EJE, RAMPA_MAPA } from "../tokens";

const VENTANAS = [
  { valor: 24, etiqueta: "24 h" },
  { valor: 168, etiqueta: "7 días" },
  { valor: 720, etiqueta: "30 días" },
];

const RESOLUCIONES = [
  { valor: "hora", etiqueta: "Horaria" },
  { valor: "dia", etiqueta: "Diaria" },
  { valor: "semana", etiqueta: "Semanal" },
];

export default function Mapa({ puedeOperar, alFallar }) {
  const [geo, setGeo] = useState(null);
  const [horas, setHoras] = useState(24);
  const [mapa, setMapa] = useState(null);
  const [seleccionado, setSeleccionado] = useState(null);
  const [serie, setSerie] = useState(null);
  const [resolucion, setResolucion] = useState("dia");
  const [cargando, setCargando] = useState(true);

  // El GeoJSON se sirve como archivo estático: son 90 KB que no cambian nunca,
  // así que no tiene sentido hacerlos pasar por la API ni por la base de datos.
  useEffect(() => {
    fetch("/colombia-departamentos.json")
      .then((r) => r.json())
      .then(setGeo)
      .catch(() => setGeo(null));
  }, []);

  const cargarMapa = useCallback(async () => {
    setCargando(true);
    try {
      setMapa(await api.mapaDepartamentos(horas));
    } catch (error) {
      alFallar(error);
      setMapa(null);
    } finally {
      setCargando(false);
    }
  }, [horas, alFallar]);

  useEffect(() => {
    cargarMapa();
  }, [cargarMapa]);

  useEffect(() => {
    if (!seleccionado) {
      setSerie(null);
      return;
    }
    api
      .serieDepartamento(seleccionado, resolucion, resolucion === "hora" ? 336 : 180)
      .then(setSerie)
      .catch(() => setSerie(null));
  }, [seleccionado, resolucion]);

  const conectados = useMemo(
    () => (mapa?.departamentos ?? []).filter((d) => d.interconectado),
    [mapa]
  );

  const ranking = useMemo(
    () => [...conectados].sort((a, b) => (b.demanda_24h ?? 0) - (a.demanda_24h ?? 0)),
    [conectados]
  );

  const detalle = seleccionado
    ? (mapa?.departamentos ?? []).find((d) => d.codigo_dane === seleccionado)
    : null;

  const maximo = ranking[0]?.demanda_24h ?? 0;
  const sinDatos = !cargando && !ranking.some((d) => d.demanda_24h);

  const total = energia(mapa?.total_nacional);
  const estimados = conectados.filter((d) => d.estimado).length;

  return (
    <div className="seccion">
      <header className="seccion__cabecera">
        <div>
          <div className="rotulo">Territorio</div>
          <h1 className="seccion__titulo">Demanda por departamento</h1>
          <p className="seccion__nota">
            XM publica la demanda comercial por mercado de comercialización, no por
            departamento. Los mercados que cubren varios departamentos —Caribe Mar,
            Caribe Sol y Bogotá–Cundinamarca— se reparten con pesos documentados, y esos
            departamentos aparecen marcados como <b>estimados</b>.
          </p>
        </div>
        <Conmutador
          etiqueta="Ventana agregada"
          opciones={VENTANAS}
          valor={horas}
          alCambiar={setHoras}
        />
      </header>

      {sinDatos ? (
        <Panel>
          <Vacio
            titulo="Todavía no hay demanda territorial"
            texto={
              puedeOperar
                ? "Ejecuta la ingesta territorial para descargar la demanda por mercado de comercialización y repartirla por departamento."
                : "Un usuario con rol Analista debe ejecutar primero la ingesta territorial."
            }
            accion={
              puedeOperar && (
                <IngestaTerritorial alTerminar={cargarMapa} alFallar={alFallar} />
              )
            }
          />
        </Panel>
      ) : (
        <>
          <div className="rejilla rejilla--cifras" style={{ marginBottom: 16 }}>
            <Cifra
              rotulo={`Demanda nacional · ${VENTANAS.find((v) => v.valor === horas)?.etiqueta}`}
              valor={total.valor}
              unidad={total.unidad}
              naturaleza="medida"
              pie={mapa?.instante ? `hasta ${fechaHora(mapa.instante)}` : null}
            />
            <Cifra
              rotulo="Departamentos con demanda"
              valor={conectados.filter((d) => d.demanda_24h).length}
              naturaleza="medida"
              pie={`${estimados} con valor estimado por reparto`}
            />
            <Cifra
              rotulo="Mayor consumo"
              valor={ranking[0]?.departamento ?? "—"}
              naturaleza="medida"
              pie={
                ranking[0] ? `${porcentaje(ranking[0].participacion)} del país` : null
              }
            />
            <Cifra
              rotulo="Fuera del SIN"
              valor={(mapa?.departamentos ?? []).filter((d) => !d.interconectado).length}
              naturaleza="neutra"
              pie="Zonas No Interconectadas, abastecidas con generación local"
            />
          </div>

          <div className="rejilla rejilla--mapa">
            <Panel
              rotulo="Mapa coroplético"
              titulo="Demanda agregada por departamento"
              ajustado
              pie="Los cortes de color son por cuantiles, no lineales: la demanda está tan concentrada que una escala lineal dejaría casi todo el país del mismo tono."
            >
              <Escala departamentos={conectados} />
              {cargando ? (
                <Cargando texto="consultando demanda" />
              ) : (
                <MapaColombia
                  geo={geo}
                  departamentos={mapa?.departamentos ?? []}
                  seleccionado={seleccionado}
                  alSeleccionar={setSeleccionado}
                />
              )}
            </Panel>

            <div className="pila">
              <Panel rotulo="Detalle" titulo={detalle?.departamento ?? "Elige un departamento"}>
                {detalle ? (
                  <DetalleDepartamento
                    departamento={detalle}
                    serie={serie}
                    resolucion={resolucion}
                    alCambiarResolucion={setResolucion}
                  />
                ) : (
                  <p className="seccion__nota">
                    Pulsa cualquier departamento del mapa para ver su serie histórica, su
                    hora punta y de qué mercados de XM procede su dato.
                  </p>
                )}
              </Panel>

              <Panel rotulo="Ranking" titulo="Por demanda agregada">
                <div className="ranking">
                  {ranking.slice(0, 14).map((d) => (
                    <button
                      key={d.codigo_dane}
                      type="button"
                      className="ranking__fila"
                      aria-pressed={seleccionado === d.codigo_dane}
                      onClick={() => setSeleccionado(d.codigo_dane)}
                    >
                      <span className="ranking__nombre">
                        <span>{d.departamento}</span>
                        {d.estimado && (
                          <span className="insignia insignia--estimada">est.</span>
                        )}
                      </span>
                      <span className="ranking__pista">
                        <span
                          className="ranking__relleno"
                          style={{
                            transform: `scaleX(${maximo ? (d.demanda_24h ?? 0) / maximo : 0})`,
                          }}
                        />
                      </span>
                      <span className="ranking__valor">
                        {energia(d.demanda_24h).valor} {energia(d.demanda_24h).unidad}
                      </span>
                    </button>
                  ))}
                </div>
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function Escala({ departamentos }) {
  const valores = departamentos
    .map((d) => d.demanda_24h)
    .filter((v) => v != null && v > 0)
    .sort((a, b) => a - b);

  const minimo = energia(valores[0]);
  const maximo = energia(valores.at(-1));

  return (
    <div className="escala">
      <span className="escala__extremo">
        {minimo.valor} {minimo.unidad}
      </span>
      <span className="escala__tramos" aria-hidden="true">
        {RAMPA_MAPA.map((color) => (
          <i key={color} className="escala__tramo" style={{ background: color }} />
        ))}
      </span>
      <span className="escala__extremo">
        {maximo.valor} {maximo.unidad}
      </span>
      <span className="escala__extremo" style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <i
          className="leyenda__cuadro"
          style={{ background: "var(--mapa-nulo)" }}
          aria-hidden="true"
        />
        fuera del SIN
      </span>
    </div>
  );
}

function DetalleDepartamento({ departamento, serie, resolucion, alCambiarResolucion }) {
  const total = energia(departamento.demanda_24h);
  const media = energia(departamento.demanda_media_horaria_7d);

  const datos = (serie?.puntos ?? []).map((p) => ({
    t: new Date(p.fecha_hora).getTime(),
    valor: p.demanda_kwh / 1e6,
  }));

  return (
    <>
      <div className="fila" style={{ marginBottom: 12 }}>
        <Procedencia
          estimado={departamento.estimado}
          detalle={
            departamento.mercados
              ? `Mercados de origen: ${departamento.mercados.replaceAll("+", " + ")}`
              : undefined
          }
        />
        <span className="insignia">DANE {departamento.codigo_dane}</span>
        <span className="hueco" />
        <Conmutador
          etiqueta="Resolución de la serie"
          opciones={RESOLUCIONES}
          valor={resolucion}
          alCambiar={alCambiarResolucion}
        />
      </div>

      <div className="lectura">
        <span className="rotulo">Demanda en la ventana</span>
        <span className="lectura__valor">
          {total.valor} {total.unidad}
        </span>
      </div>
      <div className="lectura">
        <span className="rotulo">Media horaria (7 días)</span>
        <span className="lectura__valor">
          {media.valor} {media.unidad}
        </span>
      </div>
      <div className="lectura">
        <span className="rotulo">Variación</span>
        <span className="lectura__valor">{signo(departamento.variacion_24h)}</span>
      </div>
      <div className="lectura">
        <span className="rotulo">Hora punta</span>
        <span className="lectura__valor">
          {departamento.pico_horario == null
            ? "—"
            : `${String(departamento.pico_horario).padStart(2, "0")}:00`}
        </span>
      </div>
      <div className="lectura">
        <span className="rotulo">Participación nacional</span>
        <span className="lectura__valor">{porcentaje(departamento.participacion)}</span>
      </div>

      {datos.length > 1 && (
        <div style={{ marginTop: 14 }}>
          <div className="rotulo" style={{ marginBottom: 6 }}>
            Serie · GWh
          </div>
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={datos} margin={{ top: 4, right: 6, bottom: 0, left: 0 }}>
              <CartesianGrid stroke={COLOR.linea} vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={(t) => marcaTemporal(t, resolucion)}
                tick={{ ...EJE, fontSize: 9 }}
                stroke={COLOR.linea}
                minTickGap={44}
              />
              <YAxis width={40} tick={{ ...EJE, fontSize: 9 }} stroke={COLOR.linea} />
              <Tooltip
                cursor={{ fill: COLOR.hundido }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <div className="pista">
                      <div className="pista__momento">
                        {marcaTemporal(label, resolucion)}
                      </div>
                      <div className="pista__linea">
                        <span className="pista__nombre">demanda</span>
                        <span className="pista__valor">
                          {payload[0].value.toFixed(2)} GWh
                        </span>
                      </div>
                    </div>
                  ) : null
                }
              />
              <Bar
                dataKey="valor"
                fill={COLOR.observado}
                radius={[2, 2, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {departamento.mercados && (
        <p className="acciones__nota">
          Origen en XM: {departamento.mercados.replaceAll("+", " + ")}
        </p>
      )}
    </>
  );
}

function IngestaTerritorial({ alTerminar, alFallar }) {
  const [ocupado, setOcupado] = useState(false);

  async function ejecutar() {
    setOcupado(true);
    try {
      const desde = new Date();
      desde.setDate(desde.getDate() - 90);
      await api.ingerirDepartamentos(desde.toISOString().slice(0, 10), null);
      await alTerminar();
    } catch (error) {
      alFallar(error);
    } finally {
      setOcupado(false);
    }
  }

  return (
    <button className="boton boton--solido" onClick={ejecutar} disabled={ocupado}>
      {ocupado ? "Descargando de XM…" : "Descargar últimos 90 días"}
    </button>
  );
}
