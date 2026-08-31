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

export const cop = (valor) => (valor == null || Number.isNaN(valor) ? "—" : NUM.format(valor));

export const entero = (valor) => (valor == null ? "—" : ENTERO.format(valor));

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

export function hora(ms) {
  return new Date(ms).toLocaleString("es-CO", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    hour12: false,
    timeZone: ZONA,
  });
}

/** Fecha de hoy o de hace N días, en formato AAAA-MM-DD. */
export function isoDia(diasAtras = 0) {
  const d = new Date();
  d.setDate(d.getDate() - diasAtras);
  return d.toISOString().slice(0, 10);
}
