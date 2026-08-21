import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
  server: {
    port: 4173,
    proxy: {
      "/app": "http://127.0.0.1:8000",
      "/companies": "http://127.0.0.1:8000",
      "/sites": "http://127.0.0.1:8000",
      "/cases": "http://127.0.0.1:8000",
      "/documents": "http://127.0.0.1:8000",
      "/document-generation-runs": "http://127.0.0.1:8000",
      "/certificates": "http://127.0.0.1:8000",
      "/business-eligibility-certificates": "http://127.0.0.1:8000",
      "/storage": "http://127.0.0.1:8000",
    },
  },
});
