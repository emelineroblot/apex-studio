import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/**
 * Configuration minimale (dev-tester, J1) — cible la logique qui casse silencieusement :
 * file d'upload, bascule fixtures/live, libellés de motifs de quarantaine. Pas de suite
 * exhaustive de composants : le backend n'a pas de rendu, on ne duplique pas cet effort
 * côté front pour du J1.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: false,
  },
  // Aucun test n'importe de CSS — évite que Vite ne résolve `postcss.config.mjs` du
  // projet (pipeline Tailwind v4 pensé pour `next build`, pas pour Vitest) au démarrage.
  css: { postcss: { plugins: [] } },
});
