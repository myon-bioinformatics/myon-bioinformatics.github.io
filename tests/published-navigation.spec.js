// Live Pages acceptance; reuse the existing Playwright image and reporter.
const {test, expect}=require('@playwright/test');
const crypto=require('node:crypto');
const origin=process.env.HTML_TOOL_BASE_URL;
test.skip(!origin,'published Pages only');
for(const width of [390,1200]){
 test.describe('published navigation '+width,()=>{
  test.use({viewport:{width,height:900},isMobile:width===390,hasTouch:width===390});
  test('Tools shell: unique return destination and all studio panels',async({page},info)=>{
   const target=new URL('/index.html#tools',origin).href;
   await page.goto('/tools/#home');
   const home=page.locator('.ui-chrome a.ui-world-home');
   const verify=async()=>{
    await expect(home).toBeVisible();
    expect(await page.locator('a[href]').evaluateAll((as,target)=>as.filter(a=>a.href===target).length,target)).toBe(1);
   };
   await verify();
   for(const panel of ['image-studio','slide-studio','browser-tools']){
    await page.evaluate(panel=>location.hash=panel,panel);
    const frame=page.locator('#'+panel+' iframe');
    await expect(frame).toBeVisible();
    await expect(frame).toHaveAttribute('data-ready',/.+/);
    const doc=page.frameLocator('#'+panel+' iframe');
    await expect(doc.locator('body')).toBeVisible();
    if(panel==='image-studio') await expect(doc.locator('#board svg')).toHaveCount(1);
    if(panel==='slide-studio') await expect(doc.locator('#studio-toolbar')).toBeVisible();
    await verify();
    await page.screenshot({path:info.outputPath(panel+'.png')});
   }
   await home.click();
   await expect(page).toHaveURL(target);
  });
  test('Aoi guide: repository link, tab switching and animated GIF',async({page},info)=>{
   await page.goto('/Aoi/');
   const target='https://github.com/myon-bioinformatics/Aoi';
   expect(await page.locator('a[href]').evaluateAll((as,target)=>as.filter(a=>a.href.replace(/\/$/,'').toLowerCase()===target.toLowerCase()).length,target)).toBe(1);
   const gif=page.locator('img[src$="browser.gif"]');
   await expect(gif).toBeVisible();
   await expect.poll(()=>gif.evaluate(im=>im.complete&&im.naturalWidth>0)).toBe(true);
   // Browser screenshots of the same decoded image over time, not only GIF header inspection.
   const hashes=new Set();
   for(let i=0;i<16;i++){
    hashes.add(crypto.createHash('sha256').update(await gif.screenshot()).digest('hex'));
    if(hashes.size>1)break;
    await page.waitForTimeout(400);
   }
   expect(hashes.size,'GIF pixels change over time').toBeGreaterThan(1);
   await page.screenshot({path:info.outputPath('aoi-gif.png')});
   const features=page.getByRole('tab').filter({hasText:'機能一覧'});
   await features.click();
   await expect(gif).toBeHidden();
   await page.getByRole('tab').filter({hasText:'GIF'}).click();
   await expect(gif).toBeVisible();
  });
 });
}
