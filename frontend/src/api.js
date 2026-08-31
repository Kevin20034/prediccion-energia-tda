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
    throw new Error(traducir(error.detail) || `Error ${respuesta.status}`);
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

// --- Autenticación ---------------------------------------------------------

export async function entrar(email, password) {
  // El endpoint espera form-data (contrato OAuth2), no JSON.
  const formulario = new URLSearchParams({ username: email, password });
  const datos = await pedir("/auth/login", { method: "POST", body: formulario });
  setToken(datos.access_token);
  return datos;
}

export const perfil = () => pedir("/auth/yo");

// --- Datos históricos ------------------------------------------------------

export const resumenDatos = () => pedir("/datos/resumen");

export const ultimosDatos = (limite = 336) => pedir(`/datos?limite=${limite}`);

export const ingerir = (inicio, fin) =>
  pedir(`/datos/ingestar?fecha_inicio=${inicio}&fecha_fin=${fin}`, { method: "POST" });

// --- Modelos ---------------------------------------------------------------

export const historicoEntrenamientos = (limite = 40) =>
  pedir(`/entrenamientos?limite=${limite}`);

export const entrenar = (cuerpo = {}) => pedir("/entrenar", { method: "POST", body: cuerpo });

// --- Predicciones ----------------------------------------------------------

export const listarPredicciones = (limite = 48) => pedir(`/predicciones?limite=${limite}`);

export const generarPredicciones = (horas = 24) =>
  pedir("/predicciones", { method: "POST", body: { horas, guardar: true } });

// --- Administración --------------------------------------------------------

export const listarUsuarios = () => pedir("/usuarios");
