// Keep portfolio behavior checks independent of third-party badge availability.
// This fixture replaces decorative remote pixels, not local data or assertions.
const { test: base, expect } = require('@playwright/test');
const path = require('node:path');
const test = base.extend({
  page: async ({ page }, use) => {
    await page.route('https://img.shields.io/github/stars/**', route => route.fulfill({
      status: 200,
      contentType: 'image/svg+xml',
      path: path.join(__dirname, 'fixtures/github-stars.svg'),
    }));
    await use(page);
  },
});
module.exports = { test, expect };
