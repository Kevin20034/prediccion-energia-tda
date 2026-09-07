import { useEffect, useRef } from "react";

/**
 * Ejecuta `accion` cada `minutos`, pero solo mientras la pestaña está visible.
 *
 * Refrescar una pestaña que nadie mira gasta batería y cuota de la API, y en un
 * portátil suspendido despierta la red para nada. Al volver a la pestaña se
 * dispara una vez de inmediato, que es justo cuando el usuario quiere el dato
 * fresco: es el momento en que vuelve a mirar.
 *
 * La acción se guarda en una referencia para que cambiarla no reinicie el
 * temporizador. Si dependiera de `accion` en el efecto, cada render de un padre
 * que la redefina en línea reiniciaría la cuenta y el refresco no llegaría nunca.
 */
export function useRefresco(accion, minutos = 5) {
  const guardada = useRef(accion);
  guardada.current = accion;

  useEffect(() => {
    let id = null;

    const visible = () => document.visibilityState === "visible";
    const disparar = () => {
      if (visible()) guardada.current();
    };

    const parar = () => {
      if (id) {
        clearInterval(id);
        id = null;
      }
    };

    const arrancar = () => {
      parar();
      id = setInterval(disparar, minutos * 60_000);
    };

    const alCambiarVisibilidad = () => {
      if (visible()) {
        disparar();
        arrancar();
      } else {
        parar();
      }
    };

    arrancar();
    document.addEventListener("visibilitychange", alCambiarVisibilidad);

    return () => {
      parar();
      document.removeEventListener("visibilitychange", alCambiarVisibilidad);
    };
  }, [minutos]);
}
