const { test, expect } = require('@playwright/test');

test('project cards and controls consume the pinned shared web-ui theme', async ({ page }) => {
  await page.route('https://api.github.com/**', route => route.fulfill({ status: 503, body: '{}' }));
  await page.route('https://img.shields.io/**', route => route.abort());
  await page.goto('/');
  await expect(page.locator('#projects-render-root .ui-card').first()).toBeVisible();
  for (const asset of ['tokens.css', 'base.css', 'components.css', 'themes/modern.css']) {
    const sheet = page.locator(`link[href="./tools/vendor/web-ui/css/${asset}"]`);
    await expect(sheet).toHaveCount(1);
    expect(await sheet.evaluate(link => !!link.sheet)).toBe(true);
  }
  await expect(page.locator('body')).toHaveAttribute('data-ui-theme', 'modern');
  await page.evaluate(() => document.body.style.setProperty('--ui-border', 'rgb(1, 2, 3)'));
  for (const selector of ['#projects-render-root .ui-card', '#project-search-input', '#projects-render-root .project-copy']) {
    await expect(page.locator(selector).first()).toHaveCSS('border-top-color', 'rgb(1, 2, 3)');
  }
  for (const mode of ['github-like', 'xml-like', 'json', 'markdown', 'modern']) {
    await page.selectOption('#view-mode-select', mode);
    const theme = mode === 'modern' ? 'modern' : mode === 'github-like' ? 'github-like' : 'plain';
    await expect(page.locator('body')).toHaveAttribute('data-ui-theme', theme);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  for (const selector of ['#project-search-input', '#projects-render-root .project-copy']) {
    const box = await page.locator(selector).first().boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(44);
  }
});
