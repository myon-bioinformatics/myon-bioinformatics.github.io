// @ts-check
const { test, expect } = require('@playwright/test');
const { EventEmitter } = require('node:events');
const fixtures = require('./fixtures/pixiv-markup.json');

const niconicoEndpoint = 'https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search?*';

function trackExternalRequests(page, baseURL) {
  const external = [], siteOrigin = new URL(baseURL).origin;
  page.on('request', request => {
    if (new URL(request.url()).origin !== siteOrigin) external.push(request.url());
  });
  return external;
}

// 🔌 Where the lab and the import are: framed #panels of the one screen (tools/#mcp, tools/#html-import) in this source;
// the published run (HTML_TOOL_BASE_URL) goes wherever the deployed front page points, since a pull request that moves
// them is published only after it merges. 🖼️ A framed app's view is a route inside its frame; 📄 a page of its own is the page.
let LAB = '/tools/#mcp', IMPORT = '/tools/#html-import', f;
async function open(page, at, view) {
  const { pathname, hash } = new URL(at, 'http://site'), name = hash.slice(1);
  if (!name) { await page.goto(pathname + (view ? '#' + view : '')); return page.mainFrame(); }
  const here = new URL(page.url());
  if (here.pathname !== pathname || here.hash !== hash) await page.goto(at);
  await page.waitForFunction(n => document.querySelector(`#${n} iframe`)?.dataset.ready, name);
  const inner = await (await page.locator(`#${name} iframe`).elementHandle()).contentFrame();
  if (view) await inner.evaluate(v => { location.hash = v; }, view);
  return inner;
}
const lab = (page, view) => open(page, LAB, view);
test.beforeAll(async ({ browser }) => {
  if (!process.env.HTML_TOOL_BASE_URL) return;
  const page = await browser.newPage();
  await page.goto(new URL('/', process.env.HTML_TOOL_BASE_URL).href);
  const at = async (links, fallback) => {          // 🔗 by place (before or after the move), whatever 🌐 the words say
    const url = new URL(await page.locator(links).first().getAttribute('href') || fallback, page.url());
    return url.pathname + url.hash;
  };
  [LAB, IMPORT] = [await at('a[href="./tools/#mcp"], a[href="./tools/mcp/"]', LAB),
                   await at('a[href="./tools/#html-import"], a[href="./tools/html-import/"]', IMPORT)];
  await page.close();
});

test.describe('MCP Tool Call Lab - Publication, navigation, and extraction', () => {
  test('transferred Pixiv extraction remains functional without upstream fetch', async ({ page }) => {
    f = await lab(page, 'pixiv');
    await expect(f.locator('[data-pages-view="pixiv"]')).toBeVisible();
    await f.locator('#pages-pixiv-title').fill('Demo');
    await f.locator('#pages-pixiv-source-text').fill('Example original source text');
    await f.locator('[data-testid="pages-pixiv-extract-submit"]').click();
    await expect(f.locator('[data-testid="pages-pixiv-extract"]')).toContainText('Example original source text');
    f = await lab(page, 'wiki');
    await expect(f.locator('#pages-wiki-form')).toBeVisible();
    await expect(f.locator('[data-pages-view="pixiv"]')).toBeHidden();
  });

  for (const mobile of [false, true]) {
    test.describe(mobile ? 'mobile shared lab UI' : 'desktop shared lab UI', () => {
      test.use({
        viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
        isMobile: mobile,
        hasTouch: mobile,
      });

      test('shared fonts and navigation preserve Pixiv and cached Wikipedia extraction', async ({ page, context }, info) => {
        f = await open(page, IMPORT);
        const reference = await f.locator('body').evaluate(e => {
          const s = getComputedStyle(e);
          return { font: s.fontFamily, size: s.fontSize, color: s.color, background: s.backgroundColor };
        });
        let fetches = 0;
        await context.route('https://en.wikipedia.org/w/api.php?*', async route => {
          fetches++;
          await route.fulfill({
            contentType: 'application/json',
            headers: { 'access-control-allow-origin': '*' },
            body: JSON.stringify({ query: { pages: { 1: { title: 'Demo', extract: 'Introduction\n== History ==\nHistory body\n== Geography ==\nGeography body' } } } }),
          });
        });
        f = await lab(page, 'pixiv');
        await expect(f.locator('[data-pages-view="pixiv"]')).toBeVisible();
        const actual = await f.locator('body').evaluate(e => {
          const s = getComputedStyle(e);
          return { font: s.fontFamily, size: s.fontSize, color: s.color, background: s.backgroundColor };
        });
        expect(actual).toEqual(reference);
        await f.locator('#pages-pixiv-title').fill('Demo');
        await f.locator('#pages-pixiv-source-text').fill('Example original source text');
        await f.getByTestId('pages-pixiv-extract-submit').click();
        await expect(f.getByTestId('pages-pixiv-extract')).toContainText('Example original source text');
        expect(await f.getByTestId('pages-pixiv-extract').evaluate(e => getComputedStyle(e).fontFamily)).toBe(reference.font);
        await context.route('https://dic.pixiv.net/a/Demo', route => route.fulfill({ contentType: 'text/html', body: '<h1>Demo article</h1>' }));
        const next = context.waitForEvent('page');
        await f.getByTestId('pages-pixiv-open-article').click();
        const popup = await next;
        await popup.waitForLoadState();
        expect(popup.url()).toBe('https://dic.pixiv.net/a/Demo');
        expect(await popup.evaluate(() => window.opener)).toBeNull();
        await popup.close();
        await f.getByTestId('pages-nav-wiki').click();
        await expect(f.locator('[data-pages-view="wiki"]')).toBeVisible();
        await expect(f.locator('[data-pages-view="pixiv"]')).toBeHidden();
        await f.locator('#pages-wiki-title').fill('Demo');
        await f.getByTestId('pages-wiki-fetch').click();
        await expect(f.getByTestId('pages-wiki-extract')).toContainText('History body');
        await f.locator('#pages-wiki-heading').selectOption({ label: '## History' });
        await expect(f.getByTestId('pages-wiki-extract')).toHaveText('History body');
        expect(fetches).toBe(1);
        expect(await f.locator('#pages-wiki-heading').evaluate(e => getComputedStyle(e).colorScheme)).toBe('dark');
        await f.getByTestId('pages-nav-pixiv').click();
        await expect(f.locator('[data-pages-view="pixiv"]')).toBeVisible();
        await expect(f.getByTestId('pages-pixiv-extract')).toContainText('Example original source text');
        expect(await f.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: info.outputPath('shared-lab-ui.png'), fullPage: true });
      });
    });
  }

  test('execution links and empty Wiki examples remain usable', async ({ page }) => {
    // The source pins the place (tools/#mcp-execution, a panel of the one screen); the published run (HTML_TOOL_BASE_URL) checks the
    // deployed pages agree with each other, since a pull request that moves the lab is published only after it merges.
    // 🔗 By place, whatever 🌐 the words say: the front's link (site-relative or absolute) and the lab's lead to one place.
    const place = href => { const url = new URL(href, 'https://myon-bioinformatics.github.io'); return url.pathname + url.hash; };
    await page.goto('/');
    const execution = place(await page.locator('a[href$="#mcp-execution"]').first().getAttribute('href'));
    if (!process.env.HTML_TOOL_BASE_URL) expect(execution).toBe('/tools/#mcp-execution');
    f = await lab(page, 'wiki');
    // 🖼️ Inside its frame the lab's link is site-relative (any origin) and leaves the frame: the same place as the front's.
    expect(place(await f.getByTestId('lab-execution-link').getAttribute('href'))).toBe(execution);
    await expect(f.getByTestId('pages-wiki-title')).toHaveValue('');
    await f.getByTestId('pages-wiki-fetch').click();
    await expect(f.getByTestId('pages-wiki-error')).toContainText('Enter a Wikipedia title.');
  });

  test('lab Pokémon tab fetches PokéAPI and accepts pasted JSON', async ({ page }) => {
    const ditto = {
      id: 132,
      name: 'ditto',
      height: 3,
      weight: 40,
      base_experience: 101,
      types: [{ slot: 1, type: { name: 'normal' } }],
      abilities: [
        { slot: 1, is_hidden: false, ability: { name: 'limber' } },
        { slot: 3, is_hidden: true, ability: { name: 'imposter' } },
      ],
      stats: [
        { base_stat: 48, stat: { name: 'hp' } },
        { base_stat: 48, stat: { name: 'attack' } },
        { base_stat: 48, stat: { name: 'defense' } },
        { base_stat: 48, stat: { name: 'special-attack' } },
        { base_stat: 48, stat: { name: 'special-defense' } },
        { base_stat: 48, stat: { name: 'speed' } },
      ],
    };
    await page.route('https://pokeapi.co/api/v2/pokemon/*', route =>
      route.fulfill({ contentType: 'application/json', body: JSON.stringify(ditto) })
    );
    f = await lab(page, 'pokemon');
    await expect(f.locator('[data-pages-view="pokemon"]')).toBeVisible();
    await f.locator('#pokemon-name').fill('ditto');
    await f.locator('[data-source-fetch]').click();
    await expect(f.locator('[data-source-output]')).toContainText('ditto (#132)');
    await expect(f.locator('[data-source-output]')).toContainText('normal');

    await f.locator('#pokemon-name').fill('');
    await f.locator('#pokemon-text').fill(JSON.stringify(ditto));
    await f.locator('[data-source-extract]').click();
    await expect(f.locator('[data-source-output]')).toContainText('ditto (#132)');
  });
});

test.describe('MCP Tool Call Lab - Pixiv heading navigation', () => {
  for (const mobile of [false, true]) {
    test.describe(mobile ? 'Pixiv mobile' : 'Pixiv desktop', () => {
      test.use({ viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 } });

      test('request guard ignores same-origin resources and records external origins', () => {
        for (const baseURL of ['http://localhost:8080', 'https://myon-bioinformatics.github.io']) {
          const probe = new EventEmitter();
          const external = trackExternalRequests(probe, baseURL), site = new URL(baseURL);
          for (const path of ['/tools/#mcp', '/assets/style.css?v=1', '/assets/app.js', '/assets/logo.png']) {
            probe.emit('request', { url: () => new URL(path, baseURL).href });
          }
          probe.emit('request', { url: () => `${baseURL.toUpperCase()}/probe` });
          if (site.protocol === 'https:') probe.emit('request', { url: () => `${baseURL}:443/probe` });
          expect(external).toEqual([]);
          const foreign = [
            'https://dic.pixiv.net/a/Demo',
            site.protocol === 'https:' ? 'http://localhost:8080/probe' : 'https://myon-bioinformatics.github.io/probe',
            `${site.protocol}//${site.hostname}.example.test${site.port ? `:${site.port}` : ''}/probe`,
            `${site.protocol === 'https:' ? 'http:' : 'https:'}//${site.host}/probe`,
            `${site.protocol}//${site.hostname}:8081/probe`,
          ];
          for (const url of foreign) probe.emit('request', { url: () => url });
          expect(external).toEqual(foreign);
        }
      });

      test('source headings select cached body and reset safely', async ({ page, baseURL }, info) => {
        const external = trackExternalRequests(page, baseURL), errors = [];
        page.on('pageerror', error => errors.push(error.message));
        f = await lab(page, 'pixiv');
        await f.getByTestId('pages-pixiv-source-text').fill(fixtures[0].source);
        await f.getByTestId('pages-pixiv-extract-submit').click();
        const select = f.locator('#pages-pixiv-heading'), output = f.getByTestId('pages-pixiv-extract');
        await expect(select.locator('option')).toHaveCount(7);
        await select.selectOption({ label: '# 世界観' });
        await expect(output).toContainText('## 文明描写');
        await expect(output).toContainText('## 社会構成');
        await expect(output).not.toContainText('関連イラスト');
        await select.selectOption({ label: '## 文明描写' });
        await expect(output).not.toContainText('社会構成');
        await select.selectOption('');
        await expect(output).toContainText('Title: 試験記事');
        await page.screenshot({ path: info.outputPath('pixiv-headings.png'), fullPage: true });
        await f.getByTestId('pages-pixiv-source-text').fill('*同名\nfirst\n*同名\n<script>window.pwned=true</script>');
        await f.getByTestId('pages-pixiv-extract-submit').click();
        await select.selectOption('1');
        await expect(output).toHaveText('<script>window.pwned=true</script>');
        expect(await f.evaluate(() => window.pwned)).toBeUndefined();
        await f.getByTestId('pages-pixiv-source-text').fill('No headings');
        await f.getByTestId('pages-pixiv-extract-submit').click();
        await expect(select).toBeDisabled();
        await expect(output).toContainText('No headings');
        await f.getByTestId('pages-pixiv-source-text').fill('');
        await f.getByTestId('pages-pixiv-extract-submit').click();
        await expect(output).toBeHidden();
        await expect(select.locator('option')).toHaveCount(1);
        await expect(f.getByTestId('pages-pixiv-error')).toBeVisible();
        expect(external).toEqual([]);
        expect(errors).toEqual([]);
        expect(await f.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      });
    });
  }
});

test.describe('MCP Tool Call Lab - Niconico search and error handling', () => {
  test.beforeEach(async ({ page }) => {
    f = await lab(page, 'niconico');
    await expect(f.getByTestId('pages-niconico')).toBeVisible();
  });

  test('search sends encoded query and sort, renders safe result links', async ({ page }) => {
    await page.route(niconicoEndpoint, async route => {
      const params = new URL(route.request().url()).searchParams;
      expect(params.get('q')).toBe('初音ミク & test');
      expect(params.get('_sort')).toBe('-startTime');
      expect(params.get('_limit')).toBe('10');
      await route.fulfill({
        json: {
          meta: { status: 200, totalCount: 42 },
          data: [{
            contentId: 'sm9',
            title: '<img src=x onerror=alert(1)>',
            description: '<b>Music</b>',
            viewCounter: 1000,
            likeCounter: 50,
            lengthSeconds: 125,
          }],
        },
      });
    });
    await f.getByTestId('pages-niconico-query').fill('初音ミク & test');
    await f.getByTestId('pages-niconico-sort').selectOption('-startTime');
    await f.getByTestId('pages-niconico-search').click();
    await expect(f.getByTestId('pages-niconico-status')).toContainText('42');
    const link = f.getByTestId('pages-niconico-results').getByRole('link');
    await expect(link).toHaveAttribute('href', 'https://www.nicovideo.jp/watch/sm9');
    await expect(link).toHaveText('<img src=x onerror=alert(1)>');
    await expect(f.getByTestId('pages-niconico-results').locator('img')).toHaveCount(0);
    await expect(f.getByTestId('pages-niconico-results')).toContainText('2:05');
  });

  for (const scenario of ['empty', 'http-error', 'invalid', 'network-error']) {
    test(`search handles ${scenario}`, async ({ page }) => {
      await page.route(niconicoEndpoint, route =>
        scenario === 'network-error'
          ? route.abort()
          : route.fulfill({
              status: scenario === 'http-error' ? 503 : 200,
              json: scenario === 'invalid'
                ? { meta: { status: 500 } }
                : { meta: { status: 200, totalCount: 0 }, data: [] },
            })
      );
      await f.getByTestId('pages-niconico-search').click();
      if (scenario === 'empty') {
        await expect(f.getByTestId('pages-niconico-results')).toContainText('No videos');
      } else {
        const error = f.getByTestId('pages-niconico-error');
        await expect(error).toBeVisible();
        if (scenario === 'http-error') await expect(error).toContainText('wait at least 5 minutes');
        if (scenario === 'network-error') await expect(error).toContainText('CORS');
      }
    });
  }

  test('official search preserves keyword and selected sort without an API response', async ({ page }) => {
    const link = f.getByTestId('pages-niconico-official');
    await expect(link).toHaveAttribute('target', '_blank');
    await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    await f.getByTestId('pages-niconico-query').fill('初音ミク & test');
    for (const [sort, official] of [['-viewCounter', 'v'], ['-startTime', 'f'], ['-likeCounter', 'likeCount'], ['-mylistCounter', 'm']]) {
      await f.getByTestId('pages-niconico-sort').selectOption(sort);
      const url = new URL(await link.getAttribute('href'));
      expect(url.origin).toBe('https://www.nicovideo.jp');
      expect(decodeURIComponent(url.pathname)).toBe('/search/初音ミク & test');
      expect(url.searchParams.get('sort')).toBe(official);
      expect(url.searchParams.get('order')).toBe('d');
    }
    await expect(f.getByTestId('pages-niconico')).not.toContainText('CORS enabled');
  });

  for (const scenario of ['non-json', 'null-row', 'invalid-description', 'invalid-id', 'invalid-count']) {
    test(`rejects malformed response: ${scenario}`, async ({ page }) => {
      const row = { contentId: 'sm9', title: 'Demo', description: 'Music' };
      if (scenario === 'invalid-description') row.description = {};
      if (scenario === 'invalid-id') row.contentId = '../not-a-video';
      await page.route(niconicoEndpoint, route =>
        route.fulfill(
          scenario === 'non-json'
            ? { contentType: 'text/html', body: '<html>upstream error</html>' }
            : {
                json: {
                  meta: { status: 200, totalCount: scenario === 'invalid-count' ? 'many' : 1 },
                  data: [scenario === 'null-row' ? null : row],
                },
              }
        )
      );
      await f.getByTestId('pages-niconico-search').click();
      await expect(f.getByTestId('pages-niconico-error')).toContainText('Invalid Niconico API response');
      await expect(f.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(0);
    });
  }

  test('renders at most ten videos even if an upstream sends more', async ({ page }) => {
    await page.route(niconicoEndpoint, route =>
      route.fulfill({
        json: {
          meta: { status: 200, totalCount: 12 },
          data: Array.from({ length: 12 }, (_, i) => ({ contentId: `sm${i + 1}`, title: `Video ${i + 1}` })),
        },
      })
    );
    await f.getByTestId('pages-niconico-search').click();
    await expect(f.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(10);
    await expect(f.getByTestId('pages-niconico-status')).toContainText('showing top 10');
  });

  test('HTTP 429 remains distinct from a browser network/CORS failure', async ({ page }) => {
    await page.route(niconicoEndpoint, route => route.fulfill({ status: 429, body: 'rate limited' }));
    await f.getByTestId('pages-niconico-search').click();
    await expect(f.getByTestId('pages-niconico-error')).toHaveText('Niconico API error: 429');
  });

  test('a hung API request times out at ten seconds and a subsequent search recovers', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-10-21T00:00:00Z') });
    await page.clock.pauseAt(new Date('2026-10-21T00:01:00Z'));
    let received;
    const started = new Promise(resolve => { received = resolve; });
    await page.route(niconicoEndpoint, () => { received(); });
    await f.getByTestId('pages-niconico-search').click();
    await started;
    await page.clock.fastForward(9999);
    await expect(f.getByTestId('pages-niconico-status')).toHaveText('Searching Niconico...');
    await page.clock.fastForward(1);
    await expect(f.getByTestId('pages-niconico-error')).toContainText('timed out after 10 seconds');
    await page.unroute(niconicoEndpoint);
    await page.route(niconicoEndpoint, route => route.fulfill({ json: { meta: { status: 200, totalCount: 0 }, data: [] } }));
    await f.getByTestId('pages-niconico-search').click();
    await expect(f.getByTestId('pages-niconico-results')).toContainText('No videos');
    await expect(f.getByTestId('pages-niconico-error')).toBeHidden();
  });

  async function installDeferredFetch() {
    await f.evaluate(() => {
      window.nicoPending = [];
      window.fetch = (url, { signal }) => new Promise((resolve, reject) => {
        window.nicoPending.push({ url, signal, resolve, reject });
      });
    });
  }

  test('a second search aborts the first and a late old response cannot replace new results', async ({ page }) => {
    await installDeferredFetch();
    await f.getByTestId('pages-niconico-search').click();
    await f.getByTestId('pages-niconico-query').fill('鏡音リン');
    await f.getByTestId('pages-niconico-sort').selectOption('-startTime');
    await f.getByTestId('pages-niconico-search').click();
    expect(await f.evaluate(() => window.nicoPending[0].signal.aborted)).toBe(true);
    await f.evaluate(() => window.nicoPending[1].resolve({
      ok: true,
      json: async () => ({ meta: { status: 200, totalCount: 1 }, data: [{ contentId: 'sm2', title: 'Newest response' }] }),
    }));
    await expect(f.getByTestId('pages-niconico-results')).toContainText('Newest response');
    await f.evaluate(() => window.nicoPending[0].resolve({
      ok: true,
      json: async () => ({ meta: { status: 200, totalCount: 1 }, data: [{ contentId: 'sm1', title: 'Stale response' }] }),
    }));
    await expect(f.getByTestId('pages-niconico-results')).not.toContainText('Stale response');
    await expect(f.getByTestId('pages-niconico-error')).toBeHidden();
  });

  test('timeout also covers the response body and late JSON cannot render', async ({ page }) => {
    await page.clock.install();
    await installDeferredFetch();
    await f.getByTestId('pages-niconico-search').click();
    await f.evaluate(() => window.nicoPending[0].resolve({
      ok: true,
      json: () => new Promise(resolve => { window.nicoBody = resolve; }),
    }));
    await page.clock.fastForward(10000);
    await f.evaluate(() => window.nicoBody({
      meta: { status: 200, totalCount: 1 },
      data: [{ contentId: 'sm9', title: 'Late body' }],
    }));
    await expect(f.getByTestId('pages-niconico-error')).toContainText('timed out');
    await expect(f.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(0);
  });

  test('tab navigation and hash routes preserve existing views', async ({ page }) => {
    await f.getByTestId('pages-nav-wiki').click();
    await expect(f.locator('[data-pages-view="wiki"]')).toBeVisible();
    await expect(f.getByTestId('pages-niconico')).toBeHidden();
    f = await lab(page, 'niconico');
    await expect(f.getByTestId('pages-niconico')).toBeVisible();
  });
});
