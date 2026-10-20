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
import { decimales, fechaHora } from "../formato";
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

  const nino = fases.find((f) => f.fase === "EL_NINO");
  const nina = fases.find((f) => f.fase === "LA_NINA");
  const neutro = fases.find((f) => f.fase === "NEUTRO");

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
      titulo="Qué le hace a la generación y al consumo"
      acciones={<Confiabilidad fases={fases} />}
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

      <div className="nino-causal-grid">
        <div className="nino-causal-card nino-causal-card--hidraulica">
          <span className="nino-causal-card__etiqueta">Hidráulica</span>
          <strong>
            {nino?.variacion_generacion_hidraulica != null
              ? `${Math.abs(nino.variacion_generacion_hidraulica).toFixed(1)}%`
              : "—"}
          </strong>
          <small>
            {nino?.variacion_generacion_hidraulica != null
              ? `baja con El Niño y se recupera con La Niña.`
              : "Sin historial suficiente para comparar."}
          </small>
        </div>
        <div className="nino-causal-card nino-causal-card--termica">
          <span className="nino-causal-card__etiqueta">Térmica</span>
          <strong>
            {nino?.variacion_generacion_termica != null
              ? `${Math.abs(nino.variacion_generacion_termica).toFixed(1)}%`
              : "—"}
          </strong>
          <small>
            {nino?.variacion_generacion_termica != null
              ? `sube cuando la hidráulica cae y encarece el sistema.`
              : "Sin historial suficiente para comparar."}
          </small>
        </div>
        <div className="nino-causal-card nino-causal-card--demanda">
          <span className="nino-causal-card__etiqueta">Consumo</span>
          <strong>
            {nino?.variacion_demanda != null ? `${Math.abs(nino.variacion_demanda).toFixed(1)}%` : "—"}
          </strong>
          <small>
            {nino?.variacion_demanda != null
              ? `se mantiene casi estable; el cambio real está en la mezcla de energía.`
              : "Sin historial suficiente para comparar."}
          </small>
        </div>
      </div>

      <p className="nino-explicacion">
        La clave es la <b>mezcla energética</b>: <b>El Niño</b> reduce la lluvia y
        baja los embalses, así que la <b>hidráulica cae</b> y el sistema debe
        compensar con <b>generación térmica</b>, que es más cara. <b>La Niña</b>{" "}
        hace lo contrario: vuelve a haber más agua, la hidroelectricidad crece y
        el costo del sistema baja. El <b>consumo</b> del país casi no cambia; lo
        que sí se altera es la forma de producir energía y, por eso, el precio.
      </p>

    </Panel>
  );
}

function Confiabilidad({ fases }) {
  const evidenciaDebil = fases.some((fase) => fase.evidencia === "debil");
  const nivel = evidenciaDebil ? "Media" : "Alta";

  return (
    <div className={`nino-confiabilidad nino-confiabilidad--${nivel.toLowerCase()}`}>
      <div className="nino-confiabilidad__cabecera">
        <span className="nino-confiabilidad__punto" aria-hidden="true" />
        <span>Confiabilidad de datos</span>
        <strong>{nivel}</strong>
      </div>
      <div className="nino-confiabilidad__fuente">
        Fuente: XM · ONI NOAA · Open-Meteo
      </div>
      <div className="nino-confiabilidad__nota">
        {evidenciaDebil
          ? "Una fase tiene menos de un año de observaciones."
          : "Fases con al menos un año de observaciones."}
      </div>
    </div>
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
