const { test, expect } = require('@playwright/test');
const endpoint = 'https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search?*';
test.beforeEach(async ({ page }) => {
  await page.goto('/tools/mcp-toolcall-lab/#niconico');
  await expect(page.getByTestId('pages-niconico')).toBeVisible();
});
test('search sends encoded query and sort, renders safe result links', async ({ page }) => {
  await page.route(endpoint, async route => {
    const params = new URL(route.request().url()).searchParams;
    expect(params.get('q')).toBe('初音ミク & test');
    expect(params.get('_sort')).toBe('-startTime');
    expect(params.get('_limit')).toBe('10');
    await route.fulfill({ json: { meta: { status:200, totalCount:42 }, data:[{
      contentId:'sm9', title:'<img src=x onerror=alert(1)>', description:'<b>Music</b>',
      viewCounter:1000, likeCounter:50, lengthSeconds:125 }] } });
  });
  await page.getByTestId('pages-niconico-query').fill('初音ミク & test');
  await page.getByTestId('pages-niconico-sort').selectOption('-startTime');
  await page.getByTestId('pages-niconico-search').click();
  await expect(page.getByTestId('pages-niconico-status')).toContainText('42');
  const link = page.getByTestId('pages-niconico-results').getByRole('link');
  await expect(link).toHaveAttribute('href','https://www.nicovideo.jp/watch/sm9');
  await expect(link).toHaveText('<img src=x onerror=alert(1)>');
  await expect(page.getByTestId('pages-niconico-results').locator('img')).toHaveCount(0);
  await expect(page.getByTestId('pages-niconico-results')).toContainText('2:05');
});
for (const scenario of ['empty','http-error','invalid','network-error']) {
  test(`search handles ${scenario}`, async ({ page }) => {
    await page.route(endpoint, route => scenario === 'network-error' ? route.abort()
      : route.fulfill({ status:scenario==='http-error'?503:200,
        json:scenario==='invalid'?{meta:{status:500}}:{meta:{status:200,totalCount:0},data:[]} }));
    await page.getByTestId('pages-niconico-search').click();
    if (scenario==='empty') await expect(page.getByTestId('pages-niconico-results')).toContainText('No videos');
    else {
      const error = page.getByTestId('pages-niconico-error');
      await expect(error).toBeVisible();
      if (scenario === 'http-error') await expect(error).toContainText('wait at least 5 minutes');
      if (scenario === 'network-error') await expect(error).toContainText('CORS');
    }
  });
}

test('official search preserves keyword and selected sort without an API response', async ({ page }) => {
  const link = page.getByTestId('pages-niconico-official');
  await expect(link).toHaveAttribute('target', '_blank');
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  await page.getByTestId('pages-niconico-query').fill('初音ミク & test');
  for (const [sort, official] of [['-viewCounter','v'], ['-startTime','f'], ['-likeCounter','like'], ['-mylistCounter','m']]) {
    await page.getByTestId('pages-niconico-sort').selectOption(sort);
    const url = new URL(await link.getAttribute('href'));
    expect(url.origin).toBe('https://www.nicovideo.jp');
    expect(decodeURIComponent(url.pathname)).toBe('/search/初音ミク & test');
    expect(url.searchParams.get('sort')).toBe(official);
    expect(url.searchParams.get('order')).toBe('d');
  }
  await expect(page.getByTestId('pages-niconico')).not.toContainText('CORS enabled');
});

for (const scenario of ['non-json', 'null-row', 'invalid-description', 'invalid-id', 'invalid-count']) {
  test(`rejects malformed response: ${scenario}`, async ({ page }) => {
    const row = {contentId:'sm9', title:'Demo', description:'Music'};
    if (scenario === 'invalid-description') row.description = {};
    if (scenario === 'invalid-id') row.contentId = '../not-a-video';
    await page.route(endpoint, route => route.fulfill(scenario === 'non-json'
      ? {contentType:'text/html', body:'<html>upstream error</html>'}
      : {json:{meta:{status:200, totalCount:scenario === 'invalid-count' ? 'many' : 1},
        data:[scenario === 'null-row' ? null : row]}}));
    await page.getByTestId('pages-niconico-search').click();
    await expect(page.getByTestId('pages-niconico-error')).toContainText('Invalid Niconico API response');
    await expect(page.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(0);
  });
}

test('renders at most ten videos even if an upstream sends more', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({json:{meta:{status:200,totalCount:12},
    data:Array.from({length:12}, (_,i) => ({contentId:`sm${i+1}`, title:`Video ${i+1}`}))}}));
  await page.getByTestId('pages-niconico-search').click();
  await expect(page.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(10);
  await expect(page.getByTestId('pages-niconico-status')).toContainText('showing top 10');
});

test('HTTP 429 remains distinct from a browser network/CORS failure', async ({ page }) => {
  await page.route(endpoint, route => route.fulfill({status:429,body:'rate limited'}));
  await page.getByTestId('pages-niconico-search').click();
  await expect(page.getByTestId('pages-niconico-error')).toHaveText('Niconico API error: 429');
});

test('a hung API request times out at ten seconds and a subsequent search recovers', async ({ page }) => {
  await page.clock.install();
  let received;
  const started = new Promise(resolve => { received = resolve; });
  await page.route(endpoint, () => { received(); });
  await page.getByTestId('pages-niconico-search').click();
  await started;
  await page.clock.fastForward(9999);
  await expect(page.getByTestId('pages-niconico-status')).toHaveText('Searching Niconico...');
  await page.clock.fastForward(1);
  await expect(page.getByTestId('pages-niconico-error')).toContainText('timed out after 10 seconds');
  await page.unroute(endpoint);
  await page.route(endpoint, route => route.fulfill({json:{meta:{status:200,totalCount:0},data:[]}}));
  await page.getByTestId('pages-niconico-search').click();
  await expect(page.getByTestId('pages-niconico-results')).toContainText('No videos');
  await expect(page.getByTestId('pages-niconico-error')).toBeHidden();
});

// A controlled fetch double lets an old response arrive after abort. This is a
// race/timeout simulation, never evidence that the external API is reachable.
async function installDeferredFetch(page) {
  await page.evaluate(() => {
    window.nicoPending = [];
    window.fetch = (url, {signal}) => new Promise((resolve, reject) => {
      window.nicoPending.push({url, signal, resolve, reject});
    });
  });
}

test('a second search aborts the first and a late old response cannot replace new results', async ({ page }) => {
  await installDeferredFetch(page);
  await page.getByTestId('pages-niconico-search').click();
  await page.getByTestId('pages-niconico-query').fill('鏡音リン');
  await page.getByTestId('pages-niconico-sort').selectOption('-startTime');
  await page.getByTestId('pages-niconico-search').click();
  expect(await page.evaluate(() => window.nicoPending[0].signal.aborted)).toBe(true);
  await page.evaluate(() => window.nicoPending[1].resolve({ok:true, json:async () => ({
    meta:{status:200,totalCount:1}, data:[{contentId:'sm2',title:'Newest response'}]})}));
  await expect(page.getByTestId('pages-niconico-results')).toContainText('Newest response');
  await page.evaluate(() => window.nicoPending[0].resolve({ok:true, json:async () => ({
    meta:{status:200,totalCount:1}, data:[{contentId:'sm1',title:'Stale response'}]})}));
  await expect(page.getByTestId('pages-niconico-results')).not.toContainText('Stale response');
  await expect(page.getByTestId('pages-niconico-error')).toBeHidden();
});

test('timeout also covers the response body and late JSON cannot render', async ({ page }) => {
  await page.clock.install();
  await installDeferredFetch(page);
  await page.getByTestId('pages-niconico-search').click();
  await page.evaluate(() => window.nicoPending[0].resolve({ok:true,
    json:() => new Promise(resolve => { window.nicoBody = resolve; })}));
  await page.clock.fastForward(10000);
  await page.evaluate(() => window.nicoBody({meta:{status:200,totalCount:1},
    data:[{contentId:'sm9',title:'Late body'}]}));
  await expect(page.getByTestId('pages-niconico-error')).toContainText('timed out');
  await expect(page.getByTestId('pages-niconico-results').getByRole('link')).toHaveCount(0);
});
test('tab navigation and query alias preserve existing views', async ({ page }) => {
  await page.getByTestId('pages-nav-wiki').click();
  await expect(page.locator('[data-pages-view="wiki"]')).toBeVisible();
  await expect(page.getByTestId('pages-niconico')).toBeHidden();
  await page.goto('/tools/mcp-toolcall-lab/?view=niconico');
  await expect(page.getByTestId('pages-niconico')).toBeVisible();
});
