import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// The Vite dev server proxies /api to the FastAPI backend so the frontend can
// use same-origin relative URLs in development. This keeps the browser out of
// CORS entirely and means no API base URL needs to be configured locally.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
