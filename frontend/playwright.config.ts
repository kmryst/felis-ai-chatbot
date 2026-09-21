import { defineConfig, devices } from "@playwright/test";

const frontendOrigin = "http://127.0.0.1:13173";
const stubOrigin = "http://127.0.0.1:18173";

export default defineConfig({
  testDir: "./e2e",
  // Vitest の既定パターン (*.test.* / *.spec.*) と分離する。
  testMatch: "**/*.pw.mts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  timeout: 30_000,
  metadata: {
    execution_purpose: "validation",
    stage: "local-environment",
    authentication: "local-principal-check-disabled",
  },
  outputDir: "./e2e-results/sli-local/artifacts",
  reporter: [
    ["list"],
    ["json", { outputFile: "./e2e-results/sli-local/results.json" }],
  ],
  use: {
    baseURL: frontendOrigin,
    serviceWorkers: "block",
    trace: "off",
    video: "off",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      name: "Chat fixture stub",
      command: "node e2e/support/chat-stub.mjs",
      url: `${stubOrigin}/healthz`,
      reuseExistingServer: false,
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
    {
      name: "Local frontend",
      command: "npm run dev -- --hostname 127.0.0.1 --port 13173",
      url: frontendOrigin,
      // 既存プロセスや .env の接続先・credential をテストに流用しない。
      reuseExistingServer: false,
      env: {
        NODE_ENV: "development",
        BACKEND_ORIGIN: stubOrigin,
        CHAT_API_KEY: "",
        BFF_PRINCIPAL_CHECK_DISABLED: "true",
        NEXT_TELEMETRY_DISABLED: "1",
      },
      timeout: 120_000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
  ],
});
