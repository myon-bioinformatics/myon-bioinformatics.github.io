// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const CONFIG_PATH = path.resolve(__dirname, '../site.config.json');

function writeConfig(mode) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: mode }));
}

function resetConfig() {
  writeConfig('xml-like');
}

async function loadFresh(page, configMode = 'xml-like') {
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

test('applies default xml-like mode on first visit', async ({ page }) => {
  const mode = await loadFresh(page, 'xml-like');
  expect(mode).toBe('xml-like');
});

test.describe('site.config.json is respected when localStorage is empty', () => {
  for (const configMode of ['modern', 'xml-like', 'json', 'markdown', 'github-like']) {
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

test('modern keeps web behavior while using terminal-inspired presentation', async ({ page }) => {
  await loadFresh(page, 'modern');
  await expect(page.locator('#profile-render-root[data-renderer="web"] .tabs')).toBeVisible();
  await expect(page.locator('.skill-bar-fill')).toHaveCount(11);
  await expect(page.locator('.timeline-item')).toHaveCount(4);
  await expect(page.locator('#projects-render-root[data-renderer="web"] .card')).toHaveCount(4);

  const modernStyles = await page.evaluate(() => {
    const body = getComputedStyle(document.body);
    const card = getComputedStyle(document.querySelector('.card'));
    return {
      fontFamily: body.fontFamily,
      background: body.backgroundColor,
      cardRadius: card.borderRadius,
    };
  });
  expect(modernStyles.fontFamily.toLowerCase()).toContain('monospace');
  expect(modernStyles.cardRadius).toBe('0px');

  await selectMode(page, 'github-like');
  const githubBackground = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(githubBackground).not.toBe(modernStyles.background);
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

test('notation syntax colors are defined through CSS variables', async ({ page }) => {
  await loadFresh(page, 'xml-like');
  const variables = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    return {
      xml: root.getPropertyValue('--syntax-xml').trim(),
      jsonPunctuation: root.getPropertyValue('--syntax-json-punctuation').trim(),
      markdownMarker: root.getPropertyValue('--syntax-markdown-marker').trim(),
    };
  });
  expect(variables.xml).not.toBe('');
  expect(variables.jsonPunctuation).not.toBe('');
  expect(variables.markdownMarker).not.toBe('');

  const xmlTagColor = await page.locator('.xml-tag').first().evaluate((node) => getComputedStyle(node).color);
  await selectMode(page, 'json');
  const jsonPunctuationColor = await page.locator('.json-punctuation').first().evaluate((node) => getComputedStyle(node).color);
  await selectMode(page, 'markdown');
  const markdownHeadingColor = await page.locator('.md-heading').first().evaluate((node) => getComputedStyle(node).color);

  expect(xmlTagColor).not.toBe('');
  expect(jsonPunctuationColor).not.toBe('');
  expect(markdownHeadingColor).not.toBe('');
});

test('reduced motion disables visible card movement', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await loadFresh(page, 'modern');
  const transitionDuration = await page.locator('.card').first().evaluate((node) => getComputedStyle(node).transitionDuration);
  expect(transitionDuration === '0s' || transitionDuration === '0.00001s').toBeTruthy();
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
