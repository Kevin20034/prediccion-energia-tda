import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// El frontend llama a rutas que empiezan por /api y Vite las reenvía al backend.
// Así el navegador solo habla con un origen y CORS deja de existir como problema
// —tanto aquí como en producción, donde un nginx haría exactamente lo mismo.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    open: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (ruta) => ruta.replace(/^\/api/, ""),
      },
    },
  },
});
