const { test, expect } = require('@playwright/test');

// Skipped in normal CI: network failures must never be counted as a mock pass.
test('LIVE: published search, two sorts and video navigation (no mocks)', async ({ page, context }, testInfo) => {
  test.skip(process.env.NICONICO_LIVE !== '1', 'Opt in with NICONICO_LIVE=1 and the live config.');
  const observations = {kind:'live-browser', mocked:false, startedAt:new Date().toISOString(),
    console:[], responses:[], failures:[], searches:[]};
  page.on('console', msg => { if (msg.type() === 'error') observations.console.push(msg.text()); });
  page.on('requestfailed', req => observations.failures.push({url:req.url(), error:req.failure()}));
  page.on('response', res => {
    if (res.url().startsWith('https://snapshot.search.nicovideo.jp/'))
      observations.responses.push({url:res.url(),status:res.status(),headers:res.headers()});
  });
  try {
    const response = await page.goto('/tools/mcp-toolcall-lab/#niconico');
    expect(response.status()).toBe(200);
    await page.getByTestId('pages-niconico-query').fill('初音ミク');
    for (const sort of ['-viewCounter', '-startTime']) {
      await page.getByTestId('pages-niconico-sort').selectOption(sort);
      const start = Date.now();
      await page.getByTestId('pages-niconico-search').click();
      await expect(page.getByTestId('pages-niconico-status')).not.toHaveText('Searching Niconico...', {timeout:15000});
      const links = page.getByTestId('pages-niconico-results').getByRole('link');
      const count = await links.count();
      observations.searches.push({sort,count,status:await page.getByTestId('pages-niconico-status').textContent(),
        error:await page.getByTestId('pages-niconico-error').textContent()});
      if (count) {
        expect(count).toBeLessThanOrEqual(10);
        const href = await links.first().getAttribute('href');
        const title = await links.first().innerText();
        const popupPromise = context.waitForEvent('page');
        await links.first().click();
        const popup = await popupPromise;
        await popup.waitForLoadState('domcontentloaded');
        observations.searches.at(-1).navigation = {expected:href, actual:popup.url(), title:await popup.title()};
        expect(popup.url()).toBe(href);
        await expect(popup).toHaveTitle(new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
        await popup.close();
      }
      // Be polite to the API even when the browser denies access to its body.
      await new Promise(resolve => setTimeout(resolve, Date.now() - start + 100));
    }
    // Do not turn an error screen into a successful live acceptance test.
    expect(observations.searches.map(s => s.count)).toEqual([10,10]);
  } finally {
    observations.finishedAt = new Date().toISOString();
    await testInfo.attach('niconico-live-observations', {body:JSON.stringify(observations,null,2),contentType:'application/json'});
  }
});
