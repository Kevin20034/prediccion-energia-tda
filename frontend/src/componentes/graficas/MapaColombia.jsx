import { useEffect, useMemo, useRef, useState } from "react";

import { energia, porcentaje } from "../../formato";
import { COLOR_SIN_DATO, RAMPA_MAPA } from "../../tokens";

/**
 * Mapa coroplético de la demanda por departamento.
 *
 * Proyección
 * ----------
 * Se usa una Mercator sencilla implementada aquí mismo en lugar de traer
 * `d3-geo`. Para un solo país que abarca 17 grados de longitud y 18 de latitud,
 * la diferencia frente a una proyección cónica adecuada es de unos pocos
 * píxeles, y la alternativa es añadir una dependencia entera para calcular dos
 * fórmulas. La latitud pasa por la transformación de Mercator (no es lineal) y
 * la longitud es proporcional: eso basta para que Colombia no salga achatada.
 *
 * Escala de color
 * ---------------
 * Dos escalas, según lo que se esté pintando:
 *
 * * `cuantiles` (demanda) — rampa secuencial de un solo tono. Codifica
 *   magnitud, y el ojo lee magnitud en la luminosidad. Los cortes son por
 *   cuantiles y no lineales: la demanda está tan concentrada (Bogotá y
 *   Antioquia solas se llevan una parte enorme) que una escala lineal dejaría
 *   veinte departamentos del mismo color y el mapa no diría nada.
 *
 * * `divergente` (anomalía de temperatura) — rampa de dos tonos con gris
 *   neutro en el centro, y cortes **simétricos respecto al cero**. La simetría
 *   no es estética: sin ella, medio grado por encima de lo normal se pintaría
 *   con la misma intensidad que tres, y el mapa exageraría.
 *
 * Los departamentos sin conexión al SIN se pintan en gris neutro con su propia
 * entrada en la leyenda: no tienen demanda cero, tienen otra fuente de
 * abastecimiento.
 */

const ANCHO = 620;
const ALTO = 700;

export default function MapaColombia({
  geo,
  departamentos = [],
  seleccionado,
  alSeleccionar,
  /** Campo por el que se colorea. */
  campo = "demanda_24h",
  rampa = RAMPA_MAPA,
  /** `"cuantiles"` para magnitud, `"divergente"` para desviaciones. */
  escala = "cuantiles",
  /** Extremo de la escala divergente. Se ignora en modo cuantiles. */
  extremo = 0,
  /** Contenido de la etiqueta flotante. Sin ella se muestra la de demanda. */
  detalle,
  etiquetaMapa = "Mapa de la demanda energética por departamento de Colombia",
}) {
  const [flotante, setFlotante] = useState(null);
  const contenedor = useRef(null);

  const porCodigo = useMemo(
    () => new Map(departamentos.map((d) => [d.codigo_dane, d])),
    [departamentos]
  );

  const { proyectar, ancho, alto } = useMemo(() => proyeccionDe(geo), [geo]);

  const cortes = rampa.length;

  /** Umbrales que separan los tramos de color. */
  const umbrales = useMemo(() => {
    if (escala === "divergente") {
      // Simétricos alrededor del cero. Con un número impar de pasos, el tramo
      // central queda centrado en cero y es el que se lee como "en su normal".
      const tope = extremo || 1;
      const pasos = cortes - 1;
      return Array.from(
        { length: pasos },
        (_, i) => -tope + ((i + 1) * (2 * tope)) / (pasos + 1)
      );
    }

    const valores = departamentos
      .map((d) => d[campo])
      .filter((v) => v != null && v > 0)
      .sort((a, b) => a - b);
    if (valores.length < cortes) return [];
    return Array.from({ length: cortes - 1 }, (_, i) =>
      valores[Math.floor(((i + 1) / cortes) * valores.length)]
    );
  }, [departamentos, campo, escala, extremo, cortes]);

  /** Orden de aparición, para que el mapa se lea solo al entrar. */
  const orden = useMemo(() => {
    const clave = escala === "divergente" ? (d) => Math.abs(d[campo] ?? 0) : (d) => d[campo] ?? -1;
    const lista = [...departamentos].sort((a, b) => clave(b) - clave(a)).map((d) => d.codigo_dane);
    return new Map(lista.map((codigo, i) => [codigo, i]));
  }, [departamentos, campo, escala]);

  // Al pulsar fuera del mapa se cierra la etiqueta flotante; sin esto se queda
  // colgada cuando el puntero sale del SVG por un borde.
  useEffect(() => {
    const cerrar = () => setFlotante(null);
    window.addEventListener("blur", cerrar);
    return () => window.removeEventListener("blur", cerrar);
  }, []);

  if (!geo) return <div className="cargando">cargando mapa</div>;

  function colorDe(dato) {
    if (!dato) return COLOR_SIN_DATO;

    // "No está en el SIN" solo significa algo cuando lo que se pinta es
    // demanda: esos departamentos no aparecen en ningún mercado de XM. Su
    // temperatura, en cambio, existe igual que la de los demás, y dejarlos
    // grises en el mapa de anomalía escondería cinco departamentos por un
    // motivo que ahí no aplica.
    if (escala !== "divergente" && !dato.interconectado) return COLOR_SIN_DATO;

    const valor = dato[campo];
    if (valor == null || !umbrales.length) return COLOR_SIN_DATO;
    const indice = umbrales.filter((u) => valor > u).length;
    return rampa[Math.min(indice, rampa.length - 1)];
  }

  function alEntrar(evento, dato, nombreGeo) {
    const caja = contenedor.current?.getBoundingClientRect();
    if (!caja) return;
    setFlotante({
      x: evento.clientX - caja.left,
      y: evento.clientY - caja.top,
      dato,
      nombre: dato?.departamento ?? capitalizar(nombreGeo),
    });
  }

  return (
    <div className="mapa" ref={contenedor}>
      <svg
        viewBox={`0 0 ${ancho} ${alto}`}
        role="img"
        aria-label={etiquetaMapa}
        onMouseLeave={() => setFlotante(null)}
      >
        {geo.features.map((rasgo) => {
          const dato = porCodigo.get(rasgo.properties.codigo);
          // En el mapa de anomalía las ZNI son departamentos como los demás:
          // tienen temperatura, se pueden consultar y no llevan la nota de
          // "no se abastece del SIN", que ahí no viene a cuento.
          const sinSin = dato && !dato.interconectado && escala !== "divergente";
          const activo = seleccionado === rasgo.properties.codigo;

          return (
            <path
              key={rasgo.properties.codigo}
              d={trazar(rasgo.geometry, proyectar)}
              fill={colorDe(dato)}
              className={[
                "mapa__depto",
                sinSin ? "mapa__depto--sin-sin" : "",
                activo ? "mapa__depto--activo" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              style={{
                animationDelay: `${(orden.get(rasgo.properties.codigo) ?? 0) * 22}ms`,
              }}
              tabIndex={sinSin ? -1 : 0}
              role={sinSin ? undefined : "button"}
              aria-label={
                dato
                  ? `${dato.departamento}: ${
                      sinSin
                        ? "sin conexión al Sistema Interconectado Nacional"
                        : escala === "divergente"
                          ? `${dato[campo] == null ? "sin dato" : `${dato[campo] > 0 ? "+" : ""}${dato[campo]} grados frente a su normal`}`
                          : `${energia(dato[campo]).valor} ${energia(dato[campo]).unidad} en 24 horas`
                    }`
                  : rasgo.properties.nombre
              }
              onMouseMove={(e) => alEntrar(e, dato, rasgo.properties.nombre)}
              onFocus={() => alSeleccionar?.(sinSin ? null : rasgo.properties.codigo)}
              onClick={() => !sinSin && alSeleccionar?.(rasgo.properties.codigo)}
              onKeyDown={(e) => {
                if (!sinSin && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  alSeleccionar?.(rasgo.properties.codigo);
                }
              }}
            />
          );
        })}
      </svg>

      {flotante && (
        <div
          className="mapa__flotante"
          style={{ left: flotante.x, top: flotante.y }}
          aria-hidden="true"
        >
          <div className="pista">
            <div className="pista__momento">{flotante.nombre}</div>
            {!flotante.dato || !flotante.dato.interconectado ? (
              <div className="pista__nota" style={{ border: "none", marginTop: 0 }}>
                Zona No Interconectada: no se abastece del SIN.
              </div>
            ) : detalle ? (
              detalle(flotante.dato)
            ) : (
              <>
                <div className="pista__linea">
                  <span className="pista__nombre">24 h</span>
                  <span className="pista__valor">
                    {energia(flotante.dato.demanda_24h).valor}{" "}
                    {energia(flotante.dato.demanda_24h).unidad}
                  </span>
                </div>
                <div className="pista__linea">
                  <span className="pista__nombre">del país</span>
                  <span className="pista__valor">
                    {porcentaje(flotante.dato.participacion)}
                  </span>
                </div>
                <div className="pista__nota">
                  {flotante.dato.estimado
                    ? "valor estimado por reparto de mercado"
                    : "atribución directa desde XM"}
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Proyección y trazado
// ---------------------------------------------------------------------------

/** Mercator ajustada a la envolvente del GeoJSON, con margen. */
function proyeccionDe(geo) {
  if (!geo) return { proyectar: () => [0, 0], ancho: ANCHO, alto: ALTO };

  // Ambos ejes tienen que estar en las mismas unidades. La `y` de Mercator sale
  // de una expresión con la latitud en radianes, así que la `x` también va en
  // radianes: mezclar grados en un eje y radianes en el otro deja la relación
  // de aspecto 57 veces achatada y el país sale como una mancha horizontal.
  const radianes = (grados) => (grados * Math.PI) / 180;
  const mercator = (lat) =>
    Math.log(Math.tan(Math.PI / 4 + radianes(Math.max(-85, Math.min(85, lat))) / 2));

  let xMin = Infinity;
  let xMax = -Infinity;
  let yMin = Infinity;
  let yMax = -Infinity;

  for (const rasgo of geo.features) {
    for (const anillo of anillosDe(rasgo.geometry)) {
      for (const [lon, lat] of anillo) {
        const x = radianes(lon);
        const y = mercator(lat);
        if (x < xMin) xMin = x;
        if (x > xMax) xMax = x;
        if (y < yMin) yMin = y;
        if (y > yMax) yMax = y;
      }
    }
  }

  const margen = 12;
  // Una sola escala para los dos ejes: escalarlos por separado estiraría el
  // país para llenar el lienzo y deformaría la silueta.
  const escala = Math.min(
    (ANCHO - margen * 2) / (xMax - xMin),
    (ALTO - margen * 2) / (yMax - yMin)
  );
  const ancho = (xMax - xMin) * escala + margen * 2;
  const alto = (yMax - yMin) * escala + margen * 2;

  const proyectar = ([lon, lat]) => [
    (radianes(lon) - xMin) * escala + margen,
    // El eje Y del SVG crece hacia abajo y la latitud hacia arriba.
    (yMax - mercator(lat)) * escala + margen,
  ];

  return { proyectar, ancho, alto };
}

function anillosDe(geometria) {
  if (!geometria) return [];
  return geometria.type === "Polygon"
    ? geometria.coordinates
    : geometria.coordinates.flat();
}

function trazar(geometria, proyectar) {
  const partes = [];
  for (const anillo of anillosDe(geometria)) {
    if (anillo.length < 3) continue;
    const puntos = anillo.map(proyectar);
    partes.push(
      `M${puntos.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join("L")}Z`
    );
  }
  return partes.join("");
}

function capitalizar(texto = "") {
  return texto
    .toLowerCase()
    .replace(/(^|\s|-)\p{L}/gu, (letra) => letra.toUpperCase());
}
