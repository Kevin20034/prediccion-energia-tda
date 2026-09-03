import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import "./estilos/base.css";
import "./estilos/acceso.css";
import "./estilos/app.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <App />
  </StrictMode>
);
