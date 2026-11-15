// @ts-check
const { test, expect, MODES: modes } = require('./portfolio-test');
const fs = require('fs');
const path = require('path');
const catalog = require('../api/repos.json');
const curated = require('../projects.json');
const profile = require('../profile.json');

// Only public, non-archived repositories are displayed across the portfolio.
const active = catalog.repos.filter(repo => !repo.archived);
const projectCount = active.length;
const skillCount = profile.skills.reduce((total, group) => total + group.items.length, 0);

const CONFIG_PATH = path.resolve(
  __dirname,
  '../.generated-site/site.config.json'
);

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

// ═══ 🧭 Catalog discovery & active repository visibility ═══════════════════════════════════════════════════

test.describe('Catalog discovery and active repository visibility', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('https://api.github.com/**', route => route.fulfill({ status: 503, body: '{}' }));
    await page.route('https://img.shields.io/**', route => route.abort());
  });

  test('every active catalog repository is reachable in every display mode', async ({ page }) => {
    await page.goto('/');
    for (const mode of modes) {
      await page.selectOption('#view-mode-select', mode);
      await expect(page.locator('#projects-count')).toHaveText(`Showing all ${active.length} projects`);
      const urls = await page.locator('#projects-render-root a').evaluateAll(links =>
        [...new Set(links.map(link => link.getAttribute('href')))].sort()
      );
      expect(urls).toEqual(active.map(repo => repo.url).sort());
    }
  });

  test('only active repositories are displayed, and curated descriptions survive', async ({ page }) => {
    await page.goto('/');
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(active.length);
    const titles = await page.locator('#projects-render-root .ui-card h3').allTextContents();
    expect(new Set(titles)).toEqual(new Set(active.map(repo => repo.name)));
    await expect(page.locator('#projects-render-root .project-status')).toHaveCount(0);
    const sample = curated.find(project => active.some(repo => repo.name === project.name));
    const card = page.locator('#projects-render-root .ui-card').filter({ has: page.getByRole('link', { name: sample.name, exact: true }) });
    await expect(card).toContainText(sample.desc);
  });

  test('archived repositories are never displayed, even when the catalog contains them', async ({ page }) => {
    const legacy = { name: 'Legacy-archived', url: 'https://github.com/myon-bioinformatics/Legacy-archived', description: 'Old work', archived: true, topics: ['legacy-topic'] };
    await page.route('**/api/repos.json', route => route.fulfill({ json: { ...catalog, repos: [...catalog.repos, legacy] } }));
    await page.goto('/');
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${active.length} projects`);
    await page.locator('#project-search-input').fill('legacy-topic');
    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
  });

  test('topic and search combine and survive mode changes', async ({ page }) => {
    await page.goto('/');
    await page.locator('.project-topic-controls summary').click();
    await page.locator('#project-tags-filter button[data-tag="nvd"]').click();
    await page.locator('#project-search-input').fill('NVD_NIST');
    for (const mode of modes) {
      await page.selectOption('#view-mode-select', mode);
      await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${active.length} projects`);
      await expect(page.locator('#projects-render-root')).toContainText('nvd_nist_known_vulns');
    }
    await page.locator('#project-search-input').fill('no-such-project-term');
    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
  });

  test('a newly refreshed repository appears without a curated card', async ({ page }) => {
    const added = { name: 'Future-project', url: 'https://github.com/myon-bioinformatics/Future-project', description: null, readmeSummary: 'New README summary', topics: ['future-topic'] };
    await page.route('**/api/repos.json', route => route.fulfill({ json: { ...catalog, repos: [...catalog.repos, added] } }));
    await page.goto('/');
    await page.locator('#project-search-input').fill('future-topic');
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${active.length + 1} projects`);
    await expect(page.locator('#projects-render-root')).toContainText('New README summary');
    await expect(page.locator('#projects-render-root h3 a')).toHaveAttribute('href', added.url);
  });

  test('curation cannot publish stale entries or override canonical URLs', async ({ page }) => {
    const repo = active[0];
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

  test('unavailable curation still displays the complete active catalog', async ({ page }) => {
    await page.route('**/projects.json', route => route.fulfill({ status: 503, body: '{}' }));
    await page.goto('/');
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(active.length);
  });

  test('search entered before the catalog loads is respected', async ({ page }) => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/repos.json', async route => {
      await gate;
      await route.fulfill({ json: catalog });
    });
    await page.goto('/');
    await page.locator('#project-search-input').fill('nvd_nist');
    release();
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${active.length} projects`);
    await expect(page.locator('#projects-render-root')).toContainText('nvd_nist_known_vulns');
    await expect(page.locator('#project-search-clear')).toBeVisible();
  });

  test('missing catalog reports an error instead of showing only curated projects', async ({ page }) => {
    await page.route('**/api/repos.json', route => route.fulfill({ status: 503, body: '{}' }));
    await page.goto('/');
    await expect(page.locator('#projects-render-root')).toHaveText('Failed to load projects. Please refresh.');
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(0);
  });

  test('the full active catalog and expanded topics fit a mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.locator('.project-topic-controls summary').click();
    for (const mode of modes) {
      await page.selectOption('#view-mode-select', mode);
      await expect(page.locator('#projects-count')).toHaveText(`Showing all ${active.length} projects`);
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
});

// ═══ 🏷️ Project tag filtering and search ═════════════════════════════════════════════════════════════════════

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
    const cveBtn = page.locator('#project-tags-filter button[data-tag="nvd"]');
    await cveBtn.click();

    await expect(cveBtn).toHaveClass(/active/);
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .ui-card h3')).toContainText('nvd_nist_known_vulns');

    const allBtn = page.locator('#project-tags-filter button[data-tag="all"]');
    await allBtn.click();
    await expect(page.locator('#projects-count')).toHaveText(`Showing all ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  });

  test('filters projects by search input and clear button', async ({ page }) => {
    const searchInput = page.locator('#project-search-input');
    const clearBtn = page.locator('#project-search-clear');

    await searchInput.fill('nvd_nist');
    await expect(clearBtn).toBeVisible();
    await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(1);
    await expect(page.locator('#projects-render-root .ui-card h3')).toContainText('nvd_nist_known_vulns');

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
    const badge = page.locator('.project-topics .ui-tag[data-topic]').first();
    const topic = await badge.getAttribute('data-topic');
    if (!topic) throw new Error('Expected a rendered project topic');
    const expectedNames = active.filter(repo =>
      [...(repo.topics || []), ...(curated.find(project => project.name === repo.name)?.topics || [])]
        .includes(topic)).map(repo => repo.name).sort();
    expect(expectedNames.length).toBeGreaterThan(0);
    await badge.click();

    await expect(page.locator(`#project-tags-filter button[data-tag=${JSON.stringify(topic)}]`))
      .toHaveAttribute('aria-pressed', 'true');
    await expect(page.locator('#projects-count')).toHaveText(expectedNames.length === projectCount
      ? `Showing all ${projectCount} projects`
      : `Showing ${expectedNames.length} of ${projectCount} projects`);
    const titles = page.locator('#projects-render-root .ui-card h3');
    await expect(titles).toHaveCount(expectedNames.length);
    expect((await titles.allTextContents()).sort()).toEqual(expectedNames);
  });

  test('clicking Copy URL button copies URL and gives visual feedback', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write']);
    const firstCopyBtn = page.locator('#projects-render-root .project-copy').first();
    await firstCopyBtn.click();

    await expect(firstCopyBtn).toHaveText('Copied!');
    await expect(firstCopyBtn).toHaveClass(/copied/);
  });

  test('combined search and tag filters persist through every display mode', async ({ page }) => {
    await page.route('https://api.github.com/search/repositories?*', route => route.fulfill({ status: 503, body: '{}' }));
    await page.goto('/');
    await page.locator('.project-topic-controls summary').click();
    await page.locator('#project-tags-filter button[data-tag="nvd"]').click();
    await page.locator('#project-search-input').fill('SCAPY');
    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
    for (const mode of modes) {
      await page.selectOption('#view-mode-select', mode);
      await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
      await page.locator('#project-search-clear').click();
      await expect(page.locator('#projects-count')).toHaveText(`Showing 1 of ${projectCount} projects`);
      await expect(page.locator('#project-tags-filter button[data-tag="nvd"]')).toHaveAttribute('aria-pressed', 'true');
      await page.locator('#project-search-input').fill('SCAPY');
    }
    await page.locator('#project-tags-filter button[data-tag="all"]').click();
    await expect(page.locator('#projects-count')).toHaveText('No matching projects found.');
  });
});

// ═══ 🎨 Shared UI theme and controls ═════════════════════════════════════════════════════════════════════════

test.describe('Shared UI theme and controls', () => {
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
});

// ═══ 👁️ View mode switching and layout contracts ═════════════════════════════════════════════════════════════

test.describe('View mode switching and layout contracts', () => {
  test('applies default modern mode on first visit', async ({ page }) => {
    const mode = await loadFresh(page, 'modern');
    expect(mode).toBe('modern');
  });

  for (const configMode of modes) {
    test(`config defaultViewMode="${configMode}" is applied`, async ({ page }) => {
      const mode = await loadFresh(page, configMode);
      expect(mode).toBe(configMode);
    });
  }

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
    await expect(page.locator('.skill-bar-fill')).toHaveCount(skillCount);
    await expect(page.locator('.timeline-item')).toHaveCount(profile.career.length);
    await expect(page.locator('#projects-render-root[data-renderer="web"] .ui-card')).toHaveCount(projectCount);

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
    await expect(page.locator('#projects-render-root .ui-card')).toHaveCount(projectCount);
  });

  for (const width of [390, 1280]) {
    test(`career matches the canonical profile across modes at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await loadFresh(page, 'modern');
      const currentActivity = profile.career.find(entry => entry.year === '2026–');
      expect(currentActivity).toBeDefined();

      for (const mode of modes) {
        await selectMode(page, mode);
        const root = page.locator('#profile-render-root');
        if (mode === 'modern' || mode === 'github-like') {
          await root.getByRole('tab', { name: /Career/ }).click();
          const items = root.locator('.timeline-item');
          await expect(items).toHaveCount(profile.career.length);
          await expect(items.locator('.tl-year')).toHaveText(profile.career.map(entry => entry.year));
          await expect(items.locator('.tl-body strong')).toHaveText(profile.career.map(entry => entry.title));
          const currentItem = items.filter({ has: page.locator('.tl-year', { hasText: currentActivity.year }) });
          await expect(currentItem.locator('.tl-year')).toBeVisible();
          await expect(currentItem.locator('.tl-body strong')).toBeVisible();
        } else if (mode === 'xml-like') {
          await expect(root.locator('.xml-tag').filter({ hasText: /^<Entry year=/ }))
            .toHaveCount(profile.career.length);
        } else if (mode === 'markdown') {
          await expect(root.locator('h3:has-text("### Career") + ul > li'))
            .toHaveCount(profile.career.length);
        } else {
          expect(JSON.parse(await root.textContent()).career).toEqual(profile.career);
        }
        await expect(root).toContainText(currentActivity.year);
        await expect(root).toContainText(currentActivity.title);
      }
    });
  }

  test('xml-like renders nested tag-style profile and project structures', async ({ page }) => {
    await loadFresh(page, 'xml-like');
    const p = page.locator('#profile-render-root');
    const projects = page.locator('#projects-render-root');
    await expect(p).toHaveAttribute('data-renderer', 'xml');
    await expect(p).toContainText('<Profile>');
    await expect(p).toContainText('<About>');
    await expect(p).toContainText('<Skills>');
    await expect(p).toContainText('<Career>');
    await expect(projects).toContainText('<Projects>');
    await expect(projects.locator('a').first()).toHaveAttribute('href', /github\.com\/myon-bioinformatics/);
  });

  test('json mode renders object and array syntax with clickable URLs', async ({ page }) => {
    await loadFresh(page, 'json');
    const p = page.locator('#profile-render-root');
    const projects = page.locator('#projects-render-root');
    await expect(p).toHaveAttribute('data-renderer', 'json');
    await expect(p).toContainText('"about":');
    await expect(p).toContainText('"skills":');
    await expect(projects).toContainText('"name":');
    await expect(projects.locator('a').first()).toHaveAttribute('href', /github\.com\/myon-bioinformatics/);
  });

  test('markdown mode renders document headings, lists, and links', async ({ page }) => {
    await loadFresh(page, 'markdown');
    const p = page.locator('#profile-render-root');
    const projects = page.locator('#projects-render-root');
    await expect(p).toHaveAttribute('data-renderer', 'markdown');
    await expect(p).toContainText('### About');
    await expect(p).toContainText('### Skills');
    await expect(p.locator('ul').first()).toBeVisible();
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

    const xmlTagColor = await page.locator('.xml-tag').first().evaluate(node => getComputedStyle(node).color);
    await selectMode(page, 'json');
    const jsonPunctuationColor = await page.locator('.json-punctuation').first().evaluate(node => getComputedStyle(node).color);
    await selectMode(page, 'markdown');
    const markdownHeadingColor = await page.locator('.md-heading').first().evaluate(node => getComputedStyle(node).color);

    expect(xmlTagColor).not.toBe('');
    expect(jsonPunctuationColor).not.toBe('');
    expect(markdownHeadingColor).not.toBe('');
  });

  test('reduced motion disables visible card movement', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await loadFresh(page, 'modern');
    const transitionDuration = await page.locator('.card').first().evaluate(node => getComputedStyle(node).transitionDuration);
    const seconds = parseFloat(transitionDuration);
    expect(seconds === 0 || seconds <= 0.0001 || transitionDuration.includes('1e-05s') || transitionDuration.includes('0.00001s')).toBeTruthy();
  });

  test('all modes render the same shared profile and project data', async ({ page }) => {
    await loadFresh(page, 'modern');

    for (const mode of modes) {
      await selectMode(page, mode);
      await expect(page.locator('#profile-render-root')).toContainText('Bioinformatics');
      await expect(page.locator('#projects-render-root')).toContainText('nvd_nist_known_vulns');
    }
  });

  test.afterAll(() => {
    resetConfig();
  });
});
