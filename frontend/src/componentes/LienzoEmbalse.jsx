import { useEffect, useRef } from "react";

/**
 * Fondo animado del acceso: la curva de carga sobre la lámina del embalse.
 *
 * Dos capas, ambas con contenido real del dominio y no ornamento genérico:
 *
 * 1. **La lámina de agua** — tres ondas sinusoidales superpuestas de periodos
 *    incompatibles entre sí, de modo que el patrón nunca se repite a la vista.
 *    Ocupa el tercio inferior: es el embalse, y el nivel al que se dibuja es
 *    el nivel de llenado.
 * 2. **La curva de carga** — el perfil de demanda de un día colombiano, con su
 *    valle de madrugada, la meseta de la mañana y el pico de las siete de la
 *    tarde. Se traza de izquierda a derecha en bucle, con un punto luminoso en
 *    la cabeza del trazo, como el barrido de un instrumento de despacho.
 *
 * Se dibuja en un `<canvas>` y no en SVG animado porque son cientos de
 * segmentos redibujados a 60 fps: en SVG eso significa cientos de nodos del DOM
 * mutando por fotograma, y el navegador rehace estilo y composición de todos.
 *
 * Respeta `prefers-reduced-motion`: en ese caso pinta un solo fotograma
 * estático con la curva completa, sin bucle de animación.
 */

/** Perfil horario normalizado (0–1) de la demanda nacional en un día típico. */
const CURVA_CARGA = [
  0.42, 0.36, 0.32, 0.30, 0.29, 0.31, 0.38, 0.5, 0.62, 0.7, 0.75, 0.78,
  0.79, 0.77, 0.75, 0.74, 0.75, 0.79, 0.9, 1.0, 0.95, 0.83, 0.68, 0.53,
];

const AGUA = "rgba(0, 147, 148, ";
const CRESTA = "rgba(96, 214, 210, ";

export default function LienzoEmbalse() {
  const referencia = useRef(null);

  useEffect(() => {
    const lienzo = referencia.current;
    if (!lienzo) return;

    const ctx = lienzo.getContext("2d");
    const reducido = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let ancho = 0;
    let alto = 0;
    let animacion = 0;

    function dimensionar() {
      // El canvas se dibuja en píxeles físicos y se escala por CSS: en una
      // pantalla con densidad 2 el trazo se vería borroso si no se hiciera.
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      ancho = lienzo.clientWidth;
      alto = lienzo.clientHeight;
      lienzo.width = Math.round(ancho * dpr);
      lienzo.height = Math.round(alto * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function ondas(t) {
      const base = alto * 0.84;
      // Tres capas de amplitud y velocidad decrecientes. Las opacidades son
      // deliberadamente muy bajas: al superponerse suman, y con valores más
      // altos el agua deja de leerse como profundidad y se convierte en una
      // franja de color macizo que compite con la tarjeta.
      const capas = [
        { amplitud: 13, periodo: 360, velocidad: 0.00022, opacidad: 0.05, desfase: 0 },
        { amplitud: 9, periodo: 230, velocidad: -0.00031, opacidad: 0.04, desfase: 1.6 },
        { amplitud: 6, periodo: 150, velocidad: 0.00046, opacidad: 0.032, desfase: 3.1 },
      ];

      for (const capa of capas) {
        ctx.beginPath();
        ctx.moveTo(0, alto);
        for (let x = 0; x <= ancho; x += 6) {
          const y =
            base +
            capa.amplitud *
              Math.sin(x / capa.periodo + t * capa.velocidad * 1000 + capa.desfase);
          ctx.lineTo(x, y);
        }
        ctx.lineTo(ancho, alto);
        ctx.closePath();
        ctx.fillStyle = AGUA + capa.opacidad + ")";
        ctx.fill();
      }

      // Línea de superficie: el "nivel" propiamente dicho.
      ctx.beginPath();
      for (let x = 0; x <= ancho; x += 6) {
        const y = base + 13 * Math.sin(x / 360 + t * 0.22);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.strokeStyle = AGUA + "0.34)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    /** Punto de la curva de carga en `u` ∈ [0,1], interpolado entre horas. */
    function alturaCurva(u) {
      const posicion = u * CURVA_CARGA.length;
      const i = Math.floor(posicion) % CURVA_CARGA.length;
      const siguiente = (i + 1) % CURVA_CARGA.length;
      const fraccion = posicion - Math.floor(posicion);
      return CURVA_CARGA[i] + (CURVA_CARGA[siguiente] - CURVA_CARGA[i]) * fraccion;
    }

    function curva(avance) {
      const arriba = alto * 0.14;
      const abajo = alto * 0.6;
      const hasta = Math.max(2, Math.round(ancho * avance));

      const trazo = (limite) => {
        ctx.beginPath();
        for (let x = 0; x <= limite; x += 2) {
          const y = abajo - alturaCurva(x / ancho) * (abajo - arriba);
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      };

      // La curva completa, tenue, siempre visible. Sin ella, al inicio de cada
      // barrido la pantalla se quedaba prácticamente vacía y la animación
      // parecía un fallo de carga en lugar de un instrumento.
      trazo(ancho);
      ctx.strokeStyle = CRESTA + "0.16)";
      ctx.lineWidth = 1.2;
      ctx.stroke();

      // Relleno bajo el tramo ya recorrido: da cuerpo al trazo sin competir.
      trazo(hasta);
      ctx.lineTo(hasta, abajo);
      ctx.lineTo(0, abajo);
      ctx.closePath();
      const degradado = ctx.createLinearGradient(0, arriba, 0, abajo);
      degradado.addColorStop(0, AGUA + "0.2)");
      degradado.addColorStop(1, AGUA + "0)");
      ctx.fillStyle = degradado;
      ctx.fill();

      // Tramo recorrido, brillante.
      trazo(hasta);
      ctx.strokeStyle = CRESTA + "0.72)";
      ctx.lineWidth = 1.8;
      ctx.stroke();

      // Cabeza del barrido, con halo.
      const y = abajo - alturaCurva(avance) * (abajo - arriba);
      ctx.beginPath();
      ctx.arc(hasta, y, 11, 0, Math.PI * 2);
      ctx.fillStyle = CRESTA + "0.1)";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(hasta, y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = "#8ff0eb";
      ctx.fill();
    }

    function fotograma(t) {
      ctx.clearRect(0, 0, ancho, alto);
      ondas(t / 1000);
      // Un barrido completo cada 11 s: lo bastante lento para leerse como un
      // instrumento y no como una animación de carga.
      curva(((t / 11000) % 1 + 1) % 1);
      animacion = requestAnimationFrame(fotograma);
    }

    function estatico() {
      ctx.clearRect(0, 0, ancho, alto);
      ondas(0);
      curva(1);
    }

    function alRedimensionar() {
      dimensionar();
      if (reducido) estatico();
    }

    dimensionar();
    if (reducido) estatico();
    else animacion = requestAnimationFrame(fotograma);

    window.addEventListener("resize", alRedimensionar);
    return () => {
      cancelAnimationFrame(animacion);
      window.removeEventListener("resize", alRedimensionar);
    };
  }, []);

  return <canvas ref={referencia} className="acceso__lienzo" aria-hidden="true" />;
}
