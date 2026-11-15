const { test, expect } = require('@playwright/test');

test('transferred Pixiv extraction remains functional without upstream fetch', async ({ page }) => {
  await page.goto('/tools/mcp-toolcall-lab/#pixiv');
  await expect(page.locator('[data-pages-view="pixiv"]')).toBeVisible();
  await page.locator('#pages-pixiv-title').fill('Demo');
  await page.locator('#pages-pixiv-source-text').fill('Example original source text');
  await page.locator('[data-testid="pages-pixiv-extract-submit"]').click();
  await expect(page.locator('[data-testid="pages-pixiv-extract"]')).toContainText('Example original source text');
  await page.goto('/tools/mcp-toolcall-lab/#wiki');
  await expect(page.locator('#pages-wiki-form')).toBeVisible();
  await expect(page.locator('[data-pages-view="pixiv"]')).toBeHidden();
});
for(const mobile of [false,true]){
 test.describe(mobile?'mobile shared lab UI':'desktop shared lab UI',()=>{
  test.use({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile});
  test('shared fonts and navigation preserve Pixiv and cached Wikipedia extraction',async({page,context},info)=>{
   await page.goto('/tools/html-import/');const reference=await page.locator('body').evaluate(e=>{const s=getComputedStyle(e);return {font:s.fontFamily,size:s.fontSize,color:s.color,background:s.backgroundColor};});
   let fetches=0;
   await context.route('https://en.wikipedia.org/w/api.php?*',async route=>{fetches++;await route.fulfill({contentType:'application/json',headers:{'access-control-allow-origin':'*'},body:JSON.stringify({query:{pages:{1:{title:'Demo',extract:'Introduction\n== History ==\nHistory body\n== Geography ==\nGeography body'}}}})});});
   await page.goto('/tools/mcp-toolcall-lab/#pixiv');await expect(page.locator('[data-pages-view="pixiv"]')).toBeVisible();
   const actual=await page.locator('body').evaluate(e=>{const s=getComputedStyle(e);return {font:s.fontFamily,size:s.fontSize,color:s.color,background:s.backgroundColor};});expect(actual).toEqual(reference);
   await page.locator('#pages-pixiv-title').fill('Demo');await page.locator('#pages-pixiv-source-text').fill('Example original source text');await page.getByTestId('pages-pixiv-extract-submit').click();await expect(page.getByTestId('pages-pixiv-extract')).toContainText('Example original source text');
   expect(await page.getByTestId('pages-pixiv-extract').evaluate(e=>getComputedStyle(e).fontFamily)).toBe(reference.font);
   await context.route('https://dic.pixiv.net/a/Demo',route=>route.fulfill({contentType:'text/html',body:'<h1>Demo article</h1>'}));
   const next=context.waitForEvent('page');await page.getByTestId('pages-pixiv-open-article').click();const popup=await next;await popup.waitForLoadState();expect(popup.url()).toBe('https://dic.pixiv.net/a/Demo');expect(await popup.evaluate(()=>window.opener)).toBeNull();await popup.close();
   await page.getByTestId('pages-nav-wiki').click();await expect(page.locator('[data-pages-view="wiki"]')).toBeVisible();await expect(page.locator('[data-pages-view="pixiv"]')).toBeHidden();
   await page.locator('#pages-wiki-title').fill('Demo');await page.getByTestId('pages-wiki-fetch').click();await expect(page.getByTestId('pages-wiki-extract')).toContainText('History body');
   await page.locator('#pages-wiki-heading').selectOption({label:'## History'});await expect(page.getByTestId('pages-wiki-extract')).toHaveText('History body');expect(fetches).toBe(1);
   expect(await page.locator('#pages-wiki-heading').evaluate(e=>getComputedStyle(e).colorScheme)).toBe('dark');
   await page.getByTestId('pages-nav-pixiv').click();await expect(page.locator('[data-pages-view="pixiv"]')).toBeVisible();await expect(page.getByTestId('pages-pixiv-extract')).toContainText('Example original source text');
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.screenshot({path:info.outputPath('shared-lab-ui.png'),fullPage:true});
   await page.goto('/tools/mcp-toolcall-lab/?view=wiki');await expect(page.locator('[data-pages-view="wiki"]')).toBeVisible();await expect(page).toHaveURL(/#wiki$/);
  });
 });
}

test('execution links and empty Wiki examples remain usable', async ({ page }) => {
  const execution = 'https://myon-bioinformatics.github.io/mcp-toolcall-lab/execution/';
  await page.goto('/');
  await expect(page.getByRole('link', { name: 'Open Execution Lab →' })).toHaveAttribute('href', execution);
  await page.goto('/tools/mcp-toolcall-lab/#wiki');
  await expect(page.getByTestId('lab-execution-link')).toHaveAttribute('href', execution);
  await expect(page.getByTestId('pages-wiki-title')).toHaveValue('');
  await page.getByTestId('pages-wiki-fetch').click();
  await expect(page.getByTestId('pages-wiki-error')).toContainText('Enter a Wikipedia title.');
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
  await page.route('https://pokeapi.co/api/v2/pokemon/*', (route) =>
    route.fulfill({ contentType: 'application/json', body: JSON.stringify(ditto) })
  );
  await page.goto('/tools/mcp-toolcall-lab/#pokemon');
  await expect(page.locator('[data-pages-view="pokemon"]')).toBeVisible();
  await page.locator('#pokemon-name').fill('ditto');
  await page.locator('[data-source-fetch]').click();
  await expect(page.locator('[data-source-output]')).toContainText('ditto (#132)');
  await expect(page.locator('[data-source-output]')).toContainText('normal');

  await page.locator('#pokemon-name').fill('');
  await page.locator('#pokemon-text').fill(JSON.stringify(ditto));
  await page.locator('[data-source-extract]').click();
  await expect(page.locator('[data-source-output]')).toContainText('ditto (#132)');
});

