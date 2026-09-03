import { useCallback, useEffect, useState } from "react";

import * as api from "./api";
import Acceso from "./componentes/Acceso";
import { Aviso, Cargando } from "./componentes/ui";
import Datos from "./secciones/Datos";
import Mapa from "./secciones/Mapa";
import Modelos from "./secciones/Modelos";
import Pronostico from "./secciones/Pronostico";

const SECCIONES = [
  { clave: "pronostico", etiqueta: "Pronóstico", Componente: Pronostico },
  { clave: "mapa", etiqueta: "Mapa", Componente: Mapa },
  { clave: "modelos", etiqueta: "Modelos", Componente: Modelos },
  { clave: "datos", etiqueta: "Datos", Componente: Datos },
];

/** Por debajo de este nivel de embalse, la regla superior pasa a ámbar. */
const EMBALSE_BAJO = 45;

const CLAVES = SECCIONES.map((s) => s.clave);

/** Sección indicada en la URL, o la primera si no hay ninguna válida. */
function seccionDeLaUrl() {
  const clave = window.location.hash.replace(/^#/, "");
  return CLAVES.includes(clave) ? clave : "pronostico";
}

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [arrancando, setArrancando] = useState(true);
  // La sección vive en el hash de la URL: así el tablero es enlazable, recargar
  // no devuelve al inicio y el botón "atrás" del navegador hace lo que se
  // espera en vez de sacar de la aplicación.
  const [seccion, setSeccion] = useState(seccionDeLaUrl);
  const [aviso, setAviso] = useState(null);
  const [nivelEmbalse, setNivelEmbalse] = useState(null);

  const puedeOperar = usuario?.rol === "ADMINISTRADOR" || usuario?.rol === "ANALISTA";

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
    const alCambiar = () => setSeccion(seccionDeLaUrl());
    window.addEventListener("hashchange", alCambiar);
    return () => window.removeEventListener("hashchange", alCambiar);
  }, []);

  function irA(clave) {
    setSeccion(clave);
    setAviso(null);
    window.location.hash = clave;
  }

  function salir() {
    api.setToken(null);
    setUsuario(null);
    setAviso(null);
    setNivelEmbalse(null);
    irA("pronostico");
  }

  if (arrancando) return <Cargando texto="conectando" />;
  if (!usuario) return <Acceso alEntrar={cargarSesion} />;

  const Actual = SECCIONES.find((s) => s.clave === seccion)?.Componente ?? Pronostico;
  const bajo = nivelEmbalse != null && nivelEmbalse < EMBALSE_BAJO;

  return (
    <>
      <header className="barra">
        <div className="barra__fila">
          <span className="barra__marca">
            <i className="barra__pulso" aria-hidden="true" />
            SIN
            <span className="barra__sitio">· Tecnológico de Antioquia</span>
          </span>

          <nav className="pestanas" aria-label="Secciones">
            {SECCIONES.map((s) => (
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
        />
      </main>
    </>
  );
}
