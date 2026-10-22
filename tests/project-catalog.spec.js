// @ts-check
const { test, expect } = require('@playwright/test');
const catalog = require('../api/repos.json');
const curated = require('../projects.json');
const modes = ['modern', 'github-like', 'xml-like', 'json', 'markdown'];

test.beforeEach(async ({ page }) => {
  await page.route('https://api.github.com/**', route => route.fulfill({ status: 503, body: '{}' }));
  await page.route('https://img.shields.io/**', route => route.abort());
});

test('every catalog repository is reachable in every display mode', async ({ page }) => {
  await page.goto('/');
  for (const mode of modes) {
    await page.selectOption('#view-mode-select', mode);
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${catalog.repos.length} projects`);
    const urls = await page.locator('#projects-render-root a').evaluateAll(links =>
      [...new Set(links.map(link => link.getAttribute('href')))].sort());
    expect(urls).toEqual(catalog.repos.map(repo => repo.url).sort());
  }
});

test('active projects appear before archived work and curated descriptions survive', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(catalog.repos.length);
  const titles = await page.locator('#projects-render-root .ui-card h3').allTextContents();
  const activeCount = catalog.repos.filter(repo => !repo.archived).length;
  expect(new Set(titles.slice(0, activeCount))).toEqual(new Set(catalog.repos.filter(repo => !repo.archived).map(repo => repo.name)));
  await expect(page.locator('#projects-render-root .project-status')).toHaveCount(catalog.repos.length - activeCount);
  const sample = curated[0];
  const card = page.locator('#projects-render-root .ui-card').filter({ has: page.getByRole('link', { name: sample.name, exact: true }) });
  await expect(card).toContainText(sample.desc);
});

test('status, topic and search combine and survive mode changes', async ({ page }) => {
  await page.goto('/');
  await page.selectOption('#project-status-filter', 'archived');
  const archived = catalog.repos.filter(repo => repo.archived).length;
  await expect(page.locator('#projects-count')).toHaveText(`Showing ${archived} of ${catalog.repos.length} projects`);
  await page.locator('.project-topic-controls summary').click();
  await page.locator('#project-tags-filter button[data-tag="nmap"]').click();
  await page.locator('#project-search-input').fill('PYTHON3NMAP');
  for (const mode of modes) {
    await page.selectOption('#view-mode-select', mode);
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${catalog.repos.length} projects`);
    await expect(page.locator('#projects-render-root')).toContainText('python3nmap_GUI_for_Beginners');
    await expect(page.locator('#project-status-filter')).toHaveValue('archived');
  }
  await page.selectOption('#project-status-filter', 'active');
  await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
});

test('a newly refreshed repository appears without a curated card', async ({ page }) => {
  const added = { name: 'Future-project', url: 'https://github.com/myon-bioinformatics/Future-project', description: null, readmeSummary: 'New README summary', topics: ['future-topic'] };
  await page.route('**/api/repos.json', route => route.fulfill({ json: { ...catalog, repos: [...catalog.repos, added] } }));
  await page.goto('/');
  await page.locator('#project-search-input').fill('future-topic');
  await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${catalog.repos.length + 1} projects`);
  await expect(page.locator('#projects-render-root')).toContainText('New README summary');
  await expect(page.locator('#projects-render-root h3 a')).toHaveAttribute('href', added.url);
});

test('curation cannot publish stale entries or override canonical URLs', async ({ page }) => {
  const repo = catalog.repos[0];
  await page.route('**/projects.json', route => route.fulfill({ json: [
    { name: repo.name, url: 'https://example.com/stale', desc: 'Curated text', topics: ['curated-topic'] },
    { name: 'Removed-repository', url: 'https://example.com/removed', desc: 'Stale entry' },
  ] }));
  await page.goto('/');
  await page.locator('#project-search-input').fill('curated-topic');
  await expect(page.locator('#projects-render-root h3 a')).toHaveAttribute('href', repo.url);
  await expect(page.locator('#projects-render-root')).toContainText('Curated text');
  await page.locator('#project-search-input').fill('Removed-repository');
  await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
});

test('unavailable curation still displays the complete public catalog', async ({ page }) => {
  await page.route('**/projects.json', route => route.fulfill({ status: 503, body: '{}' }));
  await page.goto('/');
  await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(catalog.repos.length);
});

test('search and status entered before the catalog loads are respected', async ({ page }) => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  await page.route('**/api/repos.json', async route => {
    await gate;
    await route.fulfill({ json: catalog });
  });
  await page.goto('/');
  await page.selectOption('#project-status-filter', 'archived');
  await page.locator('#project-search-input').fill('python3nmap');
  release();
  await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${catalog.repos.length} projects`);
  await expect(page.locator('#projects-render-root')).toContainText('python3nmap_GUI_for_Beginners');
  await expect(page.locator('#project-search-clear')).toBeVisible();
});

test('missing catalog reports an error instead of showing only curated projects', async ({ page }) => {
  await page.route('**/api/repos.json', route => route.fulfill({ status: 503, body: '{}' }));
  await page.goto('/');
  await expect(page.locator('#projects-render-root')).toHaveText('Failed to load projects. Please refresh.');
  await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(0);
});

test('the full catalog and expanded topics fit a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('.project-topic-controls summary').click();
  for (const mode of modes) {
    await page.selectOption('#view-mode-select', mode);
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${catalog.repos.length} projects`);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
});

test('vendored web-ui collection contract is loaded before project rendering', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(() => {
    const filter = window.WebUICollections.filterItems;
    return filter([
      { name: 'Aoi', topics: ['python'], archived: false },
      { name: 'Legacy', topics: ['python'], archived: true },
      { name: 'Other', topics: ['javascript'], archived: false },
    ], {
      query: 'PYTHON',
      text: item => [item.name, ...(item.topics || [])],
      facets: { archived: false, topic: 'python' },
      facetValues: { topic: item => item.topics },
    }).map(item => item.name);
  });
  expect(result).toEqual(['Aoi']);
});
