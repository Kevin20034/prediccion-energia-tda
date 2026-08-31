import { cop, entero, fecha } from "../formato";

/**
 * Estado del sistema y acciones del analista.
 *
 * Incluye el nivel de los embalses porque es el mecanismo económico central
 * del mercado colombiano: cuando el volumen útil baja, entra generación
 * térmica y el precio sube. No es un adorno, es la variable que explica la
 * gráfica de arriba.
 */
export default function PanelEstado({
  resumen,
  ultimoDato,
  puedeOperar,
  ocupado,
  onIngerir,
  onEntrenar,
  onPredecir,
}) {
  const embalse = ultimoDato?.volumen_util_embalse;
  const fenomeno = ultimoDato?.fenomeno_climatico || "NEUTRO";

  return (
    <section className="panel">
      <header className="panel__cabecera">
        <span className="etiqueta">Estado del sistema</span>
      </header>

      <div className="panel__cuerpo">
        <div className="lectura">
          <span className="etiqueta">Registros</span>
          <span className="lectura__valor">{entero(resumen?.total_registros)}</span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Desde</span>
          <span className="lectura__valor">{fecha(resumen?.fecha_minima)}</span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Hasta</span>
          <span className="lectura__valor">{fecha(resumen?.fecha_maxima)}</span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Precio medio</span>
          <span className="lectura__valor">{cop(resumen?.precio_medio)}</span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Máximo</span>
          <span className="lectura__valor" style={{ color: "var(--escasez)" }}>
            {cop(resumen?.precio_maximo)}
          </span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Fuente</span>
          <span className="lectura__valor">{ultimoDato?.fuente || "—"}</span>
        </div>
        <div className="lectura">
          <span className="etiqueta">Fenómeno</span>
          <span className={`enso enso--${claseEnso(fenomeno)}`}>{etiquetaEnso(fenomeno)}</span>
        </div>

        {embalse != null && (
          <div className="embalse">
            <div className="etiqueta">Volumen útil de embalses</div>
            <div className="embalse__barra">
              <div
                className={`embalse__nivel ${embalse < 40 ? "embalse__nivel--bajo" : ""}`}
                style={{ width: `${Math.min(100, Math.max(0, embalse))}%` }}
              />
            </div>
            <div className="embalse__pie">
              <span>{embalse.toFixed(1)} % de la capacidad</span>
              <span>{embalse < 40 ? "nivel bajo" : "nivel normal"}</span>
            </div>
          </div>
        )}

        <div className="acciones">
          <button
            className="boton boton--linea"
            onClick={onPredecir}
            disabled={ocupado || !resumen?.total_registros}
          >
            Predecir 24 horas
            <span className="boton__tecla">POST /predicciones</span>
          </button>

          <button
            className="boton boton--linea"
            onClick={onIngerir}
            disabled={ocupado || !puedeOperar}
            title={puedeOperar ? undefined : "Requiere rol Analista"}
          >
            Descargar datos
            <span className="boton__tecla">últimos 30 días</span>
          </button>

          <button
            className="boton boton--linea"
            onClick={onEntrenar}
            disabled={ocupado || !puedeOperar}
            title={puedeOperar ? undefined : "Requiere rol Analista"}
          >
            Entrenar modelos
            <span className="boton__tecla">~2 min</span>
          </button>

          {!puedeOperar && (
            <p className="acciones__nota">
              Tu rol permite consultar. Descargar datos y entrenar modelos requiere
              el rol Analista.
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

const claseEnso = (f) =>
  f === "EL_NINO" ? "nino" : f === "LA_NINA" ? "nina" : "neutro";

const etiquetaEnso = (f) =>
  f === "EL_NINO" ? "EL NIÑO" : f === "LA_NINA" ? "LA NIÑA" : "NEUTRO";
