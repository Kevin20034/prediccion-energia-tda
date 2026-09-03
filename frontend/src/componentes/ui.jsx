/**
 * Piezas compartidas de la interfaz.
 *
 * Viven en un solo archivo a propósito: son componentes de pocas líneas cuyo
 * valor está en usarse igual en todas partes. Repartirlos en siete archivos
 * haría más difícil comprobar de un vistazo que lo son.
 */

export function Panel({ titulo, rotulo, acciones, pie, ajustado = false, children }) {
  return (
    <section className="panel">
      {(titulo || acciones) && (
        <header className="panel__cabecera">
          <div>
            {rotulo && <div className="rotulo">{rotulo}</div>}
            {titulo && <h2 className="panel__titulo">{titulo}</h2>}
          </div>
          {acciones}
        </header>
      )}
      <div className={`panel__cuerpo${ajustado ? " panel__cuerpo--ajustado" : ""}`}>
        {children}
      </div>
      {pie && <footer className="panel__pie">{pie}</footer>}
    </section>
  );
}

/**
 * Una cifra destacada.
 *
 * `naturaleza` no es un color: dice si el número fue medido por XM o inferido
 * por un modelo. Toda la interfaz mantiene esa distinción, porque confundir
 * ambas cosas es el error que un tablero de pronóstico no puede permitirse.
 */
export function Cifra({ rotulo, valor, unidad, pie, naturaleza = "neutra", children }) {
  return (
    <div className={`cifra cifra--${naturaleza}`}>
      <div className="rotulo">{rotulo}</div>
      <div className="cifra__valor">
        {valor}
        {unidad && <span className="cifra__unidad">{unidad}</span>}
      </div>
      {pie && <div className="cifra__pie">{pie}</div>}
      {children}
    </div>
  );
}

/** Variación porcentual con signo y color según la dirección. */
export function Delta({ valor, sufijo = "vs. periodo anterior" }) {
  if (valor == null || Number.isNaN(valor)) return null;
  const sube = valor > 0;
  return (
    <>
      <span className={`delta delta--${sube ? "sube" : "baja"}`}>
        {sube ? "▲" : "▼"} {Math.abs(valor).toFixed(1)} %
      </span>
      <span>{sufijo}</span>
    </>
  );
}

/** Grupo de opciones excluyentes. */
export function Conmutador({ opciones, valor, alCambiar, etiqueta }) {
  return (
    <div className="conmutador" role="group" aria-label={etiqueta}>
      {opciones.map((opcion) => (
        <button
          key={opcion.valor}
          type="button"
          className="conmutador__opcion"
          aria-pressed={opcion.valor === valor}
          disabled={opcion.deshabilitada}
          title={opcion.ayuda}
          onClick={() => alCambiar(opcion.valor)}
        >
          {opcion.etiqueta}
        </button>
      ))}
    </div>
  );
}

export function Aviso({ aviso, alCerrar }) {
  if (!aviso) return null;
  return (
    <div
      className={`aviso aviso--${aviso.tipo}`}
      role={aviso.tipo === "error" ? "alert" : "status"}
      style={{ marginBottom: 16 }}
    >
      <span>{aviso.texto}</span>
      {alCerrar && (
        <button className="aviso__cerrar" onClick={alCerrar} aria-label="Cerrar aviso">
          ×
        </button>
      )}
    </div>
  );
}

export function Cargando({ texto = "cargando" }) {
  return (
    <div className="cargando" role="status">
      {texto}
    </div>
  );
}

/**
 * Estado vacío.
 *
 * Una pantalla vacía es una invitación a actuar, no un mensaje de error: dice
 * qué falta y ofrece el botón que lo resuelve.
 */
export function Vacio({ titulo, texto, accion }) {
  return (
    <div className="vacio">
      <p className="vacio__titulo">{titulo}</p>
      <p className="vacio__texto">{texto}</p>
      {accion}
    </div>
  );
}

/** Marca de procedencia del dato: medido por XM o estimado por reparto. */
export function Procedencia({ estimado, detalle }) {
  return (
    <span
      className={`insignia insignia--${estimado ? "estimada" : "medida"}`}
      title={detalle}
    >
      {estimado ? "estimado" : "medido"}
    </span>
  );
}

/** Bloque de conclusión en prosa. */
export function Veredicto({ texto, sinVentaja = false }) {
  return (
    <p className={`veredicto${sinVentaja ? " veredicto--sin-ventaja" : ""}`}>{texto}</p>
  );
}
