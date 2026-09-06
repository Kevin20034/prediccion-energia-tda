import { useRef, useState } from "react";

import { Conmutador } from "../ui";
import { descargarCSV, descargarGrafica, imprimirInforme, nombreConFecha } from "../../descargas";

/**
 * Barra de herramientas de una gráfica: cómo se ve y cómo se lleva uno.
 *
 * Las tres formas no son adorno; cada una responde mejor a una pregunta:
 *
 *   línea  → ¿cómo evoluciona?   (la forma del recorrido)
 *   área   → ¿cuánto hay?        (el volumen bajo la curva)
 *   barras → ¿cuánto en cada momento? (comparar valores sueltos)
 *
 * Y las descargas cubren los tres usos reales de "me lo llevo": la imagen para
 * pegarla en un documento, los datos para rehacer el cálculo, y el informe
 * impreso para archivar o entregar.
 */

export const FORMAS = [
  { valor: "linea", etiqueta: "Línea" },
  { valor: "area", etiqueta: "Área" },
  { valor: "barras", etiqueta: "Barras" },
];

export function useForma(inicial = "linea") {
  return useState(inicial);
}

export default function Herramientas({
  forma,
  alCambiarForma,
  contenedor,
  nombre = "grafica",
  datosCSV,
  columnasCSV,
  tituloInforme,
  alFallar,
}) {
  const [ocupado, setOcupado] = useState(false);

  async function conAviso(accion) {
    setOcupado(true);
    try {
      await accion();
    } catch (error) {
      alFallar?.({ tipo: "error", texto: error.message });
    } finally {
      setOcupado(false);
    }
  }

  const archivo = nombreConFecha(nombre);

  return (
    <div className="grafica__acciones">
      {alCambiarForma && (
        <Conmutador
          etiqueta="Forma de la gráfica"
          opciones={FORMAS}
          valor={forma}
          alCambiar={alCambiarForma}
        />
      )}

      <span className="hueco" />

      <button
        type="button"
        className="boton boton--fantasma"
        disabled={ocupado}
        onClick={() => conAviso(() => descargarGrafica(contenedor.current, archivo))}
        title="Guardar la gráfica como imagen PNG"
      >
        Imagen
      </button>

      {datosCSV?.length > 0 && (
        <button
          type="button"
          className="boton boton--fantasma"
          disabled={ocupado}
          onClick={() => conAviso(() => descargarCSV(datosCSV, columnasCSV, archivo))}
          title="Descargar los datos en una hoja de cálculo"
        >
          Datos
        </button>
      )}

      <button
        type="button"
        className="boton boton--fantasma"
        disabled={ocupado}
        onClick={() => conAviso(() => imprimirInforme(tituloInforme ?? archivo))}
        title="Abrir el diálogo de impresión para guardarlo en PDF"
      >
        Informe PDF
      </button>
    </div>
  );
}

/** Envuelve una gráfica para poder exportarla: devuelve `[ref, contenedor]`. */
export function useContenedorGrafica() {
  return useRef(null);
}
