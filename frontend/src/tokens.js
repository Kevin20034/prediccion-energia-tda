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

/**
 * Rampa divergente de la anomalía de temperatura.
 *
 * La anomalía no es una magnitud, es una desviación: tiene un cero con
 * significado —lo normal— y dos direcciones. La rampa secuencial de la demanda
 * la contaría mal, porque haría que "tres grados por debajo" y "lo normal" se
 * pintaran igual de apagados y solo destacara el calor.
 *
 * Frío y calor son azul y ámbar, no rojo y verde: el par rojo-verde es la
 * confusión cromática más común y borraría justo la distinción que este mapa
 * existe para mostrar. Validado con el comprobador de la guía de visualización:
 * cada mitad pasa como rampa de un solo tono (luminosidad monótona, saltos
 * visibles, contraste contra el fondo) y los dos polos se separan con ΔE 17,0
 * en protanopía, muy por encima del umbral de 8.
 *
 * La luminosidad crece hacia los extremos: sobre fondo oscuro, lo normal
 * retrocede y lo anómalo brilla, que es el orden de lectura que se busca.
 */
export const RAMPA_ANOMALIA = [
  "#9ad8f7", // −3 · mucho más frío de lo normal
  "#6fb8e4",
  "#4f93bd",
  "#5f6d66", // 0 · en su normal
  "#c2853f",
  "#e0a94f",
  "#f8cd76", // +3 · mucho más cálido de lo normal
];

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
