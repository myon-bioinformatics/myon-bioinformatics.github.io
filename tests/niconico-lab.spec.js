// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Niconico Lab Search Tab', () => {
  test('displays Niconico search tab and panel', async ({ page }) => {
    await page.goto('/tools/mcp-toolcall-lab/');
    await page.waitForLoadState('networkidle');

    const niconicoNav = page.locator('[data-testid="pages-nav-niconico"]');
    await expect(niconicoNav).toBeVisible();

    await niconicoNav.click();

    const niconicoSection = page.locator('[data-testid="pages-niconico"]');
    await expect(niconicoSection).toBeVisible();

    await expect(page.locator('[data-testid="pages-niconico-query"]')).toHaveValue('初音ミク');
    await expect(page.locator('[data-testid="pages-niconico-search"]')).toBeVisible();
  });
});
