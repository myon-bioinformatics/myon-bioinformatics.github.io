const { test, expect } = require('@playwright/test');
// Project cards exclude archived repositories; use the same pool as project-catalog specs.
const projectCount = require('../api/repos.json').repos.filter(repo => !repo.archived).length;
const endpoint = 'https://api.github.com/search/repositories?*';
test('live cards follow all display modes and retain current mode on late response', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => release=resolve);
  await page.route(endpoint, async route => {
    await gate;
    await route.fulfill({ json: { items: [0,1,2,3].map(i => ({
      full_name:`demo/model${i}`, html_url:`https://github.com/demo/model${i}`,
      description:'Safe AI example', stargazers_count:1001+i, language:'Python'
    })) } });
  });
  await page.goto('/');
  await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  await page.selectOption('#view-mode-select','json');
  release();
  await expect(page.locator('#ai-highlights-status')).toContainText('public GitHub API');
  await expect(page.locator('body')).toHaveAttribute('data-view-mode','json');
  for (const [mode, renderer] of [['xml-like','xml'],['json','json'],['markdown','markdown'],['github-like','web'],['modern','web']]) {
    await page.selectOption('#view-mode-select',mode);
    await expect(page.locator('#ai-highlights-render-root')).toHaveAttribute('data-renderer',renderer);
    await expect(page.locator('#ai-highlights-render-root')).toContainText('demo/model');
  }
  await page.locator('#ai-highlights-refresh').click();
  await expect(page.locator('#ai-highlights-render-root .card')).toHaveCount(3);
});
for (const scenario of ['http','network','unsafe-url']) {
  test(`curated fallback is identified after ${scenario} failure`, async ({ page }) => {
    await page.route(endpoint, route => scenario==='network'?route.abort():route.fulfill({
      status:scenario==='http'?403:200,
      json: {items:[{full_name:'evil/code',html_url:'javascript:alert(1)'}]}
    }));
    await page.goto('/');
    await expect(page.locator('#ai-highlights-status')).toContainText('Curated examples');
    await expect(page.locator('#ai-highlights-render-root .card')).toHaveCount(3);
    await expect(page.locator('#ai-highlights-render-root a[href^="javascript:"]')).toHaveCount(0);
  });
}

