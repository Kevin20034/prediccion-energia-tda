/**
 * Cliente HTTP de la API.
 *
 * Todas las rutas empiezan por /api, que Vite reenvía al backend (ver
 * vite.config.js). El navegador solo habla con un origen, así que CORS no
 * interviene ni en desarrollo ni detrás de un reverse proxy en producción.
 */

const BASE = "/api";
const CLAVE_TOKEN = "energia_tda_token";

let token = localStorage.getItem(CLAVE_TOKEN) || null;

export function getToken() {
  return token;
}

export function setToken(nuevo) {
  token = nuevo;
  if (nuevo) localStorage.setItem(CLAVE_TOKEN, nuevo);
  else localStorage.removeItem(CLAVE_TOKEN);
}

/** Se lanza cuando el token caducó o es inválido: obliga a volver al acceso. */
export class SesionExpirada extends Error {}

/** Se lanza cuando falta un paso previo (ingesta, entrenamiento). */
export class FaltaPaso extends Error {}

async function pedir(ruta, opciones = {}) {
  const cabeceras = { ...(opciones.headers || {}) };
  if (token) cabeceras.Authorization = `Bearer ${token}`;

  let cuerpo = opciones.body;
  if (cuerpo && !(cuerpo instanceof URLSearchParams)) {
    cabeceras["Content-Type"] = "application/json";
    cuerpo = JSON.stringify(cuerpo);
  }

  const respuesta = await fetch(`${BASE}${ruta}`, { ...opciones, headers: cabeceras, body: cuerpo });

  if (respuesta.status === 401) {
    setToken(null);
    throw new SesionExpirada("La sesión caducó. Vuelve a entrar.");
  }

  if (!respuesta.ok) {
    const error = await respuesta.json().catch(() => ({}));
    const mensaje = traducir(error.detail) || `Error ${respuesta.status}`;
    // Un 409 significa "falta un paso previo", no "algo se rompió". La interfaz
    // lo distingue para poder proponer la acción que desbloquea, en vez de
    // mostrar un error rojo genérico.
    throw respuesta.status === 409 ? new FaltaPaso(mensaje) : new Error(mensaje);
  }

  return respuesta.status === 204 ? null : respuesta.json();
}

/** La API puede devolver `detail` como texto o como lista de errores de Pydantic. */
function traducir(detalle) {
  if (!detalle) return null;
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) return detalle.map((e) => e.msg || String(e)).join(" · ");
  return String(detalle);
}

const query = (parametros) => {
  const p = new URLSearchParams();
  for (const [clave, valor] of Object.entries(parametros)) {
    if (valor === undefined || valor === null) continue;
    if (Array.isArray(valor)) valor.forEach((v) => p.append(clave, v));
    else p.append(clave, valor);
  }
  const texto = p.toString();
  return texto ? `?${texto}` : "";
};

// --- Autenticación ---------------------------------------------------------

export async function entrar(email, password) {
  // El endpoint espera form-data (contrato OAuth2), no JSON.
  const formulario = new URLSearchParams({ username: email, password });
  const datos = await pedir("/auth/login", { method: "POST", body: formulario });
  setToken(datos.access_token);
  return datos;
}

export const perfil = () => pedir("/auth/yo");

// --- Vista de usuario ------------------------------------------------------

/** Estado del sistema ya interpretado: titular, cifras, mezcla y territorio. */
export const panorama = (objetivo = "precio_bolsa") =>
  pedir(`/panorama${query({ objetivo })}`);

// --- Datos históricos ------------------------------------------------------

export const resumenDatos = () => pedir("/datos/resumen");

/** Frescura de cada fuente y estado de la ingesta automática. */
export const estadoDatos = () => pedir("/estado-datos");

export const catalogoVariables = () => pedir("/datos/catalogo");

export const ultimosDatos = (limite = 336) => pedir(`/datos${query({ limite })}`);

export const series = ({ variables, desde, hasta, resolucion = "hora", limite = 2000 }) =>
  pedir(`/datos/series${query({ variables, desde, hasta, resolucion, limite })}`);

export const perfilHorario = (variable = "demanda_real", dias = 90) =>
  pedir(`/datos/perfil-horario${query({ variable, dias })}`);

export const ingerir = (fecha_inicio, fecha_fin) =>
  pedir(`/datos/ingestar${query({ fecha_inicio, fecha_fin })}`, { method: "POST" });

// --- Territorio ------------------------------------------------------------

export const mapaDepartamentos = (horas = 24) =>
  pedir(`/departamentos/mapa${query({ horas })}`);

export const serieDepartamento = (codigo, resolucion = "dia", limite = 180) =>
  pedir(`/departamentos/${codigo}/serie${query({ resolucion, limite })}`);

export const ingerirDepartamentos = (fecha_inicio, fecha_fin) =>
  pedir(`/departamentos/ingestar${query({ fecha_inicio, fecha_fin })}`, { method: "POST" });

export const escenariosUpme = () => pedir("/upme/escenarios");

// --- Fenómeno del Niño ------------------------------------------------------

export const ninoEstado = () => pedir("/nino/estado");

export const ninoMapa = (horas = 24) => pedir(`/nino/mapa${query({ horas })}`);

export const ninoEfecto = () => pedir("/nino/efecto");

// --- Modelos ---------------------------------------------------------------

export const historicoEntrenamientos = (parametros = {}) =>
  pedir(`/entrenamientos${query({ limite: 200, ...parametros })}`);

export const comparacionModelos = (objetivo) =>
  pedir(`/modelos/comparacion${query({ objetivo })}`);

export const entrenar = (cuerpo = {}) => pedir("/entrenar", { method: "POST", body: cuerpo });

// --- Pronóstico ------------------------------------------------------------

export const pronostico = ({ objetivo = "precio_bolsa", horizonte = 24, recalcular = false }) =>
  pedir(`/pronostico${query({ objetivo, horizonte, recalcular })}`);

export const horizontesDisponibles = () => pedir("/pronostico/horizontes");

export const generarPredicciones = (objetivo = "precio_bolsa", horizonte = 24) =>
  pedir("/predicciones", {
    method: "POST",
    body: { objetivo, horizonte, guardar: true },
  });

// --- Administración --------------------------------------------------------

export const listarUsuarios = () => pedir("/usuarios");
