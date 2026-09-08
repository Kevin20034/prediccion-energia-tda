/**
 * Fenómeno del Niño: cómo está el país y qué le hace al mercado.
 *
 * La sección se lee de arriba abajo y responde tres preguntas en ese orden:
 * en qué fase estamos, dónde se está notando, y qué efecto tiene realmente.
 *
 * La tercera es la que importa, y su respuesta contradice la intuición. Lo
 * esperable sería "más calor, más consumo, más precio". Lo que dicen los datos
 * del proyecto es que la demanda apenas se mueve entre fases y el precio se
 * multiplica por 2,4: el fenómeno no golpea cuánta energía se usa, sino cuánto
 * cuesta producirla, porque sin agua entra la térmica. La sección enseña las dos
 * cifras juntas para que esa lectura sea la evidente.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import * as api from "../api";
import { Contador, Revelar } from "../componentes/animacion";
import MapaColombia from "../componentes/graficas/MapaColombia";
import { Cargando, Conmutador, Panel, Vacio } from "../componentes/ui";
import { decimales, energia, fechaHora } from "../formato";
import { COLOR, RAMPA_ANOMALIA } from "../tokens";

const VENTANAS = [
  { valor: 24, etiqueta: "24 h" },
  { valor: 168, etiqueta: "7 días" },
  { valor: 720, etiqueta: "30 días" },
];

const NOMBRE_FASE = {
  EL_NINO: "El Niño",
  LA_NINA: "La Niña",
  NEUTRO: "Neutro",
};

/** Qué es cada fase, en una línea, para quien no siga el tema. */
const QUE_ES = {
  EL_NINO: "El Pacífico está más caliente de lo normal. En Colombia se traduce en menos lluvia y embalses más bajos.",
  LA_NINA: "El Pacífico está más frío de lo normal. Suele traer más lluvia y embalses más llenos.",
  NEUTRO: "El Pacífico está en su rango normal: ni El Niño ni La Niña.",
};

export default function FenomenoNino({ alFallar }) {
  const [ventana, setVentana] = useState(24);
  const [estado, setEstado] = useState(null);
  const [mapa, setMapa] = useState(null);
  const [efecto, setEfecto] = useState(null);
  const [geo, setGeo] = useState(null);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    fetch("/colombia-departamentos.json")
      .then((r) => r.json())
      .then(setGeo)
      .catch(() => setGeo(null));
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    try {
      const [e, m, f] = await Promise.all([
        api.ninoEstado(),
        api.ninoMapa(ventana),
        api.ninoEfecto(),
      ]);
      setEstado(e);
      setMapa(m);
      setEfecto(f);
    } catch (error) {
      alFallar(error);
    } finally {
      setCargando(false);
    }
  }, [ventana, alFallar]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  if (cargando && !mapa) return <Cargando texto="leyendo el estado del Pacífico" />;

  return (
    <div className="seccion">
      <header className="seccion__cabecera">
        <div>
          <div className="rotulo">Clima y mercado</div>
          <h1 className="seccion__titulo">Fenómeno del Niño</h1>
          <p className="seccion__nota">
            El Niño y La Niña son el calentamiento y el enfriamiento del Pacífico
            ecuatorial. En un país que genera la mayor parte de su electricidad
            con agua, deciden cuánta hay en los embalses — y con ello, el precio.
          </p>
        </div>
        <Conmutador
          etiqueta="Ventana"
          opciones={VENTANAS}
          valor={ventana}
          alCambiar={setVentana}
        />
      </header>

      <Estado estado={estado} />

      <div className="rejilla rejilla--mapa separado">
        <Panel
          rotulo={`Temperatura · últimas ${VENTANAS.find((v) => v.valor === ventana)?.etiqueta}`}
          titulo="Qué tan lejos está cada departamento de su normal"
          ajustado
          pie="La anomalía compara la temperatura de cada departamento con su propia media histórica para este mes del año. Un departamento no sale caliente por ser caluroso, sino por estarlo más de lo que le toca."
        >
          {geo && mapa?.departamentos?.length ? (
            <>
              <MapaColombia
                geo={geo}
                departamentos={mapa.departamentos}
                campo="anomalia"
                rampa={RAMPA_ANOMALIA}
                escala="divergente"
                extremo={mapa.anomalia_maxima}
                etiquetaMapa="Mapa de la anomalía de temperatura por departamento de Colombia"
                detalle={(d) => <DetalleDepartamento dato={d} />}
              />
              <LeyendaAnomalia extremo={mapa.anomalia_maxima} />
            </>
          ) : (
            <Vacio
              titulo="Sin datos de clima por departamento"
              texto="Ejecuta: python -m scripts.ingestar_clima_departamentos --inicio 2023-01-01"
            />
          )}
        </Panel>

        <SerieOni serie={estado?.serie ?? []} />
      </div>

      {/* El efecto va a ancho completo y debajo, no en la columna estrecha: es
          la conclusión de la sección —lo que el fenómeno le hace al mercado— y
          en el lateral la tabla no cabía sin cortar la última columna. */}
      <div className="separado">
        <Efecto efecto={efecto} />
      </div>
    </div>
  );
}

/** Titular: en qué fase estamos y qué significa. */
function Estado({ estado }) {
  if (!estado?.fase) {
    return (
      <Panel rotulo="Estado" titulo="Sin índice ONI">
        <Vacio
          titulo="Aún no hay datos del Pacífico"
          texto="El índice ONI llega con la ingesta de clima."
        />
      </Panel>
    );
  }

  const nombre = NOMBRE_FASE[estado.fase] ?? estado.fase;
  const esNeutro = estado.fase === "NEUTRO";

  return (
    <Revelar>
      <div className={`nino-estado nino-estado--${estado.fase.toLowerCase()}`}>
        <div>
          <div className="rotulo">Ahora mismo</div>
          <h2 className="nino-estado__titular">
            {esNeutro ? (
              <>El Pacífico está en su rango <em>normal</em></>
            ) : (
              <>
                Estamos en <em>{nombre}</em>
                {estado.intensidad ? ` ${estado.intensidad}` : ""}
              </>
            )}
          </h2>
          <p className="nino-estado__texto">{QUE_ES[estado.fase]}</p>
        </div>
        <div className="nino-estado__cifra">
          <div className="rotulo">Índice ONI</div>
          <div className="cifra__valor">
            {/* El ONI se mueve en décimas: redondear a entero, que es lo que
                hace `Contador` por defecto, borraría la señal entera. */}
            <Contador valor={estado.oni} formato={(v) => v.toFixed(2)} />
          </div>
          <div className="nino-estado__pie">
            {estado.actualizado_en ? fechaHora(estado.actualizado_en) : ""}
          </div>
        </div>
      </div>
    </Revelar>
  );
}

/**
 * El efecto medido. Es el bloque que responde a la pregunta de la sección, y
 * por eso muestra precio y demanda juntos: la demanda casi plana es la mitad
 * del hallazgo, no un dato de relleno.
 */
function Efecto({ efecto }) {
  const fases = efecto?.fases ?? [];

  const contraste = useMemo(() => {
    const nino = fases.find((f) => f.fase === "EL_NINO");
    const nina = fases.find((f) => f.fase === "LA_NINA");
    if (!nino?.precio || !nina?.precio) return null;
    // `decimales` y no `toFixed`: en español el separador es la coma, y un
    // "2.5" suelto entre cifras con coma se lee como un error de la aplicación.
    return decimales(nino.precio / nina.precio, 1);
  }, [fases]);

  if (!fases.length) {
    return (
      <Panel rotulo="Efecto" titulo="Qué le hace al mercado">
        <Vacio titulo="Sin histórico suficiente" texto="Hace falta ingerir datos con índice ONI." />
      </Panel>
    );
  }

  return (
    <Panel
      rotulo="Sobre el histórico completo"
      titulo="Qué le hace al mercado"
      pie="Medias horarias de todo el histórico, agrupadas por fase del fenómeno."
    >
      {contraste && (
        <p className="nino-hallazgo">
          Con El Niño la energía cuesta <b>{contraste} veces</b> lo que cuesta con
          La Niña. El consumo, en cambio, apenas se mueve: el fenómeno no cambia
          cuánta energía usa el país, cambia <b>cuánto cuesta producirla</b>,
          porque sin agua en los embalses entra la generación térmica.
        </p>
      )}

      <div className="envoltura-tabla">
        <table className="tabla">
          <caption className="oculto-visual">
            Precio y demanda medios bajo cada fase del fenómeno
          </caption>
          <thead>
            <tr>
              <th scope="col">Fase</th>
              <th scope="col">Precio</th>
              <th scope="col">vs. normal</th>
              <th scope="col">Demanda</th>
              <th scope="col">vs. normal</th>
            </tr>
          </thead>
          <tbody>
            {fases.map((f) => (
              <tr key={f.fase}>
                {/* La muestra va bajo el nombre y no en columna propia: con seis
                    columnas la tabla se desbordaba y la última quedaba cortada,
                    que es la peor manera de mostrar una advertencia. */}
                <td>
                  <span className="tabla__nombre">{NOMBRE_FASE[f.fase] ?? f.fase}</span>
                  <span className={f.evidencia === "debil" ? "marca-debil" : "marca-solida"}>
                    {Math.round(f.horas / 24)} días
                  </span>
                </td>
                <td>{decimales(f.precio, 1)}</td>
                <td>
                  <Variacion valor={f.variacion_precio} />
                </td>
                <td>{energia(f.demanda).valor} {energia(f.demanda).unidad}</td>
                <td>
                  <Variacion valor={f.variacion_demanda} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {fases.some((f) => f.evidencia === "debil") && (
        <p className="acciones__nota">
          Una fase de menos de {Math.round(efecto.horas_para_evidencia_solida / 24)} días
          no cubre un año entero, así que su media es también la de los meses
          concretos en que ocurrió. Va marcada por eso.
        </p>
      )}
    </Panel>
  );
}

function Variacion({ valor }) {
  if (valor == null) return <span style={{ color: COLOR.tinta3 }}>referencia</span>;
  const sube = valor > 0;
  return (
    <span style={{ color: sube ? COLOR.pronosticoClaro : COLOR.observadoClaro }}>
      {sube ? "▲" : "▼"} {decimales(Math.abs(valor), 1)} %
    </span>
  );
}

/** Evolución del ONI, para ver de dónde viene la fase actual. */
function SerieOni({ serie }) {
  if (!serie.length) return null;

  const tope = Math.max(1, ...serie.map((p) => Math.abs(p.oni)));

  return (
    <Panel
      rotulo="Últimos 3 años"
      titulo="Evolución del índice"
      pie="Por encima de +0,5 es El Niño; por debajo de −0,5, La Niña. Entre medias, neutro. Es el criterio de la NOAA."
    >
      <div className="oni">
        {serie.map((p) => {
          const alto = (Math.abs(p.oni) / tope) * 50;
          const calido = p.oni > 0;
          return (
            <div className="oni__mes" key={p.mes} title={`${p.mes}: ${p.oni}`}>
              <div className="oni__mitad oni__mitad--arriba">
                {calido && (
                  <span
                    className="oni__barra"
                    style={{ height: `${alto}%`, background: RAMPA_ANOMALIA[5] }}
                  />
                )}
              </div>
              <span className="oni__cero" />
              <div className="oni__mitad oni__mitad--abajo">
                {!calido && (
                  <span
                    className="oni__barra"
                    style={{ height: `${alto}%`, background: RAMPA_ANOMALIA[1] }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="oni__ejes">
        <span>{serie[0]?.mes}</span>
        <span>{serie[serie.length - 1]?.mes}</span>
      </div>
    </Panel>
  );
}

function DetalleDepartamento({ dato }) {
  if (!dato) return null;
  const sinDato = dato.anomalia == null;

  return (
    <>
      <div className="pista__linea">
        <span className="pista__nombre">frente a su normal</span>
        <span className="pista__valor">
          {sinDato ? "sin dato" : `${dato.anomalia > 0 ? "+" : ""}${decimales(dato.anomalia, 1)} °C`}
        </span>
      </div>
      <div className="pista__linea">
        <span className="pista__nombre">temperatura</span>
        <span className="pista__valor">{decimales(dato.temperatura, 1)} °C</span>
      </div>
      <div className="pista__linea">
        <span className="pista__nombre">su normal de este mes</span>
        <span className="pista__valor">{decimales(dato.media_mensual, 1)} °C</span>
      </div>
      {dato.demanda_kwh != null && (
        <div className="pista__nota">
          {energia(dato.demanda_kwh).valor} {energia(dato.demanda_kwh).unidad} consumidos
        </div>
      )}
    </>
  );
}

/** Leyenda simétrica: el cero en el centro y el mismo alcance a ambos lados. */
function LeyendaAnomalia({ extremo }) {
  if (!extremo) return null;

  return (
    <div className="leyenda-anomalia">
      <span className="leyenda-anomalia__extremo">−{decimales(extremo, 1)} °C</span>
      <div className="leyenda-anomalia__barra">
        {RAMPA_ANOMALIA.map((color, i) => (
          <span key={color} style={{ background: color }} title={i === 3 ? "en su normal" : ""} />
        ))}
      </div>
      <span className="leyenda-anomalia__extremo">+{decimales(extremo, 1)} °C</span>
      <span className="leyenda-anomalia__nota">más frío · en su normal · más cálido</span>
    </div>
  );
}
