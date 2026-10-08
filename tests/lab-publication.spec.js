const { test, expect } = require('@playwright/test');

test('transferred Pixiv extraction remains functional without upstream fetch', async ({ page }) => {
  await page.goto('/tools/mcp-toolcall-lab/#pixiv');
  await expect(page.locator('[data-pages-view="pixiv"]')).toBeVisible();
  await page.locator('#pages-pixiv-title').fill('Demo');
  await page.locator('#pages-pixiv-source-text').fill('Example original source text');
  await page.locator('[data-testid="pages-pixiv-extract-submit"]').click();
  await expect(page.locator('[data-testid="pages-pixiv-extract"]')).toContainText('Example original source text');
  await page.goto('/tools/mcp-toolcall-lab/#wiki');
  await expect(page.locator('#pages-wiki-form')).toBeVisible();
  await expect(page.locator('[data-pages-view="pixiv"]')).toBeHidden();
});
