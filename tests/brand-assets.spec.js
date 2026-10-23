// @ts-check
const { test, expect } = require('@playwright/test');

for (const width of [390, 1280]) {
  test(`brand icon and favicons stay intact across modes at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.route('https://api.github.com/**', route => route.abort());
    await page.goto('/');
    for (const mode of ['modern', 'xml-like', 'json', 'markdown', 'github-like']) {
      await page.locator('#view-mode-select').selectOption(mode);
      await expect(page.locator('body')).toHaveAttribute('data-view-mode', mode);
      const brand = page.locator('.site-header .brand-icon');
      await expect(brand).toBeVisible();
      expect(await brand.evaluate(image => ({ loaded: image.complete, width: image.naturalWidth, height: image.naturalHeight })))
        .toEqual({ loaded: true, width: 170, height: 170 });
      await expect(page.locator('.site-header h1')).toHaveText('myon-bioinformatics');
      const header = await page.locator('.site-header .container').boundingBox();
      const heading = await page.locator('.site-header h1').boundingBox();
      expect(header).not.toBeNull();
      expect(heading).not.toBeNull();
      expect(heading.x + heading.width).toBeLessThanOrEqual(header.x + header.width);
    }
    const icons = await page.locator('link[rel="icon"]').evaluateAll(links => links.map(link => link.getAttribute('href')));
    expect(icons).toEqual(['./favicon.ico', './assets/brand/favicon-32x32.png', './assets/brand/favicon-16x16.png']);
    for (const href of icons) {
      const response = await request.get(href);
      expect(response.status()).toBe(200);
      expect((await response.body()).length).toBeGreaterThan(100);
    }
    await page.screenshot({ path: `test-results/brand-${width}.png` });
  });
}

test('brand assets also resolve when the page is served below a subpath', async ({ page, request }) => {
  await page.route('**/preview/**', async route => {
    const url = new URL(route.request().url());
    const response = await request.get(url.origin + url.pathname.replace(/^\/preview/, '') + url.search);
    await route.fulfill({ response });
  });
  await page.goto('/preview/index.html');
  const brand = page.locator('.site-header .brand-icon');
  await expect(brand).toBeVisible();
  await expect(brand).toHaveJSProperty('naturalWidth', 170);
  const hrefs = await page.locator('link[rel="icon"]').evaluateAll(links => links.map(link => link.href));
  for (const href of hrefs) expect(new URL(href).pathname).toMatch(/^\/preview\//);
});
