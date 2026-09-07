/**
 * Cuánto de viejo es lo que se está mirando.
 *
 * Muestra **dos relojes distintos y nunca fundidos en uno**:
 *
 *   «XM hasta el 31 de ago, 23:00»  → hasta dónde llega el dato publicado
 *   «revisado hace 4 min»           → cuándo se comprobó si había algo nuevo
 *
 * Fundirlos en un solo «actualizado hace 4 min» es exactamente el fallo que este
 * componente existe para impedir: durante una semana el tablero mostró datos del
 * 31 de agosto con todo el aspecto de estar al día, porque nada en pantalla
 * distinguía «no hay nada nuevo» de «nadie está buscando».
 */

import { useCallback, useEffect, useState } from "react";

import * as api from "../api";
import { fechaHora } from "../formato";
import { useRefresco } from "../useRefresco";

/** A partir de aquí el dato deja de ser un detalle y pasa a ser un aviso. */
const HORAS_PARA_AVISAR = 48;

/** Cada cuánto se vuelve a preguntar por el estado, en minutos. */
const MINUTOS_REFRESCO = 5;

export default function Frescura({ alRefrescar }) {
  const [estado, setEstado] = useState(null);
  const [consultadoEn, setConsultadoEn] = useState(null);
  // Un contador propio para que "hace X min" avance solo, sin volver a pedir.
  const [, forzarRender] = useState(0);

  const consultar = useCallback(async () => {
    try {
      setEstado(await api.estadoDatos());
      setConsultadoEn(Date.now());
      alRefrescar?.();
    } catch {
      // Un fallo aquí no debe romper la barra ni sacar al usuario: el resto del
      // tablero sigue siendo válido. Se conserva el último estado conocido.
    }
  }, [alRefrescar]);

  useEffect(() => {
    consultar();
  }, [consultar]);

  useRefresco(consultar, MINUTOS_REFRESCO);

  // El texto "hace X min" envejece aunque no lleguen datos nuevos.
  useEffect(() => {
    const id = setInterval(() => forzarRender((n) => n + 1), 30_000);
    return () => clearInterval(id);
  }, []);

  if (!estado) return null;

  const xm = estado.fuentes?.find((f) => f.nombre === "XM");
  if (!xm) return null;

  const viejo = xm.horas_de_retraso != null && xm.horas_de_retraso > HORAS_PARA_AVISAR;

  return (
    <div className={`frescura${viejo ? " frescura--vieja" : ""}`}>
      <span className="frescura__dato" title={xm.descripcion}>
        {xm.ultimo_dato ? (
          <>
            XM hasta <b>{fechaHora(xm.ultimo_dato)}</b>
          </>
        ) : (
          <b>Sin datos</b>
        )}
      </span>
      <span className="frescura__revision">
        {textoRevision(estado, consultadoEn)}
      </span>
    </div>
  );
}

/**
 * Con la ingesta apagada se dice, en vez de callarlo. Un tablero que solo
 * anuncia "revisado hace 2 min" cuando nadie está trayendo datos nuevos está
 * informando de su propio refresco de pantalla y haciéndolo pasar por frescura
 * del dato.
 */
function textoRevision(estado, consultadoEn) {
  if (!estado.ingesta_automatica) return "actualización manual";
  if (estado.ultima_revision) return `revisado ${hace(Date.parse(estado.ultima_revision))}`;
  if (consultadoEn) return `consultado ${hace(consultadoEn)}`;
  return "";
}

function hace(ms) {
  const minutos = Math.max(0, Math.round((Date.now() - ms) / 60_000));
  if (minutos < 1) return "ahora mismo";
  if (minutos < 60) return `hace ${minutos} min`;
  const horas = Math.round(minutos / 60);
  if (horas < 24) return `hace ${horas} h`;
  return `hace ${Math.round(horas / 24)} d`;
}
