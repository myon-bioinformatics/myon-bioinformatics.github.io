import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const runner = fileURLToPath(new URL('../tools/portable_playwright.mjs', import.meta.url));
function fixture() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'portable-pw-'));
  fs.writeFileSync(path.join(root, 'playwright.config.js'), 'module.exports = {};\n');
  const cli = path.join(root, 'node_modules', '@playwright', 'test', 'cli.js');
  fs.mkdirSync(path.dirname(cli), { recursive: true });
  fs.writeFileSync(cli, "console.log('1 passed'); console.error('Error: simulated'); process.exit(Number(process.env.FAKE_EXIT || 0));\n");
  return root;
}
function run(root, args = [], extraEnv = {}) {
  return spawnSync(process.execPath, [runner, '--root', root, ...args], {
    encoding: 'utf8', env: { ...process.env, ...extraEnv, PATH: path.dirname(process.execPath) },
  });
}
test('node standalone without Python executable in PATH', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const r = run(root);
  assert.equal(r.status, 0, r.stderr);
  assert.deepEqual(JSON.parse(r.stdout).lines, ['1 passed', 'Error: simulated']);
});
test('node preserves nonzero exit status', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const r = run(root, [], { FAKE_EXIT: '7' });
  assert.equal(r.status, 7);
  assert.equal(JSON.parse(r.stdout).exit_code, 7);
});
test('node dry run and line filtering', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  assert.equal(JSON.parse(run(root, ['--dry-run']).stdout).cwd, root);
  assert.deepEqual(JSON.parse(run(root, ['--match', 'passed', '--limit', '1']).stdout).lines, ['1 passed']);
});
