import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import * as api from "../api";
import { Contador, Revelar } from "../componentes/animacion";
import GraficaPronostico from "../componentes/graficas/GraficaPronostico";
import Herramientas from "../componentes/graficas/Herramientas";
import LogoTdeA from "../componentes/LogoTdeA";
import PulsoCarga from "../componentes/PulsoCarga";
import { Cargando, Panel, Vacio } from "../componentes/ui";
import { decimales, energia, fechaHora } from "../formato";
import { TECNOLOGIAS } from "../tokens";

/**
 * Vista de usuario.
 *
 * Una sola página que se lee de arriba abajo y responde, en ese orden, a las
 * tres preguntas de alguien que no trabaja en el sector:
 *
 *   1. ¿Cómo está ahora?      → portada con el titular y la cifra del momento
 *   2. ¿Hacia dónde va?       → tres horizontes y la gráfica del elegido
 *   3. ¿Por qué?              → embalses, mezcla de generación y territorio
 *
 * Cada bloque lleva una nota que explica qué se está mirando. En el tablero
 * técnico esa explicación sobra; aquí es la mitad del trabajo.
 */

const OBJETIVOS = [
  { valor: "precio_bolsa", etiqueta: "Precio", pregunta: "¿Cuánto cuesta la energía?" },
  { valor: "demanda_real", etiqueta: "Demanda", pregunta: "¿Cuánta energía consume el país?" },
];

const FLECHAS = { sube: "▲", baja: "▲", estable: "▶" };

/** Columnas del CSV que se descarga junto a la gráfica. */
const COLUMNAS_CSV = [
  { titulo: "fecha", valor: (f) => f.fecha },
  { titulo: "tipo", valor: (f) => f.tipo },
  { titulo: "valor", valor: (f) => f.valor },
  { titulo: "minimo", valor: (f) => f.minimo ?? "" },
  { titulo: "maximo", valor: (f) => f.maximo ?? "" },
];

export default function Inicio({ alFallar, alAvisar, alIrAlMapa }) {
  const [objetivo, setObjetivo] = useState("precio_bolsa");
  const [horizonte, setHorizonte] = useState(24);
  const [forma, setForma] = useState("linea");
  const contenedorGrafica = useRef(null);

  const [panorama, setPanorama] = useState(null);
  const [pronostico, setPronostico] = useState(null);
  const [cargandoPanorama, setCargandoPanorama] = useState(true);
  const [cargandoGrafica, setCargandoGrafica] = useState(true);

  const cargarPanorama = useCallback(async () => {
    setCargandoPanorama(true);
    try {
      setPanorama(await api.panorama(objetivo));
    } catch (error) {
      alFallar(error);
      setPanorama(null);
    } finally {
      setCargandoPanorama(false);
    }
  }, [objetivo, alFallar]);

  useEffect(() => {
    cargarPanorama();
  }, [cargarPanorama]);

  // La gráfica se pide aparte del panorama y a propósito: es lo único pesado de
  // la pantalla, y así los números y el titular aparecen de inmediato en vez de
  // esperar a que el modelo termine.
  //
  // Esa llamada además **regenera y guarda** el pronóstico si los datos ya lo
  // habían alcanzado. Por eso, cuando devuelve algo nuevo, se vuelve a pedir el
  // panorama: si no, las tarjetas seguirían diciendo que hay que actualizar
  // mientras la gráfica de al lado ya muestra el pronóstico recalculado.
  useEffect(() => {
    let vigente = true;
    setCargandoGrafica(true);
    api
      .pronostico({ objetivo, horizonte })
      .then((r) => {
        if (!vigente) return null;
        setPronostico(r);
        return r?.pronostico?.length ? api.panorama(objetivo) : null;
      })
      .then((fresco) => vigente && fresco && setPanorama(fresco))
      .catch(() => vigente && setPronostico(null))
      .finally(() => vigente && setCargandoGrafica(false));
    return () => {
      vigente = false;
    };
  }, [objetivo, horizonte]);

  // El CSV lleva observado y pronosticado en una sola tabla, con la banda al
  // lado: quien lo abra debe poder rehacer la gráfica entera, no solo la parte
  // medida.
  const filasCSV = useMemo(() => {
    if (!pronostico) return [];
    return [
      ...(pronostico.observado ?? []).map((p) => ({
        fecha: p.fecha_hora,
        tipo: "observado",
        valor: p.valor,
      })),
      ...(pronostico.pronostico ?? []).map((p) => ({
        fecha: p.fecha_objetivo,
        tipo: "pronosticado",
        valor: p.valor_estimado,
        minimo: p.limite_inferior,
        maximo: p.limite_superior,
      })),
    ];
  }, [pronostico]);

  const esPrecio = objetivo === "precio_bolsa";
  const indicador = esPrecio ? panorama?.precio : panorama?.demanda;
  const resumenes = panorama?.pronosticos ?? [];
  const elegido = resumenes.find((p) => p.horizonte === horizonte);

  // Si el horizonte activo no tiene modelo entrenado, se salta al primero que
  // sí lo tenga: mejor mostrar algo útil que una tarjeta vacía por defecto.
  useEffect(() => {
    if (!resumenes.length) return;
    const activo = resumenes.find((p) => p.horizonte === horizonte);
    if (activo?.hay_modelo) return;
    const primero = resumenes.find((p) => p.hay_modelo);
    if (primero) setHorizonte(primero.horizonte);
  }, [resumenes, horizonte]);

  if (cargandoPanorama && !panorama) return <Cargando texto="leyendo el sistema" />;

  if (!panorama?.instante) {
    return (
      <div className="seccion">
        <Panel>
          <Vacio
            titulo="Todavía no hay datos"
            texto="Un usuario con permisos de analista debe ejecutar la primera descarga de datos de XM."
          />
        </Panel>
      </div>
    );
  }

  return (
    <div className="seccion">
      {/* Solo aparece al imprimir: en papel el informe sale suelto, sin barra
          de navegación, así que necesita cabecera propia que diga de quién es.
          Aquí el fondo ya es blanco y el logo va a todo color, sin placa. */}
      <header className="cabecera-informe">
        <LogoTdeA tamano="informe" conPlaca={false} />
        <div>
          <div className="rotulo">Sistema Interconectado Nacional</div>
          <strong>Informe de pronóstico energético</strong>
        </div>
      </header>

      <Portada
        panorama={panorama}
        indicador={indicador}
        esPrecio={esPrecio}
        objetivo={objetivo}
        alCambiarObjetivo={setObjetivo}
      />

      <Revelar>
        <div className="seccion__cabecera" style={{ marginBottom: 12 }}>
          <div>
            <div className="rotulo">Hacia dónde va</div>
            <h2 className="seccion__titulo">Pronóstico</h2>
            <p className="seccion__nota">
              Elige un plazo. La zona sombreada de la gráfica es el margen de error
              del modelo: cuanto más lejos se mira, más ancha.
            </p>
          </div>
        </div>
      </Revelar>

      <Revelar orden={1}>
        <div className="horizontes">
          {resumenes.map((resumen) => (
            <TarjetaHorizonte
              key={resumen.horizonte}
              resumen={resumen}
              activo={resumen.horizonte === horizonte}
              esPrecio={esPrecio}
              onClick={() => setHorizonte(resumen.horizonte)}
            />
          ))}
        </div>
      </Revelar>

      <Revelar orden={2} className="separado">
        <Panel
          rotulo={elegido?.nombre_modelo ? `Modelo ${elegido.nombre_modelo}` : "Pronóstico"}
          titulo={`${esPrecio ? "Precio" : "Demanda"} en los próximos ${
            elegido?.etiqueta ?? ""
          }`}
          ajustado
          pie={
            elegido?.error_tipico
              ? `La línea continua es lo que ya ocurrió; la discontinua, lo que el modelo estima. Suele acertar dentro de ± ${decimales(
                  elegido.error_tipico,
                  0
                )} ${elegido.unidad}.`
              : "La línea continua es lo que ya ocurrió; la discontinua, lo que el modelo estima."
          }
        >
          {cargandoGrafica ? (
            <Cargando texto="calculando" />
          ) : pronostico ? (
            <>
              <div ref={contenedorGrafica}>
                <GraficaPronostico
                  observado={pronostico.observado ?? []}
                  pronostico={pronostico.pronostico ?? []}
                  unidad={pronostico.unidad ?? ""}
                  forma={forma}
                  animar
                />
              </div>
              <Herramientas
                forma={forma}
                alCambiarForma={setForma}
                contenedor={contenedorGrafica}
                nombre={`${esPrecio ? "precio" : "demanda"}-${elegido?.etiqueta ?? ""}`}
                tituloInforme={`Pronóstico de ${esPrecio ? "precio" : "demanda"} · SIN · TdeA`}
                datosCSV={filasCSV}
                columnasCSV={COLUMNAS_CSV}
                alFallar={alAvisar}
              />
            </>
          ) : (
            <Vacio
              titulo="Sin pronóstico para este plazo"
              texto="Todavía no hay un modelo entrenado para esta combinación."
            />
          )}
        </Panel>
      </Revelar>

      <Revelar orden={3}>
        <div className="seccion__cabecera separado" style={{ marginBottom: 12 }}>
          <div>
            <div className="rotulo">Por qué</div>
            <h2 className="seccion__titulo">Qué hay detrás</h2>
            <p className="seccion__nota">
              En Colombia el precio de la energía es, sobre todo, una historia sobre
              agua: cuando los embalses bajan, entran las plantas térmicas —que queman
              gas o carbón— y el precio sube.
            </p>
          </div>
        </div>
      </Revelar>

      <div className="rejilla rejilla--mitad">
        <Revelar orden={4}>
          <Medidor embalses={panorama.embalses} />
        </Revelar>
        <Revelar orden={5}>
          <Mezcla partes={panorama.mezcla} />
        </Revelar>
      </div>

      <Revelar orden={6} className="separado">
        <Departamentos
          departamentos={panorama.departamentos}
          alVerMapa={alIrAlMapa}
        />
      </Revelar>

      {/* Solo se ve al imprimir. Un informe suelto tiene que decir de dónde
          salió y con qué datos, o dentro de un mes nadie sabrá qué está
          mirando ni si sigue vigente. */}
      <p className="pie-informe">
        Sistema Interconectado Nacional · Tecnológico de Antioquia. Datos de XM
        con corte a {fechaHora(panorama.instante)}. Generado el{" "}
        {fechaHora(new Date().toISOString())}. Los valores pronosticados son
        estimaciones de un modelo estadístico, no mediciones.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------

function Portada({ panorama, indicador, esPrecio, objetivo, alCambiarObjetivo }) {
  const pronostico24 = panorama.pronosticos?.find((p) => p.horizonte === 24);
  const tendencia = pronostico24?.tendencia ?? "estable";

  // El titular se parte para poder resaltar el verbo, que es donde está la
  // información: "subirá", "bajará", "se mantendrá".
  const { antes, verbo, despues } = partirTitular(panorama.titular);

  return (
    <header className="portada">
      <PulsoCarga />
      <div className="portada__cuerpo">
        <div>
          <div className="rotulo">
            {fechaHora(panorama.instante)} · Sistema Interconectado Nacional
          </div>
          <h1 className="portada__titular">
            {antes}
            {verbo && (
              <em className={tendencia === "sube" ? "sube" : undefined}>{verbo}</em>
            )}
            {despues}
          </h1>
          <p className="portada__detalle">{panorama.detalle}</p>

          <div className="fila" style={{ marginTop: 18 }}>
            {OBJETIVOS.map((o) => (
              <button
                key={o.valor}
                type="button"
                className="pildora"
                aria-pressed={o.valor === objetivo}
                onClick={() => alCambiarObjetivo(o.valor)}
                title={o.pregunta}
              >
                {o.etiqueta}
              </button>
            ))}
          </div>
        </div>

        <div className="portada__ahora">
          <div className="rotulo">Ahora mismo</div>
          <span className="portada__cifra">
            {esPrecio ? (
              <Contador valor={indicador?.valor} formato={(v) => decimales(v, 0)} />
            ) : (
              <Contador
                valor={indicador?.valor != null ? indicador.valor / 1e6 : null}
                formato={(v) => decimales(v, 1)}
              />
            )}
            <span className="portada__unidad">{esPrecio ? "COP/kWh" : "GWh/h"}</span>
          </span>
          <div className="portada__pie">
            {indicador?.variacion_24h == null ? (
              "sin comparación disponible"
            ) : (
              <>
                <span
                  className={`delta delta--${indicador.variacion_24h > 0 ? "sube" : "baja"}`}
                >
                  {indicador.variacion_24h > 0 ? "▲" : "▼"}{" "}
                  {Math.abs(indicador.variacion_24h).toFixed(1)} %
                </span>{" "}
                frente a ayer a esta hora
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function TarjetaHorizonte({ resumen, activo, esPrecio, onClick }) {
  const valor = resumen.valor_final;
  const mostrado = esPrecio ? valor : valor != null ? valor / 1e6 : null;

  return (
    <button
      type="button"
      className="horizonte"
      aria-pressed={activo}
      /* Se puede pulsar mientras exista modelo, aunque todavía no haya
         pronóstico vigente: pulsarla es justamente lo que lo calcula. */
      disabled={!resumen.hay_modelo}
      onClick={onClick}
    >
      <div className="rotulo">Dentro de {resumen.etiqueta}</div>

      {!resumen.disponible ? (
        <>
          <div className="horizonte__cifra" style={{ color: "var(--tinta-3)" }}>
            —
          </div>
          <div className="horizonte__pie">
            {resumen.hay_modelo ? "pulsa para calcularlo" : "sin modelo entrenado"}
          </div>
        </>
      ) : (
        <>
          <div className="horizonte__cifra">
            <Contador
              valor={mostrado}
              formato={(v) => decimales(v, esPrecio ? 0 : 1)}
              duracion={700}
            />
            <span className="cifra__unidad">{esPrecio ? "COP/kWh" : "GWh/h"}</span>
          </div>
          <div className="horizonte__pie">
            <span className={`flecha flecha--${resumen.tendencia}`} aria-hidden="true">
              {FLECHAS[resumen.tendencia]}
            </span>
            {resumen.variacion == null
              ? "sin comparación"
              : resumen.tendencia === "estable"
                ? "se mantiene"
                : `${Math.abs(resumen.variacion).toFixed(1)} % ${
                    resumen.tendencia === "sube" ? "más caro" : "más barato"
                  }`}
          </div>
        </>
      )}
    </button>
  );
}

function Medidor({ embalses }) {
  const nivel = embalses?.nivel;

  return (
    <Panel rotulo="Hidrología" titulo="Nivel de los embalses">
      <div className="fila" style={{ justifyContent: "space-between" }}>
        <span className="cifra__valor" style={{ margin: 0, fontSize: 30 }}>
          <Contador valor={nivel} formato={(v) => decimales(v, 1)} />
          <span className="cifra__unidad">%</span>
        </span>
        {embalses?.variacion_7d != null && (
          <span className="insignia">
            {embalses.variacion_7d > 0 ? "+" : ""}
            {embalses.variacion_7d.toFixed(1)} pts en 7 días
          </span>
        )}
      </div>

      <div className="medidor__barra">
        <div
          className={`medidor__nivel medidor__nivel--${embalses?.estado ?? "normal"}`}
          style={{ width: `${Math.min(100, Math.max(0, nivel ?? 0))}%` }}
        />
      </div>
      <div className="medidor__marcas">
        <span>0 %</span>
        <span>vacío ← → lleno</span>
        <span>100 %</span>
      </div>

      <p className="ayuda">{embalses?.descripcion}</p>
    </Panel>
  );
}

function Mezcla({ partes = [] }) {
  const colores = useMemo(
    () => new Map(TECNOLOGIAS.map((t) => [t.clave, t.color])),
    []
  );
  const colorDe = (clave) => colores.get(clave) ?? "var(--tec-otras)";

  if (!partes.length) {
    return (
      <Panel rotulo="Generación" titulo="De dónde viene la energía">
        <Cargando texto="sin datos de generación" />
      </Panel>
    );
  }

  return (
    <Panel rotulo="Generación" titulo="De dónde viene la energía">
      <div className="mezcla-barra" role="img" aria-label={resumirMezcla(partes)}>
        {partes.map((parte) => (
          <div
            key={parte.clave}
            className="mezcla-barra__parte"
            style={{ flexGrow: parte.porcentaje, background: colorDe(parte.clave) }}
          />
        ))}
      </div>

      <div className="mezcla-lista">
        {partes.map((parte) => (
          <div className="mezcla-lista__fila" key={parte.clave}>
            <span
              className="mezcla-lista__punto"
              style={{ background: colorDe(parte.clave) }}
              aria-hidden="true"
            />
            <span>{parte.etiqueta}</span>
            <span className="mezcla-lista__valor">
              <Contador valor={parte.porcentaje} formato={(v) => decimales(v, 1)} /> %
            </span>
          </div>
        ))}
      </div>

      <p className="ayuda">Reparto de la generación del país en las últimas 24 horas.</p>
    </Panel>
  );
}

function Departamentos({ departamentos = [], alVerMapa }) {
  const maximo = Math.max(...departamentos.map((d) => d.participacion ?? 0), 1);

  if (!departamentos.length) {
    return (
      <Panel rotulo="Territorio" titulo="Dónde se consume">
        <Vacio
          titulo="Sin datos territoriales"
          texto="Todavía no se ha descargado la demanda por departamento."
        />
      </Panel>
    );
  }

  return (
    <Panel
      rotulo="Territorio"
      titulo="Dónde se consume"
      acciones={
        alVerMapa && (
          <button className="boton boton--fantasma" onClick={alVerMapa}>
            Ver el mapa completo →
          </button>
        )
      }
      pie="Los departamentos marcados como estimados forman parte de un mercado que XM publica agrupado con otros; su cifra es un reparto, no una medición directa."
    >
      {/* Una sola cifra por fila, y una barra que la hace comparable de un
          vistazo. Antes iban los GWh y el porcentaje juntos: dos números por
          línea que decían lo mismo y obligaban a leer seis veces para sacar el
          orden, que era justo lo que la barra ya cuenta sin leer nada. */}
      <div className="deptos">
        {departamentos.map((depto, indice) => (
          <div className="depto-fila" key={depto.codigo_dane}>
            <span className="depto-fila__puesto">{indice + 1}</span>
            <span className="depto-fila__nombre">
              <span>{depto.departamento}</span>
              {depto.estimado && (
                <span className="insignia insignia--estimada">estimado</span>
              )}
            </span>
            <span className="depto-fila__barra" aria-hidden="true">
              <span
                className="depto-fila__relleno"
                style={{ width: `${(depto.participacion ?? 0) / maximo * 100}%` }}
              />
            </span>
            <span className="depto-fila__valor">
              {decimales(depto.participacion, 1)} %
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------------------

/**
 * Parte el titular para poder resaltar el verbo.
 *
 * El servidor devuelve la frase completa; la interfaz solo decide qué palabra
 * lleva color. Se busca el verbo entre un conjunto cerrado en lugar de asumir
 * una posición fija, porque el titular cambia de forma según haya pronóstico o
 * no.
 */
const VERBOS = ["subirá", "bajará", "se mantendrá estable", "subió", "bajó", "se mantiene estable"];

function partirTitular(titular = "") {
  for (const verbo of VERBOS) {
    const posicion = titular.indexOf(verbo);
    if (posicion >= 0) {
      return {
        antes: titular.slice(0, posicion),
        verbo,
        despues: titular.slice(posicion + verbo.length),
      };
    }
  }
  return { antes: titular, verbo: null, despues: "" };
}

function resumirMezcla(partes) {
  return partes.map((p) => `${p.etiqueta} ${p.porcentaje} por ciento`).join(", ");
}
