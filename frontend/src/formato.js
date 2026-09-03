/**
 * Formateo consistente de números y fechas en toda la interfaz.
 *
 * NOTA SOBRE LA ZONA HORARIA. Las marcas de tiempo de XM son hora local de
 * Colombia y todo el backend las trata como ingenuas (sin desfase): la limpieza
 * les quita explícitamente la zona. Al guardarse en una columna TIMESTAMPTZ,
 * PostgreSQL las etiqueta como UTC, así que la API devuelve "2024-01-01T00:00Z".
 *
 * Si el navegador las convirtiera a hora local (UTC−5 en Colombia), mostraría
 * "31 dic 2023, 19:00" para un dato que XM publicó como "1 ene 2024, 00:00".
 * Por eso TODO se formatea en UTC: así se devuelve en pantalla exactamente el
 * reloj que publicó XM, sin desplazamientos falsos.
 */

const ZONA = "UTC";

const NUM = new Intl.NumberFormat("es-CO", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const ENTERO = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });

const nulo = (valor) => valor == null || Number.isNaN(valor);

export const cop = (valor) => (nulo(valor) ? "—" : NUM.format(valor));

export const entero = (valor) => (nulo(valor) ? "—" : ENTERO.format(valor));

export const decimales = (valor, n = 2) =>
  nulo(valor)
    ? "—"
    : new Intl.NumberFormat("es-CO", {
        minimumFractionDigits: n,
        maximumFractionDigits: n,
      }).format(valor);

export const porcentaje = (valor, n = 1) => (nulo(valor) ? "—" : `${decimales(valor, n)} %`);

export const signo = (valor, n = 1) =>
  nulo(valor) ? "—" : `${valor > 0 ? "+" : ""}${decimales(valor, n)} %`;

/**
 * Convierte kWh a la unidad legible más cercana.
 *
 * La demanda horaria nacional ronda los 8·10⁶ kWh: mostrarla en kWh son ocho
 * cifras que nadie compara de un vistazo. Se escala a MWh, GWh o TWh según la
 * magnitud, y se devuelve también la unidad para que la etiqueta nunca se
 * desincronice del número.
 */
export function energia(kwh, decimalesFijos = 1) {
  if (nulo(kwh)) return { valor: "—", unidad: "kWh" };
  const abs = Math.abs(kwh);
  if (abs >= 1e9) return { valor: decimales(kwh / 1e9, decimalesFijos), unidad: "TWh" };
  if (abs >= 1e6) return { valor: decimales(kwh / 1e6, decimalesFijos), unidad: "GWh" };
  if (abs >= 1e3) return { valor: decimales(kwh / 1e3, decimalesFijos), unidad: "MWh" };
  return { valor: decimales(kwh, decimalesFijos), unidad: "kWh" };
}

/** Escala un valor a la unidad de presentación declarada en el catálogo. */
export const escalar = (valor, escala = 1) => (nulo(valor) ? null : valor / escala);

export function fechaHora(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("es-CO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: ZONA,
  });
}

export function fecha(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-CO", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: ZONA,
  });
}

export function mesAnio(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("es-CO", {
    month: "short",
    year: "2-digit",
    timeZone: ZONA,
  });
}

/** Etiqueta del eje temporal, ajustada a la resolución que se está mostrando. */
export function marcaTemporal(ms, resolucion = "hora") {
  const d = new Date(ms);
  if (resolucion === "mes") return mesAnio(d);
  if (resolucion === "semana" || resolucion === "dia") {
    return d.toLocaleDateString("es-CO", {
      day: "2-digit",
      month: "short",
      timeZone: ZONA,
    });
  }
  return d.toLocaleString("es-CO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    hour12: false,
    timeZone: ZONA,
  });
}

export const hora = (ms) => marcaTemporal(ms, "hora");

/** Fecha de hoy o de hace N días, en formato AAAA-MM-DD. */
export function isoDia(diasAtras = 0) {
  const d = new Date();
  d.setDate(d.getDate() - diasAtras);
  return d.toISOString().slice(0, 10);
}
