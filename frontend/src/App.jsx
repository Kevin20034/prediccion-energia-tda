import { useCallback, useEffect, useState } from "react";

import * as api from "./api";
import Acceso from "./componentes/Acceso";
import Costura from "./componentes/Costura";
import GraficaCostura from "./componentes/GraficaCostura";
import PanelEstado from "./componentes/PanelEstado";
import TablaModelos from "./componentes/TablaModelos";
import { isoDia } from "./formato";

/**
 * Horas de histórico que se dibujan en la gráfica: una semana.
 *
 * Es una decisión de composición, no arbitraria. Con dos semanas, las 24 horas
 * predichas ocupaban un 7 % del ancho y la costura —el elemento central de la
 * pantalla— quedaba aplastada contra el borde. Con una semana ocupan el 12,5 %
 * y se leen, sin perder la estacionalidad semanal del precio.
 */
const VENTANA_HORAS = 168;

export default function App() {
  const [usuario, setUsuario] = useState(null);
  const [arrancando, setArrancando] = useState(true);

  const [resumen, setResumen] = useState(null);
  const [observado, setObservado] = useState([]);
  const [predicho, setPredicho] = useState([]);
  const [ejecuciones, setEjecuciones] = useState([]);

  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState(null);

  const puedeOperar = usuario?.rol === "ADMINISTRADOR" || usuario?.rol === "ANALISTA";

  /** Carga todo el estado del tablero. Tolera que alguna parte falle. */
  const cargar = useCallback(async () => {
    const [perfil, res, datos, preds, ejec] = await Promise.allSettled([
      api.perfil(),
      api.resumenDatos(),
      api.ultimosDatos(VENTANA_HORAS),
      api.listarPredicciones(48),
      api.historicoEntrenamientos(40),
    ]);

    if (perfil.status === "rejected") throw perfil.reason;
    setUsuario(perfil.value);

    if (res.status === "fulfilled") setResumen(res.value);
    if (ejec.status === "fulfilled") setEjecuciones(ejec.value);

    // La API devuelve lo más reciente primero; la gráfica necesita orden temporal.
    if (datos.status === "fulfilled") {
      setObservado([...datos.value].reverse());
    }

    if (preds.status === "fulfilled") {
      setPredicho(
        [...preds.value].sort(
          (a, b) => new Date(a.fecha_objetivo) - new Date(b.fecha_objetivo)
        )
      );
    }
  }, []);

  // Sesión guardada: se intenta reanudar al abrir.
  useEffect(() => {
    if (!api.getToken()) {
      setArrancando(false);
      return;
    }
    cargar()
      .catch(() => api.setToken(null))
      .finally(() => setArrancando(false));
  }, [cargar]);

  async function conManejo(accion, mensajeExito) {
    setOcupado(true);
    setAviso(null);
    try {
      const resultado = await accion();
      await cargar();
      setAviso({ tipo: "ok", texto: mensajeExito(resultado) });
    } catch (e) {
      if (e instanceof api.SesionExpirada) {
        setUsuario(null);
        return;
      }
      setAviso({ tipo: "error", texto: e.message });
    } finally {
      setOcupado(false);
    }
  }

  const predecir = () =>
    conManejo(
      () => api.generarPredicciones(24),
      (p) => `${p.length} predicciones generadas con ${p[0]?.nombre_modelo}.`
    );

  const ingerir = () =>
    conManejo(
      () => api.ingerir(isoDia(30), isoDia(0)),
      (r) => `${r.registros_descargados} registros procesados (${r.registros_insertados} nuevos).`
    );

  const entrenar = () =>
    conManejo(
      () => api.entrenar({ horizonte: 24, criterio: "rmse" }),
      (r) => `Entrenamiento completado. Mejor modelo: ${r.mejor_modelo}.`
    );

  function salir() {
    api.setToken(null);
    setUsuario(null);
    setResumen(null);
    setObservado([]);
    setPredicho([]);
    setEjecuciones([]);
    setAviso(null);
  }

  if (arrancando) return <div className="cargando">cargando</div>;
  if (!usuario) return <Acceso alEntrar={cargar} />;

  const ultimoDato = observado.at(-1) ?? null;

  /**
   * Solo se muestran las predicciones POSTERIORES al último dato observado.
   *
   * Sin este filtro, una predicción vieja (emitida hace meses, cuando el
   * histórico terminaba antes) se dibujaba junto a los datos recientes: el eje
   * temporal se estiraba para cubrir el hueco, la serie observada quedaba
   * aplastada contra el borde, y el porcentaje de variación comparaba dos
   * momentos sin relación entre sí.
   *
   * Las predicciones ya superadas por los datos no son pronóstico, son
   * historial: su sitio es la evaluación de error (`scripts/evaluar_produccion`),
   * no la gráfica de pronóstico.
   */
  const vigentes = ultimoDato
    ? predicho.filter(
        (p) => new Date(p.fecha_objetivo) > new Date(ultimoDato.fecha_hora)
      )
    : predicho;

  const prediccion24h = vigentes.at(-1) ?? null;
  const hayPrediccionesVencidas = predicho.length > 0 && vigentes.length === 0;

  return (
    <>
      <header className="barra">
        <span className="barra__marca">
          <i className="barra__pulso" aria-hidden="true" />
          Precio de bolsa
          <span className="barra__sitio">· Tecnológico de Antioquia</span>
        </span>

        <span className="barra__hueco" />

        <span className="barra__usuario">
          <div className="etiqueta">{usuario.rol}</div>
          <div className="barra__correo">{usuario.email}</div>
        </span>
        <button className="boton boton--fantasma" onClick={salir}>
          Salir
        </button>
      </header>

      <main className="lienzo">
        {aviso && (
          <div className={`mensaje mensaje--${aviso.tipo === "ok" ? "ok" : "error"}`}>
            {aviso.texto}
          </div>
        )}

        <section className="panel">
          <Costura
            ultimoDato={ultimoDato}
            prediccion24h={prediccion24h}
            nombreModelo={prediccion24h?.nombre_modelo}
            vencidas={hayPrediccionesVencidas}
          />
          {ocupado ? (
            <div className="cargando">procesando</div>
          ) : (
            <GraficaCostura observado={observado} predicho={vigentes} />
          )}
        </section>

        <div className="rejilla">
          <TablaModelos ejecuciones={ejecuciones} />
          <PanelEstado
            resumen={resumen}
            ultimoDato={ultimoDato}
            puedeOperar={puedeOperar}
            ocupado={ocupado}
            onPredecir={predecir}
            onIngerir={ingerir}
            onEntrenar={entrenar}
          />
        </div>
      </main>
    </>
  );
}
