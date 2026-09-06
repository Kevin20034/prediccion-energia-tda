import { useEffect, useRef } from "react";

import { COLOR } from "../tokens";
import { movimientoReducido } from "./animacion";

/**
 * Marca de agua animada de la portada: la curva de carga real del sistema.
 *
 * Es la misma figura que anima el acceso, aquí en versión clara y muy tenue
 * detrás del titular. Repetirla es deliberado: da continuidad entre la pantalla
 * de entrada y el tablero, y mantiene a la vista el objeto del que trata toda
 * la aplicación.
 *
 * Si llega `serie` —los últimos puntos observados— dibuja los datos de verdad.
 * Si no, cae al perfil típico de un día colombiano, para que la portada nunca
 * aparezca vacía mientras carga.
 */

const PERFIL_TIPICO = [
  0.42, 0.36, 0.32, 0.3, 0.29, 0.31, 0.38, 0.5, 0.62, 0.7, 0.75, 0.78,
  0.79, 0.77, 0.75, 0.74, 0.75, 0.79, 0.9, 1.0, 0.95, 0.83, 0.68, 0.53,
];

/** Segundos que tarda el destello en recorrer la curva de lado a lado. */
const CICLO = 9;

export default function PulsoCarga({ serie }) {
  const referencia = useRef(null);
  // La serie entra por `ref` y no por dependencia del efecto para que llegar
  // los datos no reinicie la animación a mitad de recorrido.
  const datos = useRef(PERFIL_TIPICO);

  useEffect(() => {
    if (serie?.length > 3) datos.current = normalizar(serie);
  }, [serie]);

  useEffect(() => {
    const lienzo = referencia.current;
    if (!lienzo) return undefined;

    const ctx = lienzo.getContext("2d");
    const reducido = movimientoReducido();
    let ancho = 0;
    let alto = 0;
    let animacion = 0;

    function dimensionar() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      ancho = lienzo.clientWidth;
      alto = lienzo.clientHeight;
      lienzo.width = Math.round(ancho * dpr);
      lienzo.height = Math.round(alto * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    const alturaEn = (u) => {
      const puntos = datos.current;
      const posicion = u * (puntos.length - 1);
      const i = Math.floor(posicion);
      const siguiente = Math.min(i + 1, puntos.length - 1);
      return puntos[i] + (puntos[siguiente] - puntos[i]) * (posicion - i);
    };

    function trazar(hasta) {
      const arriba = alto * 0.2;
      const abajo = alto * 0.94;
      ctx.beginPath();
      for (let x = 0; x <= hasta; x += 2) {
        const y = abajo - alturaEn(x / ancho) * (abajo - arriba);
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      return { arriba, abajo };
    }

    function pintar(avance) {
      ctx.clearRect(0, 0, ancho, alto);

      const { arriba, abajo } = trazar(ancho);
      ctx.lineTo(ancho, abajo);
      ctx.lineTo(0, abajo);
      ctx.closePath();
      const relleno = ctx.createLinearGradient(0, arriba, 0, abajo);
      relleno.addColorStop(0, "rgba(32, 192, 147, 0.16)");
      relleno.addColorStop(1, "rgba(32, 192, 147, 0)");
      ctx.fillStyle = relleno;
      ctx.fill();

      trazar(ancho);
      ctx.strokeStyle = "rgba(32, 192, 147, 0.32)";
      ctx.lineWidth = 1.4;
      ctx.stroke();

      if (reducido) return;

      // Destello que recorre la curva: un tramo corto y más opaco que se
      // desplaza. Da señal de vida sin repintar toda la figura de color.
      const largo = ancho * 0.16;
      const centro = avance * (ancho + largo) - largo / 2;
      const degradado = ctx.createLinearGradient(centro - largo, 0, centro + largo, 0);
      degradado.addColorStop(0, "rgba(32, 192, 147, 0)");
      degradado.addColorStop(0.5, COLOR.observado);
      degradado.addColorStop(1, "rgba(32, 192, 147, 0)");

      trazar(ancho);
      ctx.strokeStyle = degradado;
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    function fotograma(t) {
      pintar(((t / (CICLO * 1000)) % 1 + 1) % 1);
      animacion = requestAnimationFrame(fotograma);
    }

    function alRedimensionar() {
      dimensionar();
      pintar(0);
    }

    dimensionar();
    if (reducido) pintar(0);
    else animacion = requestAnimationFrame(fotograma);

    window.addEventListener("resize", alRedimensionar);
    return () => {
      cancelAnimationFrame(animacion);
      window.removeEventListener("resize", alRedimensionar);
    };
  }, []);

  return <canvas ref={referencia} className="portada__pulso" aria-hidden="true" />;
}

/** Lleva la serie al rango 0-1 para poder dibujarla sin conocer su unidad. */
function normalizar(serie) {
  const valores = serie.map((p) => p.valor ?? p).filter((v) => v != null);
  if (valores.length < 4) return PERFIL_TIPICO;

  const minimo = Math.min(...valores);
  const maximo = Math.max(...valores);
  if (maximo === minimo) return PERFIL_TIPICO;

  return valores.map((v) => (v - minimo) / (maximo - minimo));
}
