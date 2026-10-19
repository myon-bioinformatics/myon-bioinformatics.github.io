// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('AI Tech Highlights Widget', () => {
  test('renders AI highlights section and shuffle button', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const section = page.locator('#ai-highlights');
    await expect(section).toBeVisible();

    const root = page.locator('#ai-highlights-render-root');
    await expect(root).toBeVisible();

    const cards = root.locator('.card');
    await expect(cards).toHaveCount(3);

    const refreshBtn = page.locator('#ai-highlights-refresh');
    await expect(refreshBtn).toBeVisible();

    await refreshBtn.click();
    await expect(cards).toHaveCount(3);
  });
});
