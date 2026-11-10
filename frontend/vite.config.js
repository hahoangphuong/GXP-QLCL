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
            "/api": {
                target: "http://127.0.0.1:8000",
                rewrite: function (path) { return path.replace(/^\/api(?=\/|$)/, ""); },
            },
        },
    },
});
