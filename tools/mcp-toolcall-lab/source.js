/** web-ui source: read a name (one GET per press, never retried) or JSON you pasted, through a consumer's declarative spec, in the page. Nothing is stored. Python (web_ui.source_*) is the reference; this must agree. */
(function(root,factory){
  const api=factory();
  if(typeof module==='object' && module.exports) module.exports=api;
  else {root.webUiSource=api; if(root.document){const start=()=>api.bindSources(root);if(root.document.readyState==='loading')root.document.addEventListener('DOMContentLoaded',start,{once:true});else start();}}
})(typeof globalThis==='undefined'?this:globalThis,function(){
  'use strict';
  const LIMIT=2*1024*1024,fail=m=>{throw Error(m);};
  const bytes=t=>typeof TextEncoder==='function'?new TextEncoder().encode(t).length:t.length;
  function sourceName(spec,text){const t=String(text??'').replace(/^[ \t\n\r\f\v]+|[ \t\n\r\f\v]+$/g,'').toLowerCase();return new RegExp('^(?:'+spec.name+')$').test(t)?t:'';}
  function sourceUrl(spec,name){const n=sourceName(spec,name);return n?spec.url.replace('{name}',()=>encodeURIComponent(n)):'';}
  const get=(data,path)=>{for(const part of path.split('.')){if(data!==null&&typeof data==='object'&&!Array.isArray(data)&&Object.prototype.hasOwnProperty.call(data,part))data=data[part];else fail('missing '+path);}return data;};
  const scalar=v=>{if(typeof v==='string')return v;if(typeof v==='boolean')return v?'true':'false';if(v===null)return '';if(typeof v==='number')return String(v);return fail('not a scalar');};
  const number=v=>typeof v==='number'?v:fail('not a number');
  function cell(c,ctx){
    let v=get(ctx,c.key);
    if(Array.isArray(v)){if('sort' in c)v=v.slice().sort((a,b)=>number(get(a,c.sort))-number(get(b,c.sort)));return v.map(r=>scalar('pick' in c?get(r,c.pick):r)).join('sep' in c?c.sep:', ');}
    if('yes' in c){if(typeof v!=='boolean')fail('not a boolean');return v?c.yes:'';}
    if('div' in c){const r=number(v)/c.div;return Number.isInteger(r)?r.toFixed(1):String(r);}
    return scalar(v);
  }
  function sourceExtract(spec,input){
    let data=input;const limit=spec.limit||LIMIT;
    if(typeof input==='string'){
      if(bytes(input)>limit)fail('source exceeds '+limit+' bytes');
      try{data=JSON.parse(input);}catch{fail('source is not JSON');}
    }
    try{
      const title=spec.title.replace(/\{([a-z0-9_.]+)\}/g,(m,k)=>scalar(get(data,k)));
      const tables=spec.tables.map(t=>{
        let rows;
        if(t.each){let items=get(data,t.each);if(!Array.isArray(items))fail('not a list');if('sort' in t)items=items.slice().sort((a,b)=>number(get(a,t.sort))-number(get(b,t.sort)));rows=items.map(i=>t.cells.map(c=>cell(c,i)));}
        else rows=t.rows.map(r=>r.map(c=>cell(c,data)));
        return {headers:t.headers.slice(),rows};
      });
      return {title,tables};
    }catch{fail(spec.error||'not the expected response');}
  }
  const esc=s=>String(s).replace(/\|/g,'\\|').replace(/[\r\n]/g,' ');
  function sourceMarkdown(x){
    return '# '+String(x.title).replace(/[\r\n]/g,' ')+'\n\n'+x.tables.map(t=>'| '+t.headers.map(esc).join(' | ')+' |\n| '+t.headers.map(()=>'---').join(' | ')+' |\n'+t.rows.map(r=>'| '+r.map(esc).join(' | ')+' |\n').join('')).join('\n');
  }
  function loadSource(spec,name,fetchImpl){
    const url=sourceUrl(spec,name);
    if(!url)return Promise.resolve({ok:false,error:spec.missing||'Enter a valid name.'});
    return Promise.resolve().then(()=>fetchImpl(url,{headers:{Accept:'application/json'},redirect:'error',credentials:'omit',referrerPolicy:'no-referrer'})).then(r=>{
      if(r.status===404)return {ok:false,error:'not found: '+sourceName(spec,name)};
      if(!r.ok)return {ok:false,error:'HTTP '+r.status};
      return r.text().then(t=>{try{return {ok:true,extract:sourceExtract(spec,t)};}catch(e){return {ok:false,error:e.message};}});
    }).catch(e=>({ok:false,error:'could not fetch ('+((e&&e.message)||'network error')+'). Open the JSON, copy it and paste it below instead.'}));
  }
  const handles=new WeakMap();
  function bindSource(panel,{window:win=globalThis.window,fetch:fetchImpl}={}){
    if(handles.has(panel))return handles.get(panel);
    const spec=JSON.parse(panel.getAttribute('data-source-spec'));
    const q=n=>panel.querySelector('[data-source-'+n+']');
    const els={name:q('name'),fetch:q('fetch'),open:q('open'),text:q('text'),extract:q('extract'),status:q('status'),error:q('error'),output:q('output')};
    const send=fetchImpl||(win&&typeof win.fetch==='function'?win.fetch.bind(win):null);
    const show=(result,origin)=>{
      els.error.hidden=result.ok;els.output.hidden=!result.ok;
      els.error.textContent=result.ok?'':result.error;
      els.output.textContent=result.ok?sourceMarkdown(result.extract):'';
      els.status.textContent=result.ok?result.extract.title+' — '+origin:'';
      return result;
    };
    els.open.addEventListener('click',()=>{
      const url=sourceUrl(spec,els.name.value);
      if(!url)return show({ok:false,error:spec.missing||'Enter a valid name.'});
      win.open(url,'_blank','noopener,noreferrer');els.status.textContent='Opened '+url+' — copy its JSON and paste it below.';return null;
    });
    els.fetch.addEventListener('click',()=>{
      if(!send)return show({ok:false,error:'fetch is not available; paste the JSON instead'});
      if(els.fetch.disabled)return null;
      els.fetch.disabled=true;els.status.textContent='Fetching\u2026';
      return loadSource(spec,els.name.value,send).then(r=>{els.fetch.disabled=false;return show(r,'fetched');});
    });
    els.extract.addEventListener('click',()=>{
      const text=String(els.text.value||'').trim();
      let result;
      if(!text)result={ok:false,error:'Paste the JSON first.'};
      else try{result={ok:true,extract:sourceExtract(spec,text)};}catch(e){result={ok:false,error:e.message};}
      return show(result,'from pasted JSON');
    });
    const handle={spec,show};handles.set(panel,handle);return handle;
  }
  function bindSources(win){return [...win.document.querySelectorAll('[data-ui-source]')].map(p=>bindSource(p,{window:win}));}
  return {sourceName,sourceUrl,sourceExtract,sourceMarkdown,loadSource,bindSource,bindSources};
});
