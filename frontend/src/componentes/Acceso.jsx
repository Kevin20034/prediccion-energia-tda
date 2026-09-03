import { useState } from "react";

import { entrar } from "../api";
import LienzoEmbalse from "./LienzoEmbalse";

/** Cuentas de demostración creadas por `python -m scripts.seed`. */
const CUENTAS = [
  { rol: "Administrador", email: "admin@tda.edu.co", password: "Admin123*" },
  { rol: "Analista", email: "analista@tda.edu.co", password: "Analista123*" },
  { rol: "Institucional", email: "consulta@tda.edu.co", password: "Consulta123*" },
];

/** Retardo de la entrada escalonada, en milisegundos. */
const PASO = 70;

export default function Acceso({ alEntrar }) {
  const [email, setEmail] = useState("admin@tda.edu.co");
  const [password, setPassword] = useState("Admin123*");
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);
  const [saliendo, setSaliendo] = useState(false);

  async function enviar(evento) {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await entrar(email, password);
      // Se emerge del agua antes de montar el tablero: la animación de salida
      // ocupa el tiempo que de todas formas tarda la primera carga de datos.
      setSaliendo(true);
      await alEntrar();
    } catch (e) {
      setError(e.message);
      setSaliendo(false);
      setEnviando(false);
    }
  }

  function usar(cuenta) {
    setEmail(cuenta.email);
    setPassword(cuenta.password);
    setError(null);
  }

  const escalonado = (indice) => ({ animationDelay: `${indice * PASO}ms` });

  return (
    <div className={`acceso${saliendo ? " acceso--saliendo" : ""}`}>
      <LienzoEmbalse />
      <div className="acceso__reticula" aria-hidden="true" />

      <div className="acceso__caja emerge">
        <div className="rotulo emerge" style={escalonado(1)}>
          Tecnológico de Antioquia
        </div>
        <h1 className="acceso__marca emerge" style={escalonado(2)}>
          Sistema <em>Interconectado</em> Nacional
        </h1>
        <p className="acceso__sub emerge" style={escalonado(3)}>
          Pronóstico del precio de bolsa y de la demanda, con datos horarios de XM.
        </p>

        {error && (
          <div className="aviso aviso--error" role="alert">
            {error}
          </div>
        )}

        <form onSubmit={enviar}>
          <label className="acceso__campo emerge" style={escalonado(4)}>
            <span className="rotulo">Correo</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>

          <label className="acceso__campo emerge" style={escalonado(5)}>
            <span className="rotulo">Contraseña</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          <div className="emerge" style={escalonado(6)}>
            <button className="boton boton--solido" type="submit" disabled={enviando}>
              {enviando ? "Entrando…" : "Entrar"}
            </button>
          </div>
        </form>

        <div className="acceso__pistas emerge" style={escalonado(7)}>
          <div className="rotulo" style={{ marginBottom: 9 }}>
            Cuentas de prueba
          </div>
          {CUENTAS.map((c) => (
            <button
              key={c.email}
              type="button"
              className="acceso__pista"
              onClick={() => usar(c)}
            >
              <b>{c.rol}</b>
              <span>{c.email}</span>
            </button>
          ))}
        </div>

        <div className="acceso__pie rotulo emerge" style={escalonado(8)}>
          Datos públicos de XM · Open-Meteo · NOAA
        </div>
      </div>
    </div>
  );
}
