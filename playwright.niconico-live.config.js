// Opt-in only: uses the deployed site and REAL API. No local web server/routes.
const { defineConfig, devices } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  testMatch: 'niconico-live.spec.js',
  timeout: 60000,
  retries: 0,
  workers: 1,
  use: { ...devices['Desktop Chrome'], channel:'chromium',
    baseURL: process.env.NICONICO_LIVE_BASE_URL || 'https://myon-bioinformatics.github.io',
    screenshot:'only-on-failure', trace:'retain-on-failure' },
});
