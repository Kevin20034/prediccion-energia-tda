/**
 * Los mismos tokens de color que `estilos/base.css`, disponibles para JavaScript.
 *
 * Recharts pinta con atributos SVG y no lee variables CSS, así que los valores
 * tienen que existir también aquí. Están duplicados a propósito y con esta nota
 * al lado: si se cambia uno, hay que cambiar el otro. La alternativa —leer las
 * variables con `getComputedStyle` en cada render— cuesta un reflow por gráfica
 * y falla durante el primer pintado, cuando la hoja de estilos aún no se aplicó.
 */

export const COLOR = {
  papel: "#0a1310",
  panel: "#101b16",
  panelAlto: "#16241d",
  hundido: "#0d1713",
  linea: "#22332b",
  lineaFuerte: "#354b40",

  tinta: "#e9f2ea",
  tinta2: "#a3bcae",
  tinta3: "#7a9488",

  observado: "#20c093",
  observadoClaro: "#5ad4b2",
  pronostico: "#f0a640",
  pronosticoClaro: "#f7c079",
  tercero: "#b98cf5",

  alerta: "#f4776a",
  nina: "#5aa8ff",

  // Marca del Tecnológico de Antioquia. Viste la identidad, no los datos.
  lima: "#8cc63f",
  verde: "#00843d",
};

/**
 * Mezcla de generación, en **orden fijo**.
 *
 * Tres categorías y no cinco. Eólica, solar y cogeneración suman menos de un
 * 9 % del sistema, y separarlas obligaba a meter un amarillo junto al ámbar de
 * la térmica: ese par no llega ni a ΔE 12 en visión normal, así que eran dos
 * franjas que nadie podía distinguir. Agrupadas en "otras fuentes" el gráfico
 * dice lo mismo con tres colores que sí se separan.
 *
 * El color sigue a la entidad, nunca a su posición: si un filtro deja fuera una
 * categoría, las demás no cambian de color.
 *
 * Validada sobre el fondo oscuro (#101b16): separación por visión cromática
 * ΔE 9,3 en el peor par, por encima del objetivo de 8, y contraste mínimo
 * 6,8:1.
 */
export const TECNOLOGIAS = [
  { clave: "generacion_hidraulica", etiqueta: "Agua", color: COLOR.observado },
  { clave: "generacion_termica", etiqueta: "Gas y carbón", color: COLOR.pronostico },
  { clave: "generacion_otras", etiqueta: "Sol y viento", color: COLOR.tercero },
];

/** Series que se suman en la categoría "otras" del gráfico de mezcla. */
export const OTRAS_TECNOLOGIAS = [
  "generacion_solar",
  "generacion_eolica",
  "generacion_cogeneracion",
];

/**
 * Rampa secuencial del mapa: un solo tono, de oscuro a luminoso.
 *
 * Invertida respecto a un tema claro. Sobre un fondo oscuro la magnitud se lee
 * en cuánta luz emite la zona, no en cuánta tinta lleva: el departamento que
 * más consume es el que más brilla.
 */
export const RAMPA_MAPA = [
  "#16261f",
  "#1b453a",
  "#1d6152",
  "#1c7d69",
  "#199a80",
  "#20c093",
  "#6fe0bd",
];

export const COLOR_SIN_DATO = "#1a231f";

/** Familias de modelos, para agrupar la comparación. */
export const FAMILIAS = {
  referencia: { etiqueta: "Referencia", color: COLOR.tinta3 },
  lineal: { etiqueta: "Lineal", color: COLOR.nina },
  arboles: { etiqueta: "Árboles", color: COLOR.observado },
  serie_temporal: { etiqueta: "Serie temporal", color: COLOR.pronostico },
  red_neuronal: { etiqueta: "Red neuronal", color: COLOR.tercero },
  otro: { etiqueta: "Otro", color: COLOR.lineaFuerte },
};

/** Tipografía de los ejes de todas las gráficas. */
export const EJE = {
  fontSize: 10,
  fontFamily: "IBM Plex Mono, monospace",
  fill: COLOR.tinta3,
};

/** Paleta para las series que el usuario elige libremente en el explorador. */
export const PALETA_SERIES = [
  COLOR.observado,
  COLOR.pronostico,
  COLOR.tercero,
  COLOR.nina,
  COLOR.lima,
  COLOR.tinta2,
];
