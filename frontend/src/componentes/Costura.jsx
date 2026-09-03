import { decimales, fechaHora } from "../formato";

/**
 * Los dos números que resumen la pantalla, con el eje "ahora" entre ellos.
 *
 * A la izquierda, lo último que XM midió. A la derecha, lo que el modelo cree
 * que pasará al final del horizonte. El eje central marca la frontera entre
 * ambos, y el lado derecho lleva una trama diagonal porque esa región no está
 * medida. La cifra inferida va subrayada con línea discontinua: nunca se
 * presenta con el mismo aplomo tipográfico que un dato real.
 */
export default function Costura({
  observado,
  pronostico,
  unidad,
  etiquetaHorizonte,
  nombreModelo,
}) {
  const medido = observado?.valor;
  const estimado = pronostico?.valor_estimado;

  const variacion =
    medido != null && estimado != null && medido !== 0
      ? ((estimado - medido) / Math.abs(medido)) * 100
      : null;

  return (
    <div className="costura">
      <div className="costura__lado">
        <div className="rotulo">Último dato medido</div>
        <div className="costura__cifra costura__cifra--medida">
          {decimales(medido, 1)}
          <span className="cifra__unidad">{unidad}</span>
        </div>
        <div className="costura__banda">
          {observado ? fechaHora(observado.fecha_hora) : "sin datos"}
        </div>
      </div>

      <div className="costura__eje" aria-hidden="true" />

      <div className="costura__lado costura__lado--futuro">
        <div className="rotulo">Pronóstico a {etiquetaHorizonte}</div>

        {estimado == null ? (
          <p className="costura__vacio">
            Todavía no hay pronóstico para este horizonte. Entrena el modelo desde la
            sección Modelos.
          </p>
        ) : (
          <>
            <div className="costura__cifra costura__cifra--inferida">
              {decimales(estimado, 1)}
              <span className="cifra__unidad">{unidad}</span>
            </div>
            <div className="costura__banda">
              {variacion != null && (
                <>
                  <span
                    className={`delta delta--${variacion > 0 ? "sube" : "baja"}`}
                  >
                    {variacion > 0 ? "▲" : "▼"} {Math.abs(variacion).toFixed(1)} %
                  </span>{" "}
                  frente al último dato ·{" "}
                </>
              )}
              {nombreModelo}
            </div>
            {pronostico.limite_inferior != null && (
              <div className="costura__banda">
                banda 80 %: {decimales(pronostico.limite_inferior, 0)} –{" "}
                {decimales(pronostico.limite_superior, 0)} {unidad}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
