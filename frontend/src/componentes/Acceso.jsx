import { useState } from "react";

import { entrar } from "../api";

/** Cuentas de demostración creadas por `python -m scripts.seed`. */
const CUENTAS = [
  { rol: "Administrador", email: "admin@tda.edu.co", password: "Admin123*" },
  { rol: "Analista", email: "analista@tda.edu.co", password: "Analista123*" },
  { rol: "Institucional", email: "consulta@tda.edu.co", password: "Consulta123*" },
];

export default function Acceso({ alEntrar }) {
  const [email, setEmail] = useState("admin@tda.edu.co");
  const [password, setPassword] = useState("Admin123*");
  const [error, setError] = useState(null);
  const [enviando, setEnviando] = useState(false);

  async function enviar(evento) {
    evento.preventDefault();
    setError(null);
    setEnviando(true);
    try {
      await entrar(email, password);
      await alEntrar();
    } catch (e) {
      setError(e.message);
      setEnviando(false);
    }
  }

  function usar(cuenta) {
    setEmail(cuenta.email);
    setPassword(cuenta.password);
    setError(null);
  }

  return (
    <div className="acceso">
      <div className="acceso__caja">
        <div className="etiqueta">Tecnológico de Antioquia</div>
        <h1 className="acceso__marca">Precio de bolsa</h1>
        <p className="acceso__sub">
          Estimación del precio de la energía en el mercado eléctrico colombiano.
        </p>

        {error && <div className="mensaje mensaje--error">{error}</div>}

        <form onSubmit={enviar}>
          <label className="acceso__campo">
            <span className="etiqueta">Correo</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="username"
              required
            />
          </label>

          <label className="acceso__campo">
            <span className="etiqueta">Contraseña</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </label>

          <button className="boton boton--solido" type="submit" disabled={enviando}>
            {enviando ? "Entrando…" : "Entrar"}
          </button>
        </form>

        <div className="acceso__pistas">
          <div className="etiqueta" style={{ marginBottom: 8 }}>
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
      </div>
    </div>
  );
}
