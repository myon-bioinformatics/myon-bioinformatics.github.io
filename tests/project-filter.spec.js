// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Project tag filtering and search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
  });

  test('renders search input, topic tag buttons, and project count', async ({ page }) => {
    await expect(page.locator('#project-search-input')).toBeVisible();
    await expect(page.locator('#project-tags-filter')).toBeVisible();
    await expect(page.locator('#projects-count')).toHaveText('Showing all 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(4);
  });

  test('filters projects by tag button click', async ({ page }) => {
    const securityBtn = page.locator('#project-tags-filter button[data-tag="security"]');
    await securityBtn.click();

    await expect(securityBtn).toHaveClass(/active/);
    await expect(page.locator('#projects-count')).toHaveText('Showing 1 of 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .card h3')).toContainText('python3nmap_GUI_for_Beginners');

    // Return to All
    const allBtn = page.locator('#project-tags-filter button[data-tag="all"]');
    await allBtn.click();
    await expect(page.locator('#projects-count')).toHaveText('Showing all 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(4);
  });

  test('filters projects by search input and clear button', async ({ page }) => {
    const searchInput = page.locator('#project-search-input');
    const clearBtn = page.locator('#project-search-clear');

    await searchInput.fill('scapy');
    await expect(clearBtn).toBeVisible();
    await expect(page.locator('#projects-count')).toHaveText('Showing 1 of 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .card h3')).toContainText('scapy_GUI_for_Beginners');

    await clearBtn.click();
    await expect(clearBtn).toBeHidden();
    await expect(page.locator('#projects-count')).toHaveText('Showing all 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(4);
  });

  test('shows empty state message when no projects match filter', async ({ page }) => {
    const searchInput = page.locator('#project-search-input');
    await searchInput.fill('nonexistentterm12345');

    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
    await expect(page.locator('.empty-projects-msg')).toBeVisible();
    await expect(page.locator('.empty-projects-msg')).toHaveText('No projects match your filter.');
  });

  test('clicking topic tag on a card filters projects', async ({ page }) => {
    const scapyBadge = page.locator('.badges .tag[data-topic="scapy"]').first();
    await scapyBadge.click();

    await expect(page.locator('#project-tags-filter button[data-tag="scapy"]')).toHaveClass(/active/);
    await expect(page.locator('#projects-count')).toHaveText('Showing 1 of 4 projects');
    await expect(page.locator('#projects-render-root .card')).toHaveCount(1);
  });

  test('clicking Copy URL button copies URL and gives visual feedback', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const firstCopyBtn = page.locator('#projects-render-root .copy-btn').first();
    await firstCopyBtn.click();

    await expect(firstCopyBtn).toHaveText('Copied!');
    await expect(firstCopyBtn).toHaveClass(/copied/);
  });
});
