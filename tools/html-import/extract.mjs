// Browser companion to the pinned lab extractor. Input nodes never enter the live DOM.
const excluded = new Set(['script', 'style', 'template', 'noscript']);
export const MAX_BYTES = 2 * 1024 * 1024;
import '../vendor/web-ui/js/navigation.js';
export const sourceURL = globalThis.webUiNavigation.sourceURL;
export function parseHTML(html) {
  if (typeof html !== 'string' || new TextEncoder().encode(html).length > MAX_BYTES) throw Error('HTMLの上限は2 MiBです。');
  const template = document.createElement('template');
  template.innerHTML = html; // inert: no script, image, iframe or stylesheet activation
  const root = {tag:'document', attrs:{}, parent:null, children:[]};
  function convert(dom, parent, depth) {
    if (dom.nodeType === 3) return dom.data;
    if (dom.nodeType !== 1) return null;
    if (depth >= 128) throw Error('HTMLの階層が128を超えています。');
    const node = {tag:dom.localName, attrs:Object.fromEntries([...dom.attributes].map(a=>[a.name,a.value])), parent, children:[]};
    // template content and excluded descendants are deliberately not visited.
    if (!excluded.has(node.tag)) node.children = [...dom.childNodes].map(c=>convert(c,node,depth+1)).filter(c=>c!==null);
    return node;
  }
  root.children = [...template.content.childNodes].map(c=>convert(c,root,1)).filter(c=>c!==null);
  return root;
}
function walk(node) { if (excluded.has(node.tag)) return []; return [node,...node.children.filter(c=>typeof c!=='string').flatMap(walk)]; }
function rawText(node) { return excluded.has(node.tag)?'':node.children.map(c=>typeof c==='string'?c:rawText(c)).join(' '); }
// Python str.split whitespace includes NEL and U+001C..1F, but excludes BOM.
const clean = n=>rawText(n).replace(/[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/g,' ').replace(/^ +| +$/g,'');
const words = s=>(s||'').split(/\s+/);
function select(nodes, selector) {
  if (typeof selector!=='string' || !selector.trim() || selector.length>512) throw Error('selector must be a non-empty string of at most 512 characters');
  const tokens=selector.match(/>|[^\s>]+/g), parts=[], relations=[];
  let relation=null;
  for (const t of tokens) {
    if (t==='>') { if (!parts.length || relation==='>') throw Error('invalid selector combinator'); relation='>'; continue; }
    if (t!==':root' && !/^(?:[a-zA-Z][\w-]*|\*)?(?:[.#][a-zA-Z_][\w-]*)*$/.test(t)) throw Error('unsupported selector syntax');
    if(parts.length) relations.push(relation||' '); parts.push(t); relation=null;
  }
  if(relation || !parts.length) throw Error('invalid selector combinator');
  function matches(n,t) {
    if (t===':root') return n.parent?.tag==='document';
    const tag=t.match(/^[a-zA-Z][\w-]*|^\*/)?.[0];
    if (tag && tag!=='*' && n.tag!==tag.toLowerCase()) return false;
    for(const m of t.matchAll(/([.#])([a-zA-Z_][\w-]*)/g)) if(m[1]==='#'?n.attrs.id!==m[2]:!words(n.attrs.class).includes(m[2])) return false;
    return n.tag!=='document';
  }
  function chain(n,i) {
    if(!n || !matches(n,parts[i])) return false;
    if(!i) return true;
    if(relations[i-1]==='>') return chain(n.parent,i-1);
    for(let p=n.parent;p;p=p.parent) if(chain(p,i-1)) return true;
    return false;
  }
  return nodes.filter(n=>chain(n,parts.length-1));
}
const resolve = (href,url)=>{try{const u=new URL(href,url);return ['http:','https:'].includes(u.protocol)?u.href:null;}catch{return null;}};
export function extract(root, url, profile='generic', selector=null) {
  sourceURL(url);
  if(!['generic','github-readme'].includes(profile)) throw Error('unknown HTML profile');
  const nodes=walk(root); let scopes=nodes.filter(n=>n.tag==='article'), scope='article';
  if(selector!==null) {
    if(profile!=='generic') throw Error('selector requires generic profile');
    scopes=select(nodes,selector); scope=selector;
    if(!scopes.length) throw Error('selector matched no elements');
  } else if(profile==='github-readme') {
    scopes=scopes.filter(n=>words(n.attrs.class).includes('markdown-body'));
    if(scopes.length!==1) throw Error('github-readme requires exactly one article.markdown-body');
  } else if(!scopes.length) { scopes=nodes.filter(n=>n.tag==='main'); if(!scopes.length) scopes=[root]; scope=scopes[0]===root?'document':'main'; }
  const descendants=new Set(scopes.flatMap(n=>walk(n).slice(1)));
  scopes=scopes.filter(n=>!descendants.has(n));
  const content=scopes.flatMap(walk), text=scopes.map(clean).filter(Boolean).join(' ');
  if(!text) throw Error('selected HTML scope has no text');
  return {source_url:url,profile,scope,scope_count:scopes.length,title:clean(nodes.find(n=>n.tag==='title')||{children:[]}),
    headings:content.filter(n=>/^h[1-6]$/.test(n.tag)).map(n=>({level:n.tag,text:clean(n)})),text,
    links:content.filter(n=>n.tag==='a' && n.attrs.href && resolve(n.attrs.href,url)).map(n=>({text:clean(n),url:resolve(n.attrs.href,url)})),
    structure:nodes.filter(n=>['main','article'].includes(n.tag)).map(n=>({tag:n.tag,id:n.attrs.id??null,class:n.attrs.class??null})),
    stylesheets:nodes.filter(n=>n.tag==='link' && words((n.attrs.rel||'').toLowerCase()).includes('stylesheet') && n.attrs.href && resolve(n.attrs.href,url)).map(n=>resolve(n.attrs.href,url))};
}
