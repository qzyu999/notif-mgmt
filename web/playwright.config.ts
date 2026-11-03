import { defineConfig } from "@playwright/test";

// End-to-end against a throwaway synthetic database seeded by the CLI demo.
// Requires the API venv at ../.venv and a one-time browser install:
//   npx playwright install chromium
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:5173" },
  webServer: [
    {
      command:
        "rm -f /tmp/notif-mgmt-e2e.db && .venv/bin/notif-mgmt demo --db /tmp/notif-mgmt-e2e.db && NOTIF_MGMT_DB=/tmp/notif-mgmt-e2e.db .venv/bin/uvicorn notif_mgmt.api:app --host 127.0.0.1 --port 8000",
      cwd: "..",
      url: "http://127.0.0.1:8000/api/v1/people",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
