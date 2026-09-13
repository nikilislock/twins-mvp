import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  base: "/static/dist/",
  build: { outDir: "../../twins/static/dist", emptyOutDir: true, chunkSizeWarningLimit: 1400 },
  server: { proxy: { "/api": "http://127.0.0.1:8765", "/static/assets": "http://127.0.0.1:8765", "/docs": "http://127.0.0.1:8765" } }
});
