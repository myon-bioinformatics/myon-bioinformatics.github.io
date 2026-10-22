'use strict';
// Reuse repository configuration without changing it.
const base = require(process.env.PORTABLE_PW_BASE_CONFIG);
const cfg = base.default || base;
const executablePath = process.env.PORTABLE_PW_BROWSER;
function override(use) {
  return { ...use, ...(executablePath ? { channel: undefined } : {}),
    launchOptions: { ...(use?.launchOptions || {}), ...(executablePath ? { executablePath } : {}) } };
}
module.exports = {
  ...cfg,
  testDir: process.env.PORTABLE_PW_TEST_DIR,
  use: override(cfg.use || {}),
  projects: (cfg.projects || []).map(p => ({ ...p, use: override(p.use || {}) })),
};
