#!/usr/bin/env node
// Standalone Node runner: no Python dependency.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

function parse(argv) {
  const options = { root: '.', browserRoots: [], timeout: 900, limit: 20, match: 'passed|failed|skipped|^\\s+\\d+\\) |Error:', specs: [] };
  for (let i = 0; i < argv.length; i++) {
    const key = argv[i];
    if (key === '--dry-run') { options.dryRun = true; continue; }
    if (['--root', '--browser-root', '--browser', '--timeout', '--limit', '--match', '--node'].includes(key)) {
      if (++i >= argv.length) throw new Error('missing value for ' + key);
      const value = argv[i];
      if (key === '--browser-root') options.browserRoots.push(value);
      else options[{ '--root':'root', '--browser':'browser', '--timeout':'timeout', '--limit':'limit', '--match':'match', '--node':'node' }[key]] = value;
    } else if (key.startsWith('-')) throw new Error('unknown option: ' + key);
    else options.specs.push(key);
  }
  options.timeout = Number(options.timeout);
  options.limit = Number(options.limit);
  if (!Number.isFinite(options.timeout) || options.timeout <= 0 || !Number.isInteger(options.limit) || options.limit < 0) throw new Error('invalid timeout or limit');
  return options;
}
function discover(roots) {
  const candidates = [];
  for (const root of roots) {
    if (!fs.existsSync(root)) continue;
    for (const dir of fs.readdirSync(root)) {
      const m = /^chromium-(\d+)$/.exec(dir);
      if (!m) continue;
      for (const sub of fs.readdirSync(path.join(root, dir))) {
        if (!sub.startsWith('chrome-linux')) continue;
        for (const exe of ['chrome', 'chrome.exe']) {
          const candidate = path.join(root, dir, sub, exe);
          if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) candidates.push({ version: Number(m[1]), path: path.resolve(candidate) });
        }
      }
    }
  }
  return candidates.sort((a,b) => b.version - a.version || a.path.localeCompare(b.path))[0]?.path ?? null;
}
function main() {
  const args = parse(process.argv.slice(2));
  const root = path.resolve(args.root);
  const config = path.join(root, 'playwright.config.js');
  if (!fs.existsSync(config)) throw new Error('missing ' + config);
  const browser = args.browser ? path.resolve(args.browser) : discover(args.browserRoots.length ? args.browserRoots : ['/opt/pw-browsers']);
  if (args.browser && !fs.existsSync(browser)) throw new Error('browser not found: ' + browser);
  const bridge = path.join(path.dirname(fileURLToPath(import.meta.url)), 'portable_playwright_config.cjs');
  const cmd = [args.node || process.execPath, path.join(root, 'node_modules/@playwright/test/cli.js'), 'test', '-c', bridge, ...args.specs, '--reporter=line'];
  if (args.dryRun) { console.log(JSON.stringify({ command: cmd, browser, cwd: root, config })); return 0; }
  const env = { ...process.env, PORTABLE_PW_BASE_CONFIG: config, PORTABLE_PW_TEST_DIR: path.join(root, 'tests') };
  if (browser) env.PORTABLE_PW_BROWSER = browser;
  else delete env.PORTABLE_PW_BROWSER;
  const result = spawnSync(cmd[0], cmd.slice(1), { cwd: root, env, encoding: 'utf8', timeout: args.timeout * 1000, maxBuffer: 32 * 1024 * 1024 });
  const timedOut = result.error?.code === 'ETIMEDOUT';
  const exitCode = timedOut ? 124 : result.error ? 127 : result.status ?? 1;
  const lines = ((result.stdout || '') + '\n' + (result.stderr || '')).split(/\r?\n/).filter(line => new RegExp(args.match).test(line));
  console.log(JSON.stringify({ exit_code: exitCode, timed_out: timedOut, browser, lines: args.limit ? lines.slice(0,args.limit) : lines, ...(result.error && !timedOut ? {error:result.error.message} : {}) }));
  return exitCode;
}
try { process.exitCode = main(); }
catch (error) { console.error(error.message); process.exitCode = 2; }
