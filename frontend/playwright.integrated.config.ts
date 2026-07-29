import { defineConfig, devices } from "@playwright/test";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(frontendRoot, "..");
const fixtureStateRoot = mkdtempSync(
  join(tmpdir(), "stock-strategy-monitoring-browser-"),
);
const statePath = join(fixtureStateRoot, "state.sqlite3");
const baseURL = "http://127.0.0.1:8765";
const venvPython = join(repositoryRoot, ".venv", "bin", "python");
const pythonExecutable =
  process.env.PYTHON ?? (existsSync(venvPython) ? venvPython : "python");

function shellArgument(value: string): string {
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

const fixtureCommand = [
  "npm",
  "--prefix",
  shellArgument(frontendRoot),
  "run",
  "build",
  "--",
  "--outDir",
  shellArgument(join(frontendRoot, "dist")),
  "&&",
  shellArgument(pythonExecutable),
  shellArgument(
    join(repositoryRoot, "backend", "scripts", "monitoring_browser_fixture.py"),
  ),
  "--host",
  "127.0.0.1",
  "--port",
  "8765",
  "--state-path",
  shellArgument(statePath),
  "--frontend-root",
  shellArgument(join(frontendRoot, "dist")),
].join(" ");

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/monitoring.integrated.e2e.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? "github" : "list",
  timeout: 120_000,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(process.env.PLAYWRIGHT_CHANNEL
          ? { channel: process.env.PLAYWRIGHT_CHANNEL }
          : {}),
      },
    },
  ],
  webServer: {
    command: fixtureCommand,
    url: `${baseURL}/api/health`,
    env: {
      ...process.env,
      PYTHONPATH: join(repositoryRoot, "backend"),
    },
    reuseExistingServer: false,
    timeout: 180_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
