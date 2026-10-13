import type { Plugin } from "vite";

export function readOnlyProxy(): Plugin {
  return {
    name: "rehearsal-read-only",
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const incoming = request as { url?: string; method?: string };
        const path = (incoming.url ?? "").split("?")[0];
        if (path.startsWith("/api") || path === "/healthz" || path === "/readyz") {
          if (incoming.method !== "GET" && incoming.method !== "HEAD") {
            response.statusCode = 405;
            response.setHeader("Allow", "GET, HEAD");
            response.setHeader("Content-Type", "application/json");
            response.end(JSON.stringify({ detail: "Read-only rehearsal proxy blocks mutations" }));
            return;
          }
        }
        next();
      });
    },
  };
}

export function tunnelTarget(value: string): string {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)
    || url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("Rehearsal target must be a credential-free loopback HTTP tunnel origin");
  }
  return url.origin;
}

// Direct VM FastAPI serves root routes; VM Nginx strips /api/. Fixture APIs
// and an Nginx tunnel keep the prefix. Select explicitly, never retry/fallback.
export function directBackendPath(path: string): string {
  return path === "/api" ? "/" : path.startsWith("/api/") ? path.slice(4) : path;
}
