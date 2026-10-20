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
    else await expect(page.getByTestId('pages-niconico-error')).toBeVisible();
  });
}
test('tab navigation and query alias preserve existing views', async ({ page }) => {
  await page.getByTestId('pages-nav-wiki').click();
  await expect(page.locator('[data-pages-view="wiki"]')).toBeVisible();
  await expect(page.getByTestId('pages-niconico')).toBeHidden();
  await page.goto('/tools/mcp-toolcall-lab/?view=niconico');
  await expect(page.getByTestId('pages-niconico')).toBeVisible();
});
