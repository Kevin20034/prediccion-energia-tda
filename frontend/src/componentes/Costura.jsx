import { cop, fechaHora } from "../formato";

/**
 * Los dos números que resumen todo el trabajo de grado.
 *
 * A la izquierda, el último precio MEDIDO. A la derecha, el precio ESTIMADO
 * para dentro de 24 horas. Entre ellos, el eje del "ahora".
 *
 * El subrayado discontinuo bajo la cifra estimada y la trama diagonal de fondo
 * dicen lo mismo sin palabras: ese número no se midió, se infirió.
 */
export default function Costura({ ultimoDato, prediccion24h, nombreModelo, vencidas }) {
  const observado = ultimoDato?.precio_bolsa;
  const estimado = prediccion24h?.precio_estimado;

  const delta =
    observado != null && estimado != null && observado !== 0
      ? ((estimado - observado) / observado) * 100
      : null;

  return (
    <div className="costura">
      <div className="costura__lado">
        <div className="etiqueta">Último precio observado</div>
        <div className="costura__cifra costura__cifra--medida">
          {cop(observado)}
          <span className="costura__unidad">COP/kWh</span>
        </div>
        <div className="costura__pie">
          {ultimoDato ? fechaHora(ultimoDato.fecha_hora) : "sin datos"}
          {ultimoDato?.fuente && ` · ${ultimoDato.fuente}`}
        </div>
      </div>

      <div className="costura__eje" aria-hidden="true" />

      <div className="costura__lado costura__lado--futuro">
        <div className="etiqueta">Estimado a 24 horas</div>

        {estimado != null ? (
          <>
            <div>
              <span className="costura__cifra costura__cifra--inferida">
                {cop(estimado)}
                <span className="costura__unidad">COP/kWh</span>
              </span>
            </div>
            <div className="costura__pie">
              {fechaHora(prediccion24h.fecha_objetivo)}
              {delta != null && (
                <>
                  {" · "}
                  <span
                    className={`costura__delta ${
                      delta >= 0 ? "costura__delta--sube" : "costura__delta--baja"
                    }`}
                  >
                    {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} %
                  </span>
                </>
              )}
              {nombreModelo && ` · ${nombreModelo}`}
            </div>
          </>
        ) : (
          <p className="costura__vacio">
            {vencidas ? (
              <>
                Las predicciones guardadas ya quedaron atrás: los datos llegan
                más lejos que ellas. Genera una nueva con{" "}
                <b>Predecir 24 horas</b>.
              </>
            ) : (
              <>
                Aún no hay predicciones. Genera una con <b>Predecir 24 horas</b>.
              </>
            )}
          </p>
        )}
      </div>
    </div>
  );
}
