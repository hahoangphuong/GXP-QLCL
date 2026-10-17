import { defineConfig, loadEnv, mergeConfig } from "vite";
import base from "../vite.config";
import { readOnlyProxy, tunnelTarget, directBackendPath } from "../src/qa/rehearsalProxy";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "GXP_");
  const target = tunnelTarget(env.GXP_REHEARSAL_PROXY_TARGET || "http://127.0.0.1:8000");
  return mergeConfig(base, {
    define: { "import.meta.env.VITE_API_BASE_URL": JSON.stringify("/api") },
    plugins: [readOnlyProxy()],
    server: {
      host: "127.0.0.1", strictPort: true,
      proxy: {
        "/api": { target, ...(env.GXP_REHEARSAL_STRIP_API_PREFIX === "1" ? { rewrite: directBackendPath } : {}) },
        "/healthz": target, "/readyz": target,
      },
    },
  });
});
