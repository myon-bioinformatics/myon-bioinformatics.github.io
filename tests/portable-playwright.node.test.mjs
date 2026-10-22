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

const bridgePath = fileURLToPath(new URL('../tools/portable_playwright_config.cjs', import.meta.url));
function loadBridge(root, content) {
  const configDir = path.join(root, 'config');
  fs.mkdirSync(configDir, { recursive: true });
  const config = path.join(configDir, 'playwright.config.js');
  fs.writeFileSync(config, content);
  const script = 'console.log(JSON.stringify(require(' + JSON.stringify(bridgePath) + ').webServer ?? null))';
  const r = spawnSync(process.execPath, ['-e', script], {
    encoding: 'utf8',
    env: { ...process.env, PORTABLE_PW_BASE_CONFIG: config, PORTABLE_PW_TEST_DIR: path.join(root, 'tests') },
  });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}
test('bridge serves from original config directory when cwd omitted', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const config = 'module.exports = {webServer: {command: "node server.js", url: "http://localhost:8080", reuseExistingServer: false}}';
  assert.deepEqual(loadBridge(root, config), {
    command: 'node server.js', url: 'http://localhost:8080',
    reuseExistingServer: false, cwd: path.join(root, 'config'),
  });
});
test('bridge resolves relative cwd in server array and preserves absolute cwd', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const absolute = path.join(root, 'absolute');
  const config = 'module.exports = {webServer: [' +
    '{command: "node default.js"},' +
    '{command: "node relative.js", cwd: "../site", env: {MODE: "test"}},' +
    '{command: "node absolute.js", cwd: ' + JSON.stringify(absolute) + ', timeout: 1234}' +
    ']}';
  assert.deepEqual(loadBridge(root, config), [
    {command: 'node default.js', cwd: path.join(root, 'config')},
    {command: 'node relative.js', cwd: path.join(root, 'site'), env: {MODE: 'test'}},
    {command: 'node absolute.js', cwd: absolute, timeout: 1234},
  ]);
});
test('bridge leaves configs without webServer unchanged', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  assert.equal(loadBridge(root, 'module.exports = {};'), null);
});
function loadLaunch(root, extraEnv = {}) {
  const configDir = path.join(root, 'config');
  fs.mkdirSync(configDir, { recursive: true });
  const config = path.join(configDir, 'playwright.config.js');
  fs.writeFileSync(config, 'module.exports = {use:{channel:"chromium",headless:true},projects:[{name:"chromium",use:{channel:"chromium",headless:true}}]}');
  const script = 'const cfg = require(' + JSON.stringify(bridgePath) + '); console.log(JSON.stringify({use:cfg.use,projects:cfg.projects}))';
  const env = { ...process.env, PORTABLE_PW_BASE_CONFIG: config, PORTABLE_PW_TEST_DIR: path.join(root, 'tests') };
  delete env.PORTABLE_PW_BROWSER;
  delete env.PORTABLE_PW_HEADLESS_SHELL;
  Object.assign(env, extraEnv);
  const r = spawnSync(process.execPath, ['-e', script], {
    encoding: 'utf8',
    env,
  });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}
test('bridge keeps the chromium channel unless a browser path or headless shell is requested', t => {
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const kept = loadLaunch(root);
  assert.equal(kept.use.channel, 'chromium');
  assert.equal(kept.use.headless, true);
  assert.equal(kept.projects[0].use.channel, 'chromium');
  const shell = loadLaunch(root, { PORTABLE_PW_HEADLESS_SHELL: '1' });
  assert.equal(shell.use.channel, undefined);
  assert.equal(shell.projects[0].use.channel, undefined);
  assert.equal(shell.use.headless, true);
  assert.equal(shell.use.launchOptions.executablePath, undefined);
  const browser = loadLaunch(root, { PORTABLE_PW_BROWSER: '/tmp/chrome' });
  assert.equal(browser.use.channel, undefined);
  assert.equal(browser.projects[0].use.channel, undefined);
  assert.equal(browser.use.launchOptions.executablePath, '/tmp/chrome');
});
