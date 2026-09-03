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
  papel: "#edf1f4",
  panel: "#ffffff",
  hundido: "#f4f7f9",
  linea: "#d3dde4",
  lineaFuerte: "#a9bcc8",

  tinta: "#0f2430",
  tinta2: "#4a6376",
  tinta3: "#6f8a9c",

  observado: "#009394",
  observadoHondo: "#00696a",
  observadoVelo: "#dcefef",
  pronostico: "#cc6a00",
  pronosticoHondo: "#8f4a00",
  pronosticoVelo: "#fbeeda",

  nino: "#a8123f",
  nina: "#1d4ed8",
};

/**
 * Paleta categórica de tecnologías de generación, en **orden fijo**.
 *
 * El color sigue a la entidad, nunca a su posición en el ranking: si un filtro
 * deja fuera la solar, la hidráulica no cambia de color. Por eso el mapa es
 * nombre -> color y no una lista que se recorre.
 *
 * Validada para separación por visión cromática (ΔE ≥ 8 en todos los pares,
 * protanopía y deuteranopía) sobre fondo blanco. El oro solar queda por debajo
 * de 3:1 de contraste, así que allí donde se usa lleva etiqueta visible; no se
 * distingue nunca solo por el color.
 */
export const TECNOLOGIAS = [
  { clave: "generacion_hidraulica", etiqueta: "Hidráulica", color: "#009394" },
  { clave: "generacion_termica", etiqueta: "Térmica", color: "#db6c00" },
  { clave: "generacion_solar", etiqueta: "Solar", color: "#d1ae00" },
  { clave: "generacion_otras", etiqueta: "Eólica y cogeneración", color: "#8b5cd6" },
];

/** Series que se suman en la categoría "otras" del gráfico de mezcla. */
export const OTRAS_TECNOLOGIAS = ["generacion_eolica", "generacion_cogeneracion"];

/**
 * Rampa secuencial del mapa: un solo tono, de claro a oscuro.
 *
 * Un solo tono porque lo que codifica es **magnitud**, y el ojo lee la
 * magnitud en la luminosidad. Una rampa de arcoíris introduce fronteras donde
 * los datos son continuos y no tiene un orden que nadie pueda leer sin leyenda.
 */
export const RAMPA_MAPA = [
  "#eef5f5",
  "#cbe6e5",
  "#97d2d0",
  "#5cb8b6",
  "#1f9b99",
  "#00787a",
  "#005457",
];

export const COLOR_SIN_DATO = "#e3e9ed";

/** Familias de modelos, para agrupar la comparación. */
export const FAMILIAS = {
  referencia: { etiqueta: "Referencia", color: COLOR.tinta3 },
  lineal: { etiqueta: "Lineal", color: "#5055d3" },
  arboles: { etiqueta: "Árboles", color: "#009394" },
  serie_temporal: { etiqueta: "Serie temporal", color: "#db6c00" },
  red_neuronal: { etiqueta: "Red neuronal", color: "#8b5cd6" },
  otro: { etiqueta: "Otro", color: COLOR.lineaFuerte },
};

/** Tipografía de los ejes de todas las gráficas. */
export const EJE = {
  fontSize: 10,
  fontFamily: "IBM Plex Mono, monospace",
  fill: COLOR.tinta3,
};
