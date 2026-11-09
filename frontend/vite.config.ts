import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend, so the browser only ever talks to localhost.
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
