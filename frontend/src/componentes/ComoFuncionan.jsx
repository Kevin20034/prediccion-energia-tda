/**
 * Cómo funcionan los modelos, en lenguaje llano.
 *
 * La tabla comparativa dice *cuál* gana; esto dice *por qué* un modelo puede
 * ganar. Va encima de la tabla a propósito: los números no significan nada para
 * quien no sabe qué está compitiendo.
 *
 * Las tarjetas se construyen a partir de las familias que de verdad aparecen en
 * el lote entrenado, no de una lista escrita a mano. Si algún día se retira una
 * familia del entrenamiento por defecto, su explicación desaparece sola en vez
 * de quedarse describiendo algo que ya no se ejecuta.
 */

import { useMemo } from "react";

import { COLOR, FAMILIAS } from "../tokens";

/**
 * Una frase por familia, sin fórmulas. La clave coincide con `familia` que
 * devuelve la API y con `tokens.FAMILIAS`, para que el color de cada tarjeta sea
 * el mismo que el de esa familia en la tabla y en la gráfica de RMSE.
 */
const EXPLICACION = {
  referencia: {
    titulo: "Repite el pasado",
    cuerpo:
      "No aprende nada: para saber el precio de mañana a las 3 de la tarde, mira el precio de hoy a las 3 de la tarde. Está aquí para marcar el listón. Un modelo que no le gane no compensa su complejidad, por bueno que parezca su R².",
  },
  arboles: {
    titulo: "Preguntan y se reparten los casos",
    cuerpo:
      "Un árbol va haciendo preguntas sobre los datos —¿los embalses están por debajo del 40 %?, ¿es festivo?— y cada respuesta separa las horas en grupos parecidos entre sí. El bosque aleatorio construye muchos árboles distintos y promedia su voto, de modo que los errores de unos compensan los de otros. XGBoost y LightGBM los encadenan: cada árbol se entrena sobre lo que falló el anterior. Afinan más, pero cuando la señal es débil terminan aprendiendo el ruido, y eso es justo lo que se ve a 30 días.",
  },
  lineal: {
    titulo: "Buscan una fórmula recta",
    cuerpo:
      "Asignan un peso a cada variable y suman. Su valor no está en el error que consiguen, sino en que los pesos se leen: dicen cuánto empuja cada factor y en qué dirección. ElasticNet además apaga las variables que no aportan, así que las que sobreviven son un resultado en sí mismo.",
  },
  serie_temporal: {
    titulo: "Modelan el ritmo de la serie",
    cuerpo:
      "En vez de mirar variables externas, descomponen la serie en nivel, tendencia y ciclos que se repiten, y proyectan esa estructura hacia adelante. Son los que mejor explican por qué una serie se comporta como lo hace, aunque aquí no sean los que menos se equivocan.",
  },
  red_neuronal: {
    titulo: "Recuerdan la secuencia",
    cuerpo:
      "La LSTM lee las horas en orden y va guardando un resumen de lo que lleva visto, así que puede aprender dependencias largas sin que se le indiquen. A cambio necesita muchos más datos y mucho más tiempo que un bosque de árboles.",
  },
};

const PASOS = [
  { nombre: "Datos de XM", detalle: "34 variables horarias" },
  { nombre: "Limpieza", detalle: "huecos y atípicos" },
  { nombre: "Variables", detalle: "109 predictoras" },
  { nombre: "Modelo", detalle: "uno por plazo" },
  { nombre: "Pronóstico", detalle: "valor + banda" },
];

export default function ComoFuncionan({ filas = [] }) {
  // Orden estable: el de `FAMILIAS`, no el que traiga la respuesta. Si el orden
  // dependiera de los datos, las tarjetas bailarían al cambiar de horizonte.
  const familias = useMemo(() => {
    const presentes = new Set(filas.map((f) => f.familia));
    return Object.keys(FAMILIAS).filter(
      (clave) => presentes.has(clave) && EXPLICACION[clave]
    );
  }, [filas]);

  return (
    <section className="explicacion" aria-labelledby="como-funcionan">
      <h2 className="explicacion__titulo" id="como-funcionan">
        Cómo trabajan estos modelos con los datos
      </h2>

      <p className="explicacion__entrada">
        Todos reciben lo mismo y devuelven lo mismo. Lo que cambia es cómo
        deciden. A cada modelo se le da una foto de una hora concreta —qué precio
        hubo, cómo estaban los embalses, qué día era, qué tiempo hacía: 109
        variables— y se le pide un solo número: cuánto valdrá la energía dentro
        de 24 horas, 7 días o 30 días. Junto al número entrega una banda, que es
        el margen dentro del cual suele acertar.
      </p>

      <Recorrido />

      <div className="explicacion__tarjetas">
        {familias.map((clave) => (
          <article className="explicacion__tarjeta" key={clave}>
            <span
              className="explicacion__punto"
              style={{ background: FAMILIAS[clave].color }}
              aria-hidden="true"
            />
            <div>
              <h3 className="explicacion__nombre">
                {FAMILIAS[clave].etiqueta}
                <span className="explicacion__lema">
                  {EXPLICACION[clave].titulo}
                </span>
              </h3>
              <p className="explicacion__cuerpo">{EXPLICACION[clave].cuerpo}</p>
            </div>
          </article>
        ))}
      </div>

      <p className="explicacion__nota">
        <strong>Por qué el examen se parte por fecha y no al azar.</strong> El
        modelo se entrena con los primeros años y se examina con los últimos
        meses, que nunca ha visto. Repartir las horas al azar dejaría horas del
        futuro dentro del entrenamiento: el modelo habría visto el final de la
        película antes del examen y sacaría una nota excelente que no se repite
        cuando el futuro es de verdad futuro.
      </p>
    </section>
  );
}

/** El recorrido del dato, dibujado. Sin librería: son cinco cajas y cuatro flechas. */
function Recorrido() {
  return (
    <ol className="recorrido">
      {PASOS.map((paso, i) => (
        <li className="recorrido__paso" key={paso.nombre}>
          <span className="recorrido__caja">
            <span className="recorrido__nombre">{paso.nombre}</span>
            <span className="recorrido__detalle">{paso.detalle}</span>
          </span>
          {i < PASOS.length - 1 && (
            <svg
              className="recorrido__flecha"
              viewBox="0 0 24 8"
              aria-hidden="true"
              focusable="false"
            >
              <path
                d="M0 4 H19 M15 1 L19 4 L15 7"
                fill="none"
                stroke={COLOR.tinta3}
                strokeWidth="1.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </li>
      ))}
    </ol>
  );
}
