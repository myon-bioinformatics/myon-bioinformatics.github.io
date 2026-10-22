'use strict';
// Reuse repository configuration without changing it.
const path = require('node:path');
const baseConfig = process.env.PORTABLE_PW_BASE_CONFIG;
const base = require(baseConfig);
const cfg = base.default || base;
const executablePath = process.env.PORTABLE_PW_BROWSER;
function override(use) {
  return { ...use, ...(executablePath ? { channel: undefined } : {}),
    launchOptions: { ...(use?.launchOptions || {}), ...(executablePath ? { executablePath } : {}) } };
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
