import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const state = await mkdtemp(join(tmpdir(), 'memora-e2e-'));
const child = spawn(process.execPath, [fileURLToPath(import.meta.resolve('@playwright/test/cli')), 'test', '--config', 'tests/e2e/playwright.config.ts', ...process.argv.slice(2)], {
  stdio: 'inherit', env: { ...process.env, MEMORA_E2E_STATE: state },
});
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => child.kill(signal));
const code = await new Promise(resolve => {
  child.once('error', error => { console.error(error); resolve(1); });
  child.once('exit', (code) => resolve(code ?? 1));
});
await rm(state, { recursive: true, force: true });
process.exitCode = code;
