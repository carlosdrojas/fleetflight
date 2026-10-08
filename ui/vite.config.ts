import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

// Dev-only stand-in for `fleetflight serve`: answers the same /api routes from ../fixtures
// (or from FF_FIXTURES=<dir>, e.g. a checker `out/` dir plus a describe.json).
// Set FF_API=http://127.0.0.1:8765 to proxy to the real server instead.
const FIXTURES = resolve(process.env.FF_FIXTURES ?? resolve(import.meta.dirname, "../fixtures"));

function loadFixtures(): Record<string, unknown>[] {
  return readdirSync(FIXTURES)
    .filter((f) => f.endsWith(".json"))
    .sort()
    .map((f) => JSON.parse(readFileSync(resolve(FIXTURES, f), "utf8")));
}

const bySchema = (docs: Record<string, unknown>[], s: string) =>
  docs.filter((d) => typeof d.schema === "string" && d.schema.startsWith(`fleetflight/${s}@`));

const normSut = (v: string, name: string) => (v.includes("@") ? v : `${name}@${v}`);

function fixtureApi(): Plugin {
  return {
    name: "fleetflight-fixture-api",
    configureServer(server) {
      server.middlewares.use("/api", (req, res) => {
        const send = (code: number, body: unknown) => {
          res.statusCode = code;
          res.setHeader("Content-Type", "application/json");
          setTimeout(() => res.end(JSON.stringify(body)), 120);
        };
        const docs = loadFixtures();
        const url = (req.url ?? "/").split("?")[0].replace(/\/+$/, "");
        const parts = url.split("/").filter(Boolean).map(decodeURIComponent);

        if (req.method === "POST" && parts[0] === "replay") {
          let raw = "";
          req.on("data", (c) => (raw += c));
          req.on("end", () => {
            let body: { cex?: string; sut?: string } = {};
            try {
              body = JSON.parse(raw || "{}");
            } catch {
              return send(400, { error: "invalid JSON body" });
            }
            const describe = bySchema(docs, "describe")[0] as { sut?: { name?: string } } | undefined;
            const name = describe?.sut?.name ?? "";
            const hit = bySchema(docs, "replay-result").find((d) => {
              const r = d as { counterexample?: string; sut?: { id?: string }; cex_sut?: string };
              const want = body.sut ? normSut(body.sut, name) : r.cex_sut;
              return r.counterexample === body.cex && r.sut?.id === want;
            });
            if (!hit) return send(404, { error: `no fixture replay for ${body.cex} on ${body.sut}` });
            send(200, hit);
          });
          return;
        }
        if (req.method !== "GET") return send(405, { error: "method not allowed" });

        if (parts[0] === "describe" && parts.length === 1) return send(200, bySchema(docs, "describe")[0]);
        if (parts[0] === "runs" && parts.length === 1) {
          const list = bySchema(docs, "run-list")[0];
          if (list) return send(200, list);
          // No run-list on disk (a raw out/ dir): build one from the check reports, like serve does.
          const runs = bySchema(docs, "check-report").map((d) => {
            const r = d as { run_id?: string; created_at?: string; model?: { name?: string }; sut?: { id?: string }; verdict?: string; stats?: { states?: number; wall_s?: number }; invariants?: { counterexample?: string | null }[] };
            return {
              run_id: r.run_id, created_at: r.created_at, model: r.model?.name, sut: r.sut?.id, verdict: r.verdict,
              states: r.stats?.states, wall_s: r.stats?.wall_s,
              counterexamples: (r.invariants ?? []).map((i) => i.counterexample).filter(Boolean),
            };
          });
          return send(200, { schema: "fleetflight/run-list@1", runs });
        }
        if (parts[0] === "runs" && parts.length === 2) {
          const hit = bySchema(docs, "check-report").find((d) => d.run_id === parts[1]);
          return hit ? send(200, hit) : send(404, { error: `no run ${parts[1]}` });
        }
        if (parts[0] === "cex" && parts.length === 2) {
          const hit = bySchema(docs, "counterexample").find((d) => d.id === parts[1]);
          return hit ? send(200, hit) : send(404, { error: `no counterexample ${parts[1]}` });
        }
        send(404, { error: `unknown endpoint /api${url}` });
      });
    },
  };
}

const api = process.env.FF_API;

export default defineConfig({
  base: "./",
  plugins: [react(), ...(api ? [] : [fixtureApi()])],
  server: api
    ? {
        proxy: {
          "/api": {
            target: api,
            changeOrigin: true,
            // serve rejects cross-origin POST /api/replay; present the dev page as same-origin.
            configure: (proxy) => proxy.on("proxyReq", (req) => req.setHeader("origin", api)),
          },
        },
      }
    : {},
  build: { outDir: "dist", emptyOutDir: true },
});
