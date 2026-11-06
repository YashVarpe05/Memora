import path from 'node:path';
import { defineConfig } from '@playwright/test';

if (!process.env.MEMORA_E2E_STATE) throw new Error('Run pnpm test:e2e so temporary state is isolated.');
const cwd = path.resolve(import.meta.dirname, '../..');
const api = Number(process.env.MEMORA_E2E_API_PORT || 18080);
const web = Number(process.env.MEMORA_E2E_WEB_PORT || 18173);
export default defineConfig({
  testDir: '.', testMatch: '**/*.spec.ts', fullyParallel: false, workers: 1,
  timeout: 120_000, expect: { timeout: 15_000 }, retries: 0,
  outputDir: path.join(cwd, 'test-results'),
  reporter: [['list'], ['html', { outputFolder: path.join(cwd, 'playwright-report'), open: 'never' }]],
  use: {
    baseURL: `http://127.0.0.1:${web}`, browserName: 'chromium',
    viewport: { width: 375, height: 812 }, trace: 'retain-on-failure', screenshot: 'only-on-failure',
    launchOptions: { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH },
  },
  webServer: [
    { cwd, command: 'uv --directory ../api run python tests/e2e_server.py',
      url: `http://127.0.0.1:${api}/health`, reuseExistingServer: false, timeout: 60_000 },
    { cwd, command: 'pnpm exec vite --config tests/e2e/vite.config.ts',
      url: `http://127.0.0.1:${web}`, reuseExistingServer: false, timeout: 60_000 },
  ],
});
