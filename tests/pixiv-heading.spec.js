const {test, expect} = require('@playwright/test');
const fixtures = require('./fixtures/pixiv-markup.json');
for (const mobile of [false, true]) {
  test.describe(mobile ? 'Pixiv mobile' : 'Pixiv desktop', () => {
    test.use({viewport: mobile ? {width:390,height:844} : {width:1440,height:900}});
    test('source headings select cached body and reset safely', async ({page}, info) => {
      const external = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', request => { if (!request.url().startsWith('http://localhost:8080/')) external.push(request.url()); });
      await page.goto('/tools/mcp-toolcall-lab/#pixiv');
      await page.getByTestId('pages-pixiv-source-text').fill(fixtures[0].source);
      await page.getByTestId('pages-pixiv-extract-submit').click();
      const select = page.locator('#pages-pixiv-heading'), output = page.getByTestId('pages-pixiv-extract');
      await expect(select.locator('option')).toHaveCount(7);
      await select.selectOption({label:'# 世界観'});
      await expect(output).toContainText('## 文明描写');
      await expect(output).toContainText('## 社会構成');
      await expect(output).not.toContainText('関連イラスト');
      await select.selectOption({label:'## 文明描写'});
      await expect(output).not.toContainText('社会構成');
      await select.selectOption('');
      await expect(output).toContainText('Title: 試験記事');
      await page.screenshot({path:info.outputPath('pixiv-headings.png'),fullPage:true});
      await page.getByTestId('pages-pixiv-source-text').fill('*同名\nfirst\n*同名\n<script>window.pwned=true</script>');
      await page.getByTestId('pages-pixiv-extract-submit').click();
      await select.selectOption('1');
      await expect(output).toHaveText('<script>window.pwned=true</script>');
      expect(await page.evaluate(() => window.pwned)).toBeUndefined();
      await page.getByTestId('pages-pixiv-source-text').fill('No headings');
      await page.getByTestId('pages-pixiv-extract-submit').click();
      await expect(select).toBeDisabled();
      await expect(output).toContainText('No headings');
      await page.getByTestId('pages-pixiv-source-text').fill('');
      await page.getByTestId('pages-pixiv-extract-submit').click();
      await expect(output).toBeHidden();
      await expect(select.locator('option')).toHaveCount(1);
      await expect(page.getByTestId('pages-pixiv-error')).toBeVisible();
      expect(external).toEqual([]);
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  });
}
