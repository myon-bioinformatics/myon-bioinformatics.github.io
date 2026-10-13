import {setText,prettyJson} from '../vendor/web-ui/js/ui.js';
import {parseHTML,extract,sourceURL,MAX_BYTES} from './extract.mjs';
const $=id=>document.getElementById(id);
let loaded=null, result=null, revision=0;
const sourceLink=globalThis.webUiNavigation.bindSourceLink($('source-url'),$('source-open'));
function clearResult(){result=null;setText($('body-result'),'');setText($('headings-result'),'');setText($('links-result'),'');setText($('provenance'),'');$('download').disabled=true;}
function fail(e){clearResult();setText($('status'),e.message);}
function apply(){
  clearResult();
  if(!loaded) return setText($('status'),'まずHTMLを取り込んでください。');
  try {
    const extraction=extract(loaded.root,loaded.snapshot.url,$('profile').value,$('selector').value.trim()||null);
    const {html,...metadata}=loaded.snapshot;
    result={snapshot:metadata,input:{kind:loaded.kind,name:loaded.name},extraction};
    setText($('body-result'),extraction.text);setText($('headings-result'),prettyJson(extraction.headings));setText($('links-result'),prettyJson(extraction.links));
    setText($('provenance'),prettyJson({...metadata,input:result.input,scope:extraction.scope,scope_count:extraction.scope_count}));
    setText($('status'),'抽出しました。同じ取込データで条件を変更できます。');$('download').disabled=false;
  }catch(e){fail(e);}
}
async function load(html,kind,name,url,token){
  const root=parseHTML(html);
  const bytes=new TextEncoder().encode(html);
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
  if(token!==revision) return;
  loaded={root,kind,name,snapshot:{schema:'html-snapshot/1',url,html,fetched_at:null,encoding:'utf-8',response_sha256:null,content_sha256:hash}};
  apply();
}
$('paste-load').addEventListener('click',async()=>{
  const token=++revision;loaded=null;clearResult();
  try{await load($('html-input').value,'paste',null,sourceURL($('source-url').value.trim()),token);}catch(e){if(token===revision)fail(e);}
});
$('file-input').addEventListener('change',async()=>{
  const token=++revision;loaded=null;clearResult();
  const file=$('file-input').files[0];if(!file)return;
  try{
    const url=sourceURL($('source-url').value.trim());
    if(file.size>MAX_BYTES)throw Error('HTMLの上限は2 MiBです。');
    const html=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    if(token===revision) await load(html,'file',file.name,url,token);
  }catch(e){if(token===revision)fail(e);}
});
$('apply').addEventListener('click',apply);
$('download').addEventListener('click',()=>{
  if(!result)return;
  const url=URL.createObjectURL(new Blob([prettyJson(result)+'\n'],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='html-extraction.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('clear').addEventListener('click',()=>{++revision;loaded=null;clearResult();$('html-input').value='';$('file-input').value='';$('source-url').value='';sourceLink.update();setText($('status'),'取込データと結果を消去しました。');});
