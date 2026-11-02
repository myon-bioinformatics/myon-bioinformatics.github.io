// Exercise the same generated assets over the unchanged public URLs.
process.env.GENERATED_ASSETS_TEST = '1';
const base = require('./playwright.config.js');
module.exports = {
  ...base,
  webServer: { ...base.webServer, command: 'python3 -m http.server 8080 --bind 127.0.0.1 --directory .generated-site' },
};
