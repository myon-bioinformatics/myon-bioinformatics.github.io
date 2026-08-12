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

// ── helpers ───────────────────────────────────────────────────────────────────

/** Load the page with a clean localStorage and return the body dataset value */
async function loadFresh(page, configMode = 'modern') {
  writeConfig(configMode);
  await page.context().clearCookies();
  // Clear localStorage via CDP / evaluate before navigation
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  // Reload so the JS runs with an empty store
  writeConfig(configMode);
  await page.reload();
  await page.waitForLoadState('networkidle');
  return page.locator('body').getAttribute('data-view-mode');
}

// ── Test 1: default mode (modern) applied when localStorage is empty ──────────
test('applies default modern mode on first visit', async ({ page }) => {
  const mode = await loadFresh(page, 'modern');
  expect(mode).toBe('modern');
});

// ── Test 2: site.config.json value is respected when no localStorage ──────────
test.describe('site.config.json is respected when localStorage is empty', () => {
  for (const configMode of ['xml-like', 'json', 'markdown', 'github-like']) {
    test(`config defaultViewMode="${configMode}" is applied`, async ({ page }) => {
      const mode = await loadFresh(page, configMode);
      expect(mode).toBe(configMode);
    });
  }
});

// ── Test 3: dropdown changes the view mode immediately ────────────────────────
test('dropdown change updates body data-view-mode immediately', async ({ page }) => {
  await loadFresh(page, 'modern');

  const select = page.locator('#view-mode-select');
  await select.selectOption('markdown');

  const mode = await page.locator('body').getAttribute('data-view-mode');
  expect(mode).toBe('markdown');
});

// ── Test 4: selection is persisted to localStorage ────────────────────────────
test('selected mode is saved to localStorage', async ({ page }) => {
  await loadFresh(page, 'modern');

  await page.locator('#view-mode-select').selectOption('json');

  const stored = await page.evaluate(() => localStorage.getItem('site:view-mode'));
  expect(stored).toBe('json');
  // base key must be set to the current config value so stale detection works
  const base = await page.evaluate(() => localStorage.getItem('site:view-mode-base'));
  expect(base).toBe('modern');
});

// ── Test 5: localStorage value survives reload ────────────────────────────────
test('localStorage value is restored on reload', async ({ page }) => {
  await loadFresh(page, 'modern');

  await page.locator('#view-mode-select').selectOption('github-like');
  await page.reload();
  await page.waitForLoadState('networkidle');

  const mode = await page.locator('body').getAttribute('data-view-mode');
  expect(mode).toBe('github-like');
});

// ── Test 6 (FIXED): site.config.json change overrides stale localStorage ──────
// When site.config.json changes its defaultViewMode, the user's previously
// stored choice is treated as stale and the new config value takes effect.
test('site.config.json change overrides stale localStorage on next load', async ({ page }) => {
  // Step 1 – user visits with config=modern, picks xml-like, stored in localStorage
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('xml-like');

  // Step 2 – admin changes site.config.json to "json"
  writeConfig('json');

  // Step 3 – user reloads; the new config value should be active
  await page.reload();
  await page.waitForLoadState('networkidle');

  const mode = await page.locator('body').getAttribute('data-view-mode');
  expect(mode).toBe('json');
});

// ── Test 7: user choice persists across reloads when config is unchanged ──────
test('user choice persists on reload when config has not changed', async ({ page }) => {
  await loadFresh(page, 'modern');
  await page.locator('#view-mode-select').selectOption('markdown');

  // Config stays "modern" — user's choice should survive reload
  await page.reload();
  await page.waitForLoadState('networkidle');

  const mode = await page.locator('body').getAttribute('data-view-mode');
  expect(mode).toBe('markdown');
});

// ── Test 7: unknown config value falls back to modern ─────────────────────────
test('invalid config defaultViewMode falls back to modern', async ({ page }) => {
  // Write an invalid value
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: 'totally-invalid' }));
  await page.goto('/');
  await page.evaluate(() => localStorage.clear());
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ defaultViewMode: 'totally-invalid' }));
  await page.reload();
  await page.waitForLoadState('networkidle');
  resetConfig();

  const mode = await page.locator('body').getAttribute('data-view-mode');
  expect(mode).toBe('modern');
});

// ── Cleanup ───────────────────────────────────────────────────────────────────
test.afterAll(() => {
  resetConfig();
});
