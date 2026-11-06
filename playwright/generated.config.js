// Exercise the same generated assets over the unchanged public URLs.
process.env.GENERATED_ASSETS_TEST = '1';
const path = require('path');
const root = path.resolve(__dirname, '..');
const base = require('../playwright.config.js');
module.exports = {
  ...base,
  testDir: path.join(root, 'tests'),
  outputDir: path.join(root, 'test-results'),
  webServer: { ...base.webServer, cwd: root, command: 'python3 -m http.server 8080 --bind 127.0.0.1 --directory .generated-site' },
};
