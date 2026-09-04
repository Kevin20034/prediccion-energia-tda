import { useEffect, useRef, useState } from "react";

/**
 * Utilidades de movimiento.
 *
 * Todas comprueban `prefers-reduced-motion` y, cuando está activo, saltan
 * directamente al estado final. Eso significa que quien haya pedido no ver
 * movimiento ve exactamente el mismo contenido, no una versión degradada: la
 * animación es una capa encima, nunca el mecanismo que hace visible algo.
 */

export function movimientoReducido() {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** Suavizado de salida: rápido al principio, se posa al final. */
const suavizar = (t) => 1 - (1 - t) ** 3;

/**
 * Cuenta desde cero (o desde el valor anterior) hasta `destino`.
 *
 * Se usa `requestAnimationFrame` y no una transición CSS porque lo que cambia
 * es el **texto** del número, no una propiedad de estilo: CSS no sabe
 * interpolar "1.046,5".
 *
 * El conteo tiene una función más allá del adorno: da al ojo una referencia de
 * magnitud. Ver un número subir hasta 1.046 comunica "esto es grande" mejor que
 * verlo aparecer ya escrito.
 */
export function useContador(destino, { duracion = 900, activo = true } = {}) {
  const [valor, setValor] = useState(() => (movimientoReducido() ? destino : 0));
  const anterior = useRef(0);

  useEffect(() => {
    if (destino == null || Number.isNaN(destino)) {
      setValor(destino);
      return undefined;
    }
    if (!activo || movimientoReducido()) {
      setValor(destino);
      anterior.current = destino;
      return undefined;
    }

    const origen = anterior.current;
    const inicio = performance.now();
    let cuadro = 0;

    const paso = (ahora) => {
      const avance = Math.min(1, (ahora - inicio) / duracion);
      setValor(origen + (destino - origen) * suavizar(avance));
      if (avance < 1) cuadro = requestAnimationFrame(paso);
      else anterior.current = destino;
    };

    cuadro = requestAnimationFrame(paso);
    return () => cancelAnimationFrame(cuadro);
  }, [destino, duracion, activo]);

  return valor;
}

/**
 * Un número que cuenta hasta su valor.
 *
 * `formato` recibe el valor intermedio y devuelve el texto: así el conteo
 * respeta los separadores de miles y los decimales del resto de la interfaz en
 * lugar de mostrar cifras crudas mientras sube.
 */
export function Contador({ valor, formato = (v) => Math.round(v), duracion = 900 }) {
  const animado = useContador(valor, { duracion });
  if (valor == null || Number.isNaN(valor)) return "—";
  return formato(animado);
}

/**
 * Detecta cuándo un elemento entra en pantalla.
 *
 * Devuelve `[ref, visible]`. `visible` no vuelve a `false` al salir: una
 * sección que se revela y se vuelve a ocultar al desplazarse hacia arriba
 * resulta molesta y hace que la página parezca inestable.
 */
export function useRevelar({ margen = "0px 0px -12% 0px" } = {}) {
  const referencia = useRef(null);
  const [visible, setVisible] = useState(() => movimientoReducido());

  useEffect(() => {
    const nodo = referencia.current;
    if (!nodo || visible) return undefined;

    // Sin soporte de IntersectionObserver se muestra todo: preferible a dejar
    // la página en blanco por una capacidad que solo sirve para animar.
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return undefined;
    }

    const observador = new IntersectionObserver(
      (entradas) => {
        if (entradas.some((e) => e.isIntersecting)) {
          setVisible(true);
          observador.disconnect();
        }
      },
      { rootMargin: margen, threshold: 0.08 }
    );

    observador.observe(nodo);
    return () => observador.disconnect();
  }, [margen, visible]);

  return [referencia, visible];
}

/**
 * Envuelve un bloque para que aparezca al llegar a él.
 *
 * `orden` escalona la entrada de varios hermanos. Se mantiene corto a
 * propósito: por encima de unos 300 ms de retardo total, el escalonado deja de
 * leerse como una composición y empieza a parecer que la página va lenta.
 */
export function Revelar({ orden = 0, children, className = "", ...resto }) {
  const [referencia, visible] = useRevelar();

  return (
    <div
      ref={referencia}
      className={`revelar${visible ? " revelar--visible" : ""} ${className}`.trim()}
      style={{ transitionDelay: `${Math.min(orden, 5) * 60}ms` }}
      {...resto}
    >
      {children}
    </div>
  );
}
