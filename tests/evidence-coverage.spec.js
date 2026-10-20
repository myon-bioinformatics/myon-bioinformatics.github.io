// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Sub-site & Sub-page Evidence Coverage', () => {
  const routes = [
    { name: 'Home', path: '/' },
    { name: 'HTML Import Tool', path: '/tools/html-import/' },
    { name: 'Lab Home', path: '/tools/mcp-toolcall-lab/#home' },
    { name: 'Lab Wiki Tab', path: '/tools/mcp-toolcall-lab/#wiki' },
    { name: 'Lab Pixiv Tab', path: '/tools/mcp-toolcall-lab/#pixiv' },
    { name: 'Lab Niconico Tab', path: '/tools/mcp-toolcall-lab/#niconico' },
    { name: 'Lab Diagnostics', path: '/tools/mcp-toolcall-lab/repository-diagnostics.html' },
  ];

  for (const route of routes) {
    test(`loads sub-page ${route.name} without errors`, async ({ page }) => {
      const response = await page.goto(route.path);
      expect(response?.status()).toBe(200);
      await page.waitForLoadState('networkidle');

      const screenshotBuf = await page.screenshot({ type: 'png' });
      expect(screenshotBuf.length).toBeGreaterThan(1000);
    });
  }
});
