// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const CONFIG_PATH = path.resolve(__dirname, '../site.config.json');

function writeConfig(mode) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: mode }));
}

function resetConfig() {
  writeConfig('modern');
}

async function loadFresh(page, configMode = 'modern') {
  writeConfig(configMode);
  await page.context().clearCookies();
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  writeConfig(configMode);
  await page.reload();
  await page.waitForLoadState('networkidle');
  return page.locator('body').getAttribute('data-view-mode');
}

async function selectMode(page, mode) {
  await page.locator('#view-mode-select').selectOption(mode);
  await expect(page.locator('body')).toHaveAttribute('data-view-mode', mode);
}

test('applies default modern mode on first visit', async ({ page }) => {
  const mode = await loadFresh(page, 'modern');
  expect(mode).toBe('modern');
});

test.describe('site.config.json is respected when localStorage is empty', () => {
  for (const configMode of ['xml-like', 'json', 'markdown', 'github-like']) {
    test(`config defaultViewMode="${configMode}" is applied`, async ({ page }) => {
      const mode = await loadFresh(page, configMode);
      expect(mode).toBe(configMode);
    });
  }
});

test('dropdown change updates mode and renderer immediately', async ({ page }) => {
  await loadFresh(page, 'modern');
  await expect(page.locator('#profile-render-root')).toHaveAttribute('data-renderer', 'web');

  await selectMode(page, 'markdown');
  await expect(page.locator('#profile-render-root')).toHaveAttribute('data-renderer', 'markdown');

  await selectMode(page, 'json');
  await expect(page.locator('#projects-render-root')).toHaveAttribute('data-renderer', 'json');
});

test('selected mode is saved to localStorage', async ({ page }) => {
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('json');

  expect(await page.evaluate(() => localStorage.getItem('site:view-mode'))).toBe('json');
  expect(await page.evaluate(() => localStorage.getItem('site:view-mode-base'))).toBe('modern');
});

test('localStorage value is restored on reload', async ({ page }) => {
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('github-like');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).toHaveAttribute('data-view-mode', 'github-like');
});

test('site.config.json change overrides stale localStorage on next load', async ({ page }) => {
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('xml-like');
  writeConfig('json');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).toHaveAttribute('data-view-mode', 'json');
});

test('user choice persists on reload when config has not changed', async ({ page }) => {
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('markdown');
  await page.reload();
  await page.waitForLoadState('networkidle');
  await expect(page.locator('body')).toHaveAttribute('data-view-mode', 'markdown');
});

test('invalid config defaultViewMode falls back to modern', async ({ page }) => {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: 'totally-invalid' }));
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: 'totally-invalid' }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  resetConfig();
  await expect(page.locator('body')).toHaveAttribute('data-view-mode', 'modern');
});

test('modern keeps tabs, skill bars, career timeline, and project cards', async ({ page }) => {
  await loadFresh(page, 'modern');
  await expect(page.locator('#profile-render-root[data-renderer="web"] .tabs')).toBeVisible();
  await expect(page.locator('.skill-bar-fill')).toHaveCount(11);
  await expect(page.locator('.timeline-item')).toHaveCount(4);
  await expect(page.locator('#projects-render-root[data-renderer="web"] .card')).toHaveCount(4);
});

test('github-like keeps the web-oriented renderer', async ({ page }) => {
  await loadFresh(page, 'github-like');
  await expect(page.locator('#profile-render-root')).toHaveAttribute('data-renderer', 'web');
  await expect(page.locator('#projects-render-root .card')).toHaveCount(4);
});

test('xml-like renders nested tag-style profile and project structures', async ({ page }) => {
  await loadFresh(page, 'xml-like');
  const profile = page.locator('#profile-render-root');
  const projects = page.locator('#projects-render-root');
  await expect(profile).toHaveAttribute('data-renderer', 'xml');
  await expect(profile).toContainText('<Profile>');
  await expect(profile).toContainText('<About>');
  await expect(profile).toContainText('<Skills>');
  await expect(profile).toContainText('<Career>');
  await expect(projects).toContainText('<Projects>');
  await expect(projects.locator('a').first()).toHaveAttribute('href', /github\.com\/myon-bioinformatics/);
});

test('json mode renders object and array syntax with clickable URLs', async ({ page }) => {
  await loadFresh(page, 'json');
  const profile = page.locator('#profile-render-root');
  const projects = page.locator('#projects-render-root');
  await expect(profile).toHaveAttribute('data-renderer', 'json');
  await expect(profile).toContainText('"about":');
  await expect(profile).toContainText('"skills":');
  await expect(projects).toContainText('"name":');
  await expect(projects.locator('a').first()).toHaveAttribute('href', /github\.com\/myon-bioinformatics/);
});

test('markdown mode renders document headings, lists, and links', async ({ page }) => {
  await loadFresh(page, 'markdown');
  const profile = page.locator('#profile-render-root');
  const projects = page.locator('#projects-render-root');
  await expect(profile).toHaveAttribute('data-renderer', 'markdown');
  await expect(profile).toContainText('### About');
  await expect(profile).toContainText('### Skills');
  await expect(profile.locator('ul').first()).toBeVisible();
  await expect(projects.locator('h3 a').first()).toHaveAttribute('href', /github\.com\/myon-bioinformatics/);
});

test('all modes render the same shared profile and project data', async ({ page }) => {
  await loadFresh(page, 'modern');

  for (const mode of ['modern', 'xml-like', 'json', 'markdown', 'github-like']) {
    await selectMode(page, mode);
    await expect(page.locator('#profile-render-root')).toContainText('Bioinformatics');
    await expect(page.locator('#projects-render-root')).toContainText('python3nmap_GUI_for_Beginners');
  }
});

test.afterAll(() => {
  resetConfig();
});
