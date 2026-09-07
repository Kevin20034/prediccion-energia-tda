import { useCallback, useEffect, useMemo, useState } from "react";

import * as api from "./api";
import Acceso from "./componentes/Acceso";
import LogoTdeA from "./componentes/LogoTdeA";
import { Aviso, Cargando } from "./componentes/ui";
import Datos from "./secciones/Datos";
import Inicio from "./secciones/Inicio";
import Mapa from "./secciones/Mapa";
import Modelos from "./secciones/Modelos";
import Pronostico from "./secciones/Pronostico";

/**
 * Secciones de la aplicación y a quién se le muestran.
 *
 * `acceso` dice el nivel mínimo que hace falta para verla:
 *
 *   `todos`     — cualquiera que entre. Es la aplicación tal y como la usa
 *                 alguien que solo quiere saber cómo está el mercado.
 *   `operador`  — analistas y administrador: quienes ingieren datos y
 *                 disparan entrenamientos.
 *   `admin`     — solo el administrador. La comparación de modelos vive aquí
 *                 porque es una herramienta de diagnóstico interno: RMSE, MASE
 *                 e importancia de variables no le sirven a nadie más, y
 *                 mostrarlas invita a sacar conclusiones sin el contexto
 *                 metodológico que hay detrás.
 */
const SECCIONES = [
  { clave: "inicio", etiqueta: "Inicio", Componente: Inicio, acceso: "todos" },
  { clave: "mapa", etiqueta: "Mapa", Componente: Mapa, acceso: "todos" },
  { clave: "pronostico", etiqueta: "Detalle", Componente: Pronostico, acceso: "operador" },
  { clave: "datos", etiqueta: "Datos", Componente: Datos, acceso: "operador" },
  { clave: "modelos", etiqueta: "Modelos", Componente: Modelos, acceso: "admin" },
];

/** Por debajo de este nivel de embalse, la regla superior pasa a ámbar. */
const EMBALSE_BAJO = 45;

const INICIAL = "inicio";

/** Sección indicada en la URL, si el rol tiene acceso a ella. */
function seccionDeLaUrl(permitidas) {
  const clave = window.location.hash.replace(/^#/, "");
  return permitidas.includes(clave) ? clave : INICIAL;
}

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [arrancando, setArrancando] = useState(true);
  // La sección vive en el hash de la URL: así el tablero es enlazable, recargar
  // no devuelve al inicio y el botón "atrás" del navegador hace lo que se
  // espera en vez de sacar de la aplicación.
  const [seccion, setSeccion] = useState(INICIAL);
  const [aviso, setAviso] = useState(null);
  const [nivelEmbalse, setNivelEmbalse] = useState(null);

  const esAdmin = usuario?.rol === "ADMINISTRADOR";
  const puedeOperar = esAdmin || usuario?.rol === "ANALISTA";

  const visibles = useMemo(() => {
    const permitido = { todos: true, operador: puedeOperar, admin: esAdmin };
    return SECCIONES.filter((s) => permitido[s.acceso]);
  }, [puedeOperar, esAdmin]);
  const claves = useMemo(() => visibles.map((s) => s.clave), [visibles]);

  const alFallar = useCallback((error) => {
    if (error instanceof api.SesionExpirada) {
      setUsuario(null);
      return;
    }
    setAviso({
      tipo: error instanceof api.FaltaPaso ? "falta" : "error",
      texto: error.message,
    });
  }, []);

  const cargarSesion = useCallback(async () => {
    setUsuario(await api.perfil());
  }, []);

  // Sesión guardada: se intenta reanudar al abrir.
  useEffect(() => {
    if (!api.getToken()) {
      setArrancando(false);
      return;
    }
    cargarSesion()
      .catch(() => api.setToken(null))
      .finally(() => setArrancando(false));
  }, [cargarSesion]);

  // La sección del hash solo puede resolverse cuando ya se sabe el rol: hasta
  // entonces no se sabe qué secciones existen para este usuario.
  useEffect(() => {
    if (!usuario) return;
    setSeccion(seccionDeLaUrl(claves));
  }, [usuario, claves]);

  // El nivel de los embalses alimenta la regla bajo la barra. Se pide una sola
  // vez por sesión: es un estado diario, no cambia mientras se navega.
  //
  // Se piden los últimos diez días y se usa el último punto con dato. XM
  // publica la hidrología con algo de retraso, así que pedir un solo día
  // devuelve vacío con bastante frecuencia y la regla se quedaría sin llenar.
  useEffect(() => {
    if (!usuario) return;
    api
      .series({ variables: ["volumen_util_embalse"], resolucion: "dia", limite: 10 })
      .then((r) => {
        const puntos = r.series?.[0]?.puntos ?? [];
        const ultimo = [...puntos].reverse().find((p) => p.valor != null);
        if (ultimo) setNivelEmbalse(ultimo.valor);
      })
      .catch(() => setNivelEmbalse(null));
  }, [usuario]);

  // Navegación hacia atrás y adelante del navegador.
  useEffect(() => {
    const alCambiar = () => setSeccion(seccionDeLaUrl(claves));
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, [claves]);

  const irA = useCallback((clave) => {
    setSeccion(clave);
    setAviso(null);
    window.location.hash = clave;
    // Al cambiar de sección se vuelve arriba. Sin esto, saltar desde el pie de
    // una sección larga deja la siguiente empezada por la mitad.
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  function salir() {
    api.setToken(null);
    setUsuario(null);
    setAviso(null);
    setNivelEmbalse(null);
    irA(INICIAL);
  }

  if (arrancando) return <Cargando texto="conectando" />;
  if (!usuario) return <Acceso alEntrar={cargarSesion} />;

  const Actual = visibles.find((s) => s.clave === seccion)?.Componente ?? Inicio;
  const bajo = nivelEmbalse != null && nivelEmbalse < EMBALSE_BAJO;

  return (
    <>
      <header className="barra">
        <div className="barra__fila">
          {/* El logo dice de quién es esto mejor que cualquier texto; al lado,
              el nombre de la aplicación y nada más. Antes convivían aquí dos
              nombres ("SIN" y "Pronóstico energético") y ninguno era el de la
              aplicación. */}
          <LogoTdeA tamano="barra" />
          <span className="barra__marca">
            <i className="barra__pulso" aria-hidden="true" />
            Predicción Energía TdeA
          </span>

          <nav className="pestanas" aria-label="Secciones">
            {visibles.map((s) => (
              <button
                key={s.clave}
                className="pestana"
                aria-current={s.clave === seccion ? "page" : undefined}
                onClick={() => irA(s.clave)}
              >
                {s.etiqueta}
              </button>
            ))}
          </nav>

          <span className="hueco" />

          <span className="barra__usuario">
            <div className="rotulo">{usuario.rol}</div>
            <div className="barra__correo">{usuario.email}</div>
          </span>
          <button className="boton boton--fantasma" onClick={salir}>
            Salir
          </button>
        </div>

        {/* La regla bajo la barra ES el nivel de los embalses. No decora: en
            Colombia el nivel del agua es el contexto de cualquier cifra del
            mercado, así que está presente en todas las secciones. */}
        <div
          className="nivel"
          role="img"
          aria-label={
            nivelEmbalse == null
              ? "Nivel de embalses no disponible"
              : `Nivel de los embalses del sistema: ${nivelEmbalse.toFixed(1)} por ciento`
          }
          title={
            nivelEmbalse == null
              ? "Nivel de embalses no disponible"
              : `Embalses al ${nivelEmbalse.toFixed(1)} %`
          }
        >
          {nivelEmbalse != null && (
            <div
              className={`nivel__relleno${bajo ? " nivel__relleno--bajo" : ""}`}
              style={{ width: `${Math.min(100, Math.max(0, nivelEmbalse))}%` }}
            />
          )}
        </div>
      </header>

      <main className="lienzo">
        <Aviso aviso={aviso} alCerrar={() => setAviso(null)} />
        <Actual
          key={seccion}
          puedeOperar={puedeOperar}
          alFallar={alFallar}
          alAvisar={setAviso}
          alIrAlMapa={() => irA("mapa")}
        />
      </main>
    </>
  );
}
