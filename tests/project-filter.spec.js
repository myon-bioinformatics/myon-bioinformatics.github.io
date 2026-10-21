// @ts-check
const { test, expect } = require('@playwright/test');
const { repos } = require('../api/repos.json');
const projectCount = repos.length;

test.describe('Project tag filtering and search', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await page.locator('.project-topic-controls summary').click();
  });

  test('renders search input, topic tag buttons, and project count', async ({ page }) => {
    await expect(page.locator('#project-search-input')).toBeVisible();
    await expect(page.locator('#project-tags-filter')).toBeVisible();
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  });

  test('filters projects by tag button click', async ({ page }) => {
    const nmapBtn = page.locator('#project-tags-filter button[data-tag="nmap"]');
    await nmapBtn.click();

    await expect(nmapBtn).toHaveClass(/active/);
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .ui-card h3')).toContainText('python3nmap_GUI_for_Beginners');

    // Return to All
    const allBtn = page.locator('#project-tags-filter button[data-tag="all"]');
    await allBtn.click();
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  });

  test('filters projects by search input and clear button', async ({ page }) => {
    const searchInput = page.locator('#project-search-input');
    const clearBtn = page.locator('#project-search-clear');

    await searchInput.fill('scapy');
    await expect(clearBtn).toBeVisible();
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .ui-card h3')).toContainText('scapy_GUI_for_Beginners');

    await clearBtn.click();
    await expect(clearBtn).toBeHidden();
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  });

  test('shows empty state message when no projects match filter', async ({ page }) => {
    const searchInput = page.locator('#project-search-input');
    await searchInput.fill('nonexistentterm12345');

    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
    await expect(page.locator('.empty-projects-msg')).toBeVisible();
    await expect(page.locator('.empty-projects-msg')).toHaveText('No projects match your filter.');
  });

  test('clicking topic tag on a card filters projects', async ({ page }) => {
    const scapyBadge = page.locator('.project-topics .ui-tag[data-topic="scapy"]').first();
    await scapyBadge.click();

    await expect(page.locator('#project-tags-filter button[data-tag="scapy"]')).toHaveClass(/active/);
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(1);
  });

  test('clicking Copy URL button copies URL and gives visual feedback', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const firstCopyBtn = page.locator('#projects-render-root .project-copy').first();
    await firstCopyBtn.click();

    await expect(firstCopyBtn).toHaveText('Copied!');
    await expect(firstCopyBtn).toHaveClass(/copied/);
  });
});


test('combined search and tag filters persist through every display mode', async ({ page }) => {
  await page.route('https://api.github.com/search/repositories?*', route => route.fulfill({status:503,body:'{}'}));
  await page.goto('/');
  await page.locator('.project-topic-controls summary').click();
  await page.locator('#project-tags-filter button[data-tag="nmap"]').click();
  await page.locator('#project-search-input').fill('SCAPY');
  await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
  for (const mode of ['modern','github-like','xml-like','json','markdown']) {
    await page.selectOption('#view-mode-select', mode);
    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
    await page.locator('#project-search-clear').click();
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#project-tags-filter button[data-tag="nmap"]')).toHaveAttribute('aria-pressed','true');
    await page.locator('#project-search-input').fill('SCAPY');
  }
  await page.locator('#project-tags-filter button[data-tag="all"]').click();
  await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
});
