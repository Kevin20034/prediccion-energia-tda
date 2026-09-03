import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import * as api from "../api";
import GraficaSeries from "../componentes/graficas/GraficaSeries";
import { Cargando, Cifra, Conmutador, Panel } from "../componentes/ui";
import { decimales, energia, fechaHora, mesAnio } from "../formato";
import { COLOR, EJE } from "../tokens";

const RESOLUCIONES = [
  { valor: "hora", etiqueta: "Horaria" },
  { valor: "dia", etiqueta: "Diaria" },
  { valor: "semana", etiqueta: "Semanal" },
  { valor: "mes", etiqueta: "Mensual" },
];

const MAX_SERIES = 6;
const SELECCION_INICIAL = ["precio_bolsa", "volumen_util_embalse"];

export default function Datos({ puedeOperar, alFallar, alAvisar }) {
  const [catalogo, setCatalogo] = useState([]);
  const [seleccion, setSeleccion] = useState(SELECCION_INICIAL);
  const [resolucion, setResolucion] = useState("dia");
  const [respuesta, setRespuesta] = useState(null);
  const [cargando, setCargando] = useState(true);
  const [resumen, setResumen] = useState(null);
  const [upme, setUpme] = useState(null);
  const [ingiriendo, setIngiriendo] = useState(false);

  useEffect(() => {
    api
      .catalogoVariables()
      .then((r) => setCatalogo(r.grupos ?? []))
      .catch(() => setCatalogo([]));
    api.resumenDatos().then(setResumen).catch(() => setResumen(null));
    api.escenariosUpme().then(setUpme).catch(() => setUpme(null));
  }, []);

  const cargarSeries = useCallback(async () => {
    if (!seleccion.length) {
      setRespuesta(null);
      setCargando(false);
      return;
    }
    setCargando(true);
    try {
      setRespuesta(
        await api.series({
          variables: seleccion,
          resolucion,
          limite: resolucion === "hora" ? 3000 : 1200,
        })
      );
    } catch (error) {
      alFallar(error);
    } finally {
      setCargando(false);
    }
  }, [seleccion, resolucion, alFallar]);

  useEffect(() => {
    cargarSeries();
  }, [cargarSeries]);

  function alternar(nombre) {
    setSeleccion((actual) => {
      if (actual.includes(nombre)) return actual.filter((v) => v !== nombre);
      if (actual.length >= MAX_SERIES) return actual;
      return [...actual, nombre];
    });
  }

  async function ingerir() {
    setIngiriendo(true);
    try {
      const desde = new Date();
      desde.setDate(desde.getDate() - 30);
      const r = await api.ingerir(desde.toISOString().slice(0, 10), null);
      alAvisar({
        tipo: "ok",
        texto: `${r.registros_descargados} registros procesados (${r.registros_insertados} nuevos) con ${r.variables_pobladas.length} variables.`,
      });
      const nuevo = await api.resumenDatos();
      setResumen(nuevo);
      await cargarSeries();
    } catch (error) {
      alFallar(error);
    } finally {
      setIngiriendo(false);
    }
  }

  const media = energia(resumen?.demanda_media);
  const cobertura = useMemo(() => {
    if (!resumen?.variables_totales) return null;
    return (resumen.variables_con_datos / resumen.variables_totales) * 100;
  }, [resumen]);

  return (
    <div className="seccion">
      <header className="seccion__cabecera">
        <div>
          <div className="rotulo">Fuente</div>
          <h1 className="seccion__titulo">Datos del sistema</h1>
          <p className="seccion__nota">
            Series horarias publicadas por XM, cruzadas con reanálisis climático de
            Open-Meteo y el índice ONI de la NOAA. Elige hasta {MAX_SERIES} variables:
            las de unidades distintas se dibujan en gráficas separadas, nunca sobre dos
            ejes en el mismo marco.
          </p>
        </div>
        <div className="fila">
          <Conmutador
            etiqueta="Resolución"
            opciones={RESOLUCIONES}
            valor={resolucion}
            alCambiar={setResolucion}
          />
          {puedeOperar && (
            <button
              className="boton boton--solido"
              onClick={ingerir}
              disabled={ingiriendo}
              style={{ width: "auto" }}
            >
              {ingiriendo ? "Descargando de XM…" : "Actualizar últimos 30 días"}
            </button>
          )}
        </div>
      </header>

      <div className="rejilla rejilla--cifras" style={{ marginBottom: 16 }}>
        <Cifra
          rotulo="Registros horarios"
          valor={decimales(resumen?.total_registros, 0)}
          naturaleza="medida"
          pie={
            resumen?.fecha_minima
              ? `${fechaHora(resumen.fecha_minima)} → ${fechaHora(resumen.fecha_maxima)}`
              : null
          }
        />
        <Cifra
          rotulo="Precio medio"
          valor={decimales(resumen?.precio_medio, 1)}
          unidad="COP/kWh"
          naturaleza="medida"
          pie={`mín ${decimales(resumen?.precio_minimo, 0)} · máx ${decimales(
            resumen?.precio_maximo,
            0
          )}`}
        />
        <Cifra
          rotulo="Demanda media horaria"
          valor={media.valor}
          unidad={media.unidad}
          naturaleza="medida"
        />
        <Cifra
          rotulo="Variables con datos"
          valor={`${resumen?.variables_con_datos ?? 0}/${resumen?.variables_totales ?? 0}`}
          naturaleza="medida"
          pie={cobertura == null ? null : `${cobertura.toFixed(0)} % del catálogo`}
        />
      </div>

      <Panel
        rotulo={`${seleccion.length} de ${MAX_SERIES} series`}
        titulo="Explorador de series"
        ajustado
      >
        <div style={{ padding: "4px 10px 12px" }}>
          <SelectorVariables
            catalogo={catalogo}
            seleccion={seleccion}
            alAlternar={alternar}
            maximo={MAX_SERIES}
          />
        </div>
        <GraficaSeries respuesta={respuesta} resolucion={resolucion} cargando={cargando} />
      </Panel>

      {upme?.escenarios?.length > 0 && (
        <div className="separado">
          <Panel
            rotulo="Contraste externo"
            titulo="Demanda observada frente a la proyección de la UPME"
            ajustado
            pie="La UPME hace planeación de largo plazo, no pronóstico operativo, así que esto no es una comparación de errores: es una comprobación de cordura. Que la demanda real vaya dentro de la banda alto–bajo indica que el sistema evoluciona como estaba previsto."
          >
            <GraficaUpme escenarios={upme.escenarios} />
          </Panel>
        </div>
      )}
    </div>
  );
}

function SelectorVariables({ catalogo, seleccion, alAlternar, maximo }) {
  if (!catalogo.length) return <Cargando texto="cargando catálogo" />;

  return (
    <div className="pila">
      {catalogo.map((grupo) => {
        const disponibles = grupo.variables.filter((v) => v.disponible);
        if (!disponibles.length) return null;
        return (
          <div key={grupo.clave}>
            <div className="rotulo" style={{ marginBottom: 6 }}>
              {grupo.titulo}
            </div>
            <div className="selector-variables">
              {disponibles.map((variable) => {
                const activa = seleccion.includes(variable.nombre);
                return (
                  <button
                    key={variable.nombre}
                    type="button"
                    className="pildora"
                    aria-pressed={activa}
                    disabled={!activa && seleccion.length >= maximo}
                    onClick={() => alAlternar(variable.nombre)}
                    title={`${variable.etiqueta} · ${variable.unidad}`}
                  >
                    {variable.etiqueta}
                  </button>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Banda de escenarios de la UPME con la demanda observada encima.
 *
 * La banda se dibuja como dos áreas apiladas —base invisible y espesor
 * pintado— por el mismo motivo que en la gráfica de pronóstico: es la forma
 * fiable de rellenar entre dos series en Recharts.
 */
function GraficaUpme({ escenarios }) {
  const datos = escenarios.map((e) => ({
    t: new Date(e.mes).getTime(),
    base: e.escenario_bajo == null ? null : e.escenario_bajo / 1e9,
    espesor:
      e.escenario_bajo == null || e.escenario_alto == null
        ? null
        : (e.escenario_alto - e.escenario_bajo) / 1e9,
    medio: e.escenario_medio == null ? null : e.escenario_medio / 1e9,
    observado: e.observado == null ? null : e.observado / 1e9,
  }));

  return (
    <div className="grafica">
      <div className="leyenda">
        <span className="leyenda__clave" style={{ color: COLOR.observado }}>
          <i className="leyenda__trazo" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>demanda observada</span>
        </span>
        <span className="leyenda__clave" style={{ color: COLOR.pronostico }}>
          <i className="leyenda__trazo leyenda__trazo--punteado" aria-hidden="true" />
          <span style={{ color: COLOR.tinta2 }}>escenario medio UPME</span>
        </span>
        <span className="leyenda__clave">
          <i
            className="leyenda__banda"
            style={{ background: COLOR.pronostico }}
            aria-hidden="true"
          />
          banda alto–bajo
        </span>
        <span className="hueco" />
        <span className="leyenda__clave">TWh / mes</span>
      </div>

      <ResponsiveContainer width="100%" height={250}>
        <ComposedChart data={datos} margin={{ top: 8, right: 24, bottom: 4, left: 6 }}>
          <CartesianGrid stroke={COLOR.linea} vertical={false} />
          <XAxis
            dataKey="t"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={mesAnio}
            tick={EJE}
            stroke={COLOR.linea}
            minTickGap={44}
          />
          <YAxis
            width={52}
            tick={EJE}
            stroke={COLOR.linea}
            tickFormatter={(v) => decimales(v, 1)}
            domain={["auto", "auto"]}
          />
          <Tooltip
            cursor={{ stroke: COLOR.lineaFuerte, strokeDasharray: "3 3" }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null;
              const punto = payload[0].payload;
              return (
                <div className="pista">
                  <div className="pista__momento">{mesAnio(label)}</div>
                  {punto.observado != null && (
                    <div className="pista__linea">
                      <span className="pista__nombre">
                        <i
                          className="pista__punto"
                          style={{ background: COLOR.observado }}
                          aria-hidden="true"
                        />
                        observado
                      </span>
                      <span className="pista__valor">{decimales(punto.observado, 2)}</span>
                    </div>
                  )}
                  <div className="pista__linea">
                    <span className="pista__nombre">
                      <i
                        className="pista__punto"
                        style={{ background: COLOR.pronostico }}
                        aria-hidden="true"
                      />
                      UPME medio
                    </span>
                    <span className="pista__valor">{decimales(punto.medio, 2)}</span>
                  </div>
                  {punto.base != null && (
                    <div className="pista__nota">
                      banda {decimales(punto.base, 2)} – {decimales(punto.base + punto.espesor, 2)} TWh
                    </div>
                  )}
                </div>
              );
            }}
          />
          <Area
            dataKey="base"
            stackId="upme"
            stroke="none"
            fill="none"
            isAnimationActive={false}
            activeDot={false}
          />
          <Area
            dataKey="espesor"
            stackId="upme"
            stroke="none"
            fill={COLOR.pronostico}
            fillOpacity={0.14}
            isAnimationActive={false}
            activeDot={false}
          />
          <Line
            type="monotone"
            dataKey="medio"
            stroke={COLOR.pronostico}
            strokeWidth={1.8}
            strokeDasharray="5 4"
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="observado"
            stroke={COLOR.observado}
            strokeWidth={2.2}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
