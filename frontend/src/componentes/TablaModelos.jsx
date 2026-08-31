import { cop, fechaHora } from "../formato";

const NOMBRES = {
  regresion_lineal: "Regresión lineal",
  random_forest: "Random Forest",
  xgboost: "XGBoost",
  lstm: "LSTM",
};

/**
 * Comparación de modelos: la tabla que responde la pregunta central del
 * trabajo de grado. Se muestra el último entrenamiento de cada modelo,
 * ordenado por RMSE (el criterio de selección del backend).
 */
export default function TablaModelos({ ejecuciones }) {
  const ultimas = ultimaPorModelo(ejecuciones);

  return (
    <section className="panel">
      <header className="panel__cabecera">
        <span className="etiqueta">Modelos evaluados</span>
        {ultimas.length > 0 && (
          <span className="etiqueta" style={{ letterSpacing: "0.06em" }}>
            {fechaHora(ultimas[0].ejecutado_en)}
          </span>
        )}
      </header>

      {ultimas.length === 0 ? (
        <p className="tabla__vacia">
          Todavía no se ha entrenado ningún modelo.
          <br />
          Usa <b>Entrenar modelos</b> para generar la comparación.
        </p>
      ) : (
        <table className="tabla">
          <thead>
            <tr>
              <th>Modelo</th>
              <th>MAE</th>
              <th>RMSE</th>
              <th>MAPE</th>
              <th>R²</th>
              <th>Seg.</th>
            </tr>
          </thead>
          <tbody>
            {ultimas.map((e) => (
              <tr key={e.id} className={e.es_mejor ? "tabla__fila--gana" : undefined}>
                <td className="tabla__nombre">
                  {e.es_mejor && (
                    <span className="tabla__marca" title="Menor RMSE">
                      ▸
                    </span>
                  )}
                  {NOMBRES[e.nombre_modelo] || e.nombre_modelo}
                </td>
                <td>{cop(e.mae)}</td>
                <td style={{ fontWeight: e.es_mejor ? 600 : 400 }}>{cop(e.rmse)}</td>
                <td>{cop(e.mape)}%</td>
                <td>{e.r2?.toFixed(3) ?? "—"}</td>
                <td style={{ color: "var(--tinta-tenue)" }}>
                  {e.duracion_segundos?.toFixed(1) ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {ultimas.length > 0 && (
        <p
          className="acciones__nota"
          style={{ padding: "10px 16px 14px", borderTop: "1px solid var(--hairline)", margin: 0 }}
        >
          MAE y RMSE en COP/kWh. Gana el menor RMSE: penaliza más los errores
          grandes, que en un mercado energético son los que cuestan.
        </p>
      )}
    </section>
  );
}

/** Se queda con la ejecución más reciente de cada modelo, ordenada por RMSE. */
function ultimaPorModelo(ejecuciones) {
  const vistos = new Map();
  for (const e of ejecuciones) {
    if (!vistos.has(e.nombre_modelo)) vistos.set(e.nombre_modelo, e);
  }
  return [...vistos.values()].sort((a, b) => a.rmse - b.rmse);
}
