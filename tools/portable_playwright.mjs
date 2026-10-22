#!/usr/bin/env node
// Node entrypoint delegates to the same stdlib Python runner.
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const script = path.join(path.dirname(fileURLToPath(import.meta.url)), 'portable_playwright.py');
const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const result = spawnSync(python, ['-S', script, ...process.argv.slice(2)], { stdio: 'inherit' });
if (result.error) { console.error(result.error.message); process.exitCode = 127; }
else process.exitCode = result.status ?? 1;
