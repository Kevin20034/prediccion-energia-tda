/**
 * Descarga de informes: la gráfica como imagen y los datos como hoja de cálculo.
 *
 * Sin librerías. Añadir jsPDF y html2canvas para esto costaría cerca de un
 * megabyte de JavaScript en un paquete que ya ronda los 600 KB, y el navegador
 * ya sabe hacer las tres cosas que hacen falta: serializar un SVG, pintarlo en
 * un lienzo y guardar un archivo. El PDF se obtiene por la vía de imprimir, que
 * además respeta el tamaño de papel que el usuario elija.
 */

/** Fondo de las imágenes exportadas: el mismo del panel, no transparente. */
const FONDO = "#101b16";

/** Margen alrededor de la gráfica exportada, en píxeles. */
const MARGEN = 24;

/**
 * Descarga la gráfica contenida en `nodo` como PNG.
 *
 * Recharts dibuja en SVG, así que se serializa el nodo, se pinta en un lienzo
 * al doble de resolución y se guarda. Dos detalles que no son opcionales:
 *
 * - **Fondo opaco.** El SVG es transparente; sin pintar el fondo antes, el PNG
 *   sale con texto claro sobre nada, que en cualquier visor con fondo blanco
 *   resulta ilegible.
 * - **Ancho y alto explícitos.** El SVG del gráfico usa medidas relativas al
 *   contenedor; sin fijarlas en la copia, Chrome lo rasteriza a un tamaño
 *   arbitrario o directamente falla.
 *
 * Limitación conocida: al rasterizar desde una URL de datos el navegador no
 * carga tipografías web, así que el texto sale con la tipografía equivalente
 * del sistema. Se acepta: la alternativa es empotrar la fuente en base64 y
 * multiplicar por diez el peso del archivo.
 */
export async function descargarGrafica(nodo, nombre = "grafica") {
  const svg = nodo?.querySelector("svg");
  if (!svg) throw new Error("No se encontró ninguna gráfica que descargar.");

  const caja = svg.getBoundingClientRect();
  const ancho = Math.max(1, Math.round(caja.width));
  const alto = Math.max(1, Math.round(caja.height));

  const copia = svg.cloneNode(true);
  copia.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  copia.setAttribute("width", ancho);
  copia.setAttribute("height", alto);
  copia.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);

  const escala = Math.min(window.devicePixelRatio || 1, 2) * 2;
  const lienzo = document.createElement("canvas");
  lienzo.width = (ancho + MARGEN * 2) * escala;
  lienzo.height = (alto + MARGEN * 2) * escala;

  const ctx = lienzo.getContext("2d");
  ctx.scale(escala, escala);
  ctx.fillStyle = FONDO;
  ctx.fillRect(0, 0, ancho + MARGEN * 2, alto + MARGEN * 2);

  const fuente = new XMLSerializer().serializeToString(copia);
  const url = URL.createObjectURL(new Blob([fuente], { type: "image/svg+xml;charset=utf-8" }));

  try {
    const imagen = await cargarImagen(url);
    ctx.drawImage(imagen, MARGEN, MARGEN, ancho, alto);
  } finally {
    URL.revokeObjectURL(url);
  }

  const blob = await new Promise((resolve) => lienzo.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("El navegador no pudo generar la imagen.");
  guardar(blob, `${nombre}.png`);
}

/**
 * Descarga filas como CSV.
 *
 * Se emite con **punto y coma** y BOM inicial. Excel en configuración regional
 * española abre un CSV separado por comas metiendo toda la fila en una sola
 * columna, y sin BOM se come los acentos. Son dos detalles que deciden si el
 * archivo sirve o hay que rehacerlo a mano.
 */
export function descargarCSV(filas, columnas, nombre = "datos") {
  if (!filas?.length) throw new Error("No hay datos que descargar.");

  const escapar = (valor) => {
    if (valor == null) return "";
    const texto = String(valor);
    return /[";\n]/.test(texto) ? `"${texto.replaceAll('"', '""')}"` : texto;
  };

  const lineas = [
    columnas.map((c) => escapar(c.titulo)).join(";"),
    ...filas.map((fila) => columnas.map((c) => escapar(c.valor(fila))).join(";")),
  ];

  const blob = new Blob(["﻿" + lineas.join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  guardar(blob, `${nombre}.csv`);
}

/**
 * Abre el diálogo de impresión para guardar la vista como PDF.
 *
 * "Guardar como PDF" está en el diálogo de impresión de todos los navegadores
 * actuales, así que esto entrega un PDF de verdad sin empotrar un generador. La
 * hoja de estilos de impresión (ver `estilos/informe.css`) se encarga de que lo
 * que salga sea un documento y no una captura del tablero: fondo blanco, sin
 * navegación ni botones, y sin cortar las gráficas por la mitad.
 */
export function imprimirInforme(titulo) {
  const anterior = document.title;
  if (titulo) document.title = titulo;

  // El título del documento es el nombre que el navegador propone para el
  // archivo, así que se restaura solo después de que el diálogo se cierre.
  const restaurar = () => {
    document.title = anterior;
    window.removeEventListener("afterprint", restaurar);
  };
  window.addEventListener("afterprint", restaurar);

  window.print();
}

/** Nombre de archivo con la fecha, para que varias descargas no se pisen. */
export function nombreConFecha(base) {
  const d = new Date();
  const sello = [
    d.getFullYear(),
    String(d.getMonth() + 1).padStart(2, "0"),
    String(d.getDate()).padStart(2, "0"),
  ].join("-");
  return `${base}-${sello}`;
}

// ---------------------------------------------------------------------------

function cargarImagen(url) {
  return new Promise((resolve, reject) => {
    const imagen = new Image();
    imagen.onload = () => resolve(imagen);
    imagen.onerror = () => reject(new Error("No se pudo rasterizar la gráfica."));
    imagen.src = url;
  });
}

function guardar(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = nombre;
  document.body.appendChild(enlace);
  enlace.click();
  enlace.remove();
  // Revocar de inmediato cancela la descarga en algunos navegadores.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
