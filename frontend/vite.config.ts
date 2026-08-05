import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/projects": "http://127.0.0.1:8000",
      "/sessions": "http://127.0.0.1:8000",
      "/turns": "http://127.0.0.1:8000",
      "/jobs": "http://127.0.0.1:8000",
      "/upload": "http://127.0.0.1:8000",
      "/output": "http://127.0.0.1:8000",
      "/uploads": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
