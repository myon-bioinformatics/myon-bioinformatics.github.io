// @ts-check
const { test, expect } = require('@playwright/test');
const { createApng } = require('./apng-helper');
const path = require('path');
const fs = require('fs');

test.describe('Animated PNG generation', () => {
  test('captures interactive portfolio workflow and generates animated APNG', async ({ page }) => {
    const frames = [];

    await page.goto('/');
    await page.waitForLoadState('networkidle');
    frames.push(await page.screenshot({ type: 'png' }));

    // Step 1: Tag filter
    const securityBtn = page.locator('#project-tags-filter button[data-tag="security"]');
    if (await securityBtn.isVisible()) {
      await securityBtn.click();
      frames.push(await page.screenshot({ type: 'png' }));
    }

    // Step 2: Clear tag
    const allBtn = page.locator('#project-tags-filter button[data-tag="all"]');
    if (await allBtn.isVisible()) {
      await allBtn.click();
      frames.push(await page.screenshot({ type: 'png' }));
    }

    // Step 3: Shuffle AI highlights
    const refreshBtn = page.locator('#ai-highlights-refresh');
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      frames.push(await page.screenshot({ type: 'png' }));
    }

    expect(frames.length).toBeGreaterThanOrEqual(2);

    const outputPath = path.resolve(__dirname, '../test-results/portfolio_workflow.png');
    const resultBuf = createApng(frames, outputPath, 600);

    expect(resultBuf).not.toBeNull();
    expect(fs.existsSync(outputPath)).toBeTruthy();
    expect(resultBuf.includes(Buffer.from('acTL'))).toBeTruthy();
    expect(resultBuf.includes(Buffer.from('fcTL'))).toBeTruthy();
  });
});
