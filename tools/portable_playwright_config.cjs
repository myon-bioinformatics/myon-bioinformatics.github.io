'use strict';
// Reuse repository configuration without changing it.
const path = require('node:path');
const baseConfig = process.env.PORTABLE_PW_BASE_CONFIG;
const base = require(baseConfig);
const cfg = base.default || base;
const executablePath = process.env.PORTABLE_PW_BROWSER;
const headlessShell = process.env.PORTABLE_PW_HEADLESS_SHELL === '1';
function override(use) {
  const next = { ...use,
    launchOptions: { ...(use?.launchOptions || {}), ...(executablePath ? { executablePath } : {}) } };
  // A browser path replaces the channel build. Headless shell cannot launch the channel build.
  if (executablePath || headlessShell)
    delete next.channel;
  return next;
}
function overrideWebServer(server) {
  const baseDir = path.dirname(baseConfig);
  function resolveCwd(entry) {
    return { ...entry, cwd: path.resolve(baseDir, entry.cwd || '.') };
  }
  return Array.isArray(server) ? server.map(resolveCwd) : resolveCwd(server);
}
module.exports = {
  ...cfg,
  ...(cfg.webServer ? { webServer: overrideWebServer(cfg.webServer) } : {}),
  testDir: process.env.PORTABLE_PW_TEST_DIR,
  use: override(cfg.use || {}),
  projects: (cfg.projects || []).map(p => ({ ...p, use: override(p.use || {}) })),
};
