import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import * as api from "../api";
import Costura from "../componentes/Costura";
import GraficaMezcla from "../componentes/graficas/GraficaMezcla";
import GraficaPerfil from "../componentes/graficas/GraficaPerfil";
import GraficaPronostico from "../componentes/graficas/GraficaPronostico";
import Herramientas from "../componentes/graficas/Herramientas";
import { Cargando, Cifra, Conmutador, Panel, Vacio } from "../componentes/ui";
import { decimales, fechaHora } from "../formato";

const OBJETIVOS = [
  { valor: "precio_bolsa", etiqueta: "Precio de bolsa" },
  { valor: "demanda_real", etiqueta: "Demanda" },
];

const HORIZONTES = [
  { valor: 24, etiqueta: "24 horas", texto: "24 h" },
  { valor: 168, etiqueta: "7 días", texto: "7 d" },
  { valor: 720, etiqueta: "30 días", texto: "30 d" },
];

/** Columnas del CSV que acompaña a la gráfica. */
const COLUMNAS_CSV = [
  { titulo: "fecha", valor: (f) => f.fecha },
  { titulo: "tipo", valor: (f) => f.tipo },
  { titulo: "valor", valor: (f) => f.valor },
  { titulo: "minimo", valor: (f) => f.minimo ?? "" },
  { titulo: "maximo", valor: (f) => f.maximo ?? "" },
];

/** Variables de generación que alimentan la gráfica de mezcla. */
const VARIABLES_MEZCLA = [
  "generacion_hidraulica",
  "generacion_termica",
  "generacion_solar",
  "generacion_eolica",
  "generacion_cogeneracion",
];

export default function Pronostico({ puedeOperar, alFallar, alAvisar }) {
  const [objetivo, setObjetivo] = useState("precio_bolsa");
  const [horizonte, setHorizonte] = useState(24);
  const [forma, setForma] = useState("linea");
  const contenedorGrafica = useRef(null);

  const [datos, setDatos] = useState(null);
  const [disponibles, setDisponibles] = useState([]);
  const [mezcla, setMezcla] = useState([]);
  const [perfil, setPerfil] = useState(null);

  const [cargando, setCargando] = useState(true);
  const [faltaModelo, setFaltaModelo] = useState(null);

  // Qué combinaciones tienen modelo entrenado. Se consulta una vez: sirve para
  // deshabilitar las pestañas en vez de ofrecerlas y fallar al pulsarlas.
  useEffect(() => {
    api
      .horizontesDisponibles()
      .then((r) => setDisponibles(r.disponibles ?? []))
      .catch(() => setDisponibles([]));
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setFaltaModelo(null);
    try {
      const respuesta = await api.pronostico({ objetivo, horizonte });
      setDatos(respuesta);
    } catch (error) {
      setDatos(null);
      if (error instanceof api.FaltaPaso) setFaltaModelo(error.message);
      else alFallar(error);
    } finally {
      setCargando(false);
    }
  }, [objetivo, horizonte, alFallar]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // El contexto de generación y el perfil horario no dependen del horizonte, así
  // que no se vuelven a pedir al cambiar de pestaña.
  useEffect(() => {
    api
      .series({ variables: VARIABLES_MEZCLA, resolucion: "dia", limite: 180 })
      .then((r) => setMezcla(fundir(r)))
      .catch(() => setMezcla([]));
  }, []);

  useEffect(() => {
    api
      .perfilHorario(objetivo, 90)
      .then(setPerfil)
      .catch(() => setPerfil(null));
  }, [objetivo]);

  const combinacionesConModelo = useMemo(
    () => new Set(disponibles.map((d) => `${d.objetivo}|${d.horizonte}`)),
    [disponibles]
  );

  // Observado y pronosticado en una sola tabla: quien abra el CSV tiene que
  // poder rehacer la gráfica entera, no solo la parte medida.
  const filasCSV = useMemo(
    () => [
      ...(datos?.observado ?? []).map((p) => ({
        fecha: p.fecha_hora,
        tipo: "observado",
        valor: p.valor,
      })),
      ...(datos?.pronostico ?? []).map((p) => ({
        fecha: p.fecha_objetivo,
        tipo: "pronosticado",
        valor: p.valor_estimado,
        minimo: p.limite_inferior,
        maximo: p.limite_superior,
      })),
    ],
    [datos]
  );

  const ultimoObservado = datos?.observado?.at(-1) ?? null;
  const ultimoPronostico = datos?.pronostico?.at(-1) ?? null;
  const etiquetaHorizonte =
    HORIZONTES.find((h) => h.valor === horizonte)?.etiqueta ?? `${horizonte} h`;
  const esPrecio = objetivo === "precio_bolsa";

  return (
    <div className="seccion">
      <header className="seccion__cabecera">
        <div>
          <div className="rotulo">Sistema Interconectado Nacional</div>
          <h1 className="seccion__titulo">Pronóstico</h1>
          <p className="seccion__nota">
            Cada horizonte tiene su propio modelo entrenado. La banda sombreada cubre el
            80 % central del error observado en el conjunto de prueba: es hasta dónde
            este modelo se ha equivocado antes.
          </p>
        </div>

        <div className="fila">
          <Conmutador
            etiqueta="Variable a pronosticar"
            opciones={OBJETIVOS}
            valor={objetivo}
            alCambiar={setObjetivo}
          />
          <Conmutador
            etiqueta="Horizonte"
            opciones={HORIZONTES.map((h) => ({
              ...h,
              deshabilitada:
                combinacionesConModelo.size > 0 &&
                !combinacionesConModelo.has(`${objetivo}|${h.valor}`),
              ayuda:
                combinacionesConModelo.size > 0 &&
                !combinacionesConModelo.has(`${objetivo}|${h.valor}`)
                  ? "Todavía no hay modelo entrenado para este horizonte"
                  : undefined,
            }))}
            valor={horizonte}
            alCambiar={setHorizonte}
          />
        </div>
      </header>

      <Panel>
        {faltaModelo ? (
          <Vacio
            titulo={`Sin modelo para ${etiquetaHorizonte}`}
            texto={
              puedeOperar
                ? `${faltaModelo} Entrena este horizonte desde la sección Modelos y vuelve aquí.`
                : faltaModelo
            }
          />
        ) : (
          <>
            <Costura
              observado={ultimoObservado}
              pronostico={ultimoPronostico}
              unidad={datos?.unidad ?? ""}
              etiquetaHorizonte={etiquetaHorizonte}
              nombreModelo={datos?.nombre_modelo}
            />
            {cargando ? (
              <Cargando texto="calculando pronóstico" />
            ) : (
              <>
                <div ref={contenedorGrafica}>
                  <GraficaPronostico
                    observado={datos?.observado ?? []}
                    pronostico={datos?.pronostico ?? []}
                    unidad={datos?.unidad ?? ""}
                    forma={forma}
                    conBrush
                  />
                </div>
                <Herramientas
                  forma={forma}
                  alCambiarForma={setForma}
                  contenedor={contenedorGrafica}
                  nombre={`${objetivo}-${horizonte}h`}
                  tituloInforme={`Pronóstico ${objetivo} ${horizonte}h · Predicción Energía TdeA`}
                  datosCSV={filasCSV}
                  columnasCSV={COLUMNAS_CSV}
                  alFallar={alAvisar}
                />
              </>
            )}
          </>
        )}
      </Panel>

      {datos && (
        <div className="rejilla rejilla--cifras separado">
          <Cifra
            rotulo="Modelo en uso"
            valor={datos.nombre_modelo ?? "—"}
            naturaleza="inferida"
            pie={
              datos.entrenado_en ? `entrenado el ${fechaHora(datos.entrenado_en)}` : null
            }
          />
          <Cifra
            rotulo="Error típico (RMSE)"
            valor={decimales(datos.metricas?.rmse, 1)}
            unidad={datos.unidad}
            naturaleza="inferida"
            pie={`MAE ${decimales(datos.metricas?.mae, 1)} · MAPE ${decimales(
              datos.metricas?.mape,
              1
            )} %`}
          />
          <Cifra
            rotulo="Frente al pronóstico ingenuo"
            valor={decimales(datos.metricas?.mase, 3)}
            naturaleza="inferida"
            pie={
              datos.metricas?.mase == null
                ? null
                : datos.metricas.mase < 1
                  ? "MASE < 1: aporta sobre repetir el pasado"
                  : "MASE ≥ 1: no aporta sobre repetir el pasado"
            }
          />
          <Cifra
            rotulo="Horas pronosticadas"
            valor={datos.pronostico?.length ?? 0}
            naturaleza="inferida"
            pie={datos.corte ? `desde ${fechaHora(datos.corte)}` : null}
          />
        </div>
      )}

      <div className="rejilla rejilla--mitad separado">
        <Panel
          rotulo="Contexto"
          titulo="Mezcla de generación"
          ajustado
          pie="La participación hidráulica es el factor estructural del precio en Colombia: cuando el agua cede terreno a la generación térmica, el precio de bolsa sube."
        >
          <GraficaMezcla datos={mezcla} resolucion="dia" />
        </Panel>

        <Panel
          rotulo="Contexto"
          titulo={`Curva ${esPrecio ? "de precio" : "de carga"} por hora del día`}
          ajustado
          pie="Media de los últimos 90 días. El contraste entre laborables y fines de semana muestra cuánto del pico lo pone la actividad económica."
        >
          <GraficaPerfil
            perfil={perfil?.perfil ?? []}
            unidad={esPrecio ? "COP/kWh" : "GWh"}
            escala={esPrecio ? 1 : 1e6}
          />
        </Panel>
      </div>
    </div>
  );
}

/** Convierte la respuesta de `/datos/series` en una fila por instante. */
function fundir(respuesta) {
  const filas = new Map();
  for (const serie of respuesta?.series ?? []) {
    for (const punto of serie.puntos) {
      const clave = punto.fecha_hora;
      if (!filas.has(clave)) filas.set(clave, { fecha_hora: clave });
      filas.get(clave)[serie.variable] = punto.valor;
    }
  }
  return [...filas.values()];
}
