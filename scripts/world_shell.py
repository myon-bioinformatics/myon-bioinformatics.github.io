"""The Portfolio's one published world. Individual specs and standalone exports stay in world.py."""
from html import escape

# Public fragments are stable and independent of the map engine's internal IDs.
SPACES = {
    'world': ('overworld', '🌍 村'),
    'school': ('school', '🏫 学校'),
    'tokyo': ('cities', '🗼 パラレル東京'),
    'london': ('cities', '🎡 Reverse London'),
    'paris': ('cities', '🥖 Fake Paris'),
    'nagoya': ('nagoya', '🏯 聖地ナゴヤ'),
    'camera': ('world', '🎬 カメラ'),
}

CSS = """
[data-world-space][hidden],[data-world-shell] [data-menu="favorites"],
[data-world-route]:not([data-world-route="tokyo"]) :is(#tokyo-range,#area-return){display:none!important}
[data-world-shell]>header{position:sticky;top:0;z-index:10;background:var(--ui-bg)}
[data-world-space]{position:relative;isolation:isolate;scroll-margin-top:5rem}
.world-switcher .ui-world-tools{flex-wrap:wrap;gap:.35rem}
.world-switcher details{position:relative}
.world-switcher summary{cursor:pointer;padding:.45rem;min-height:44px;display:grid;align-items:center}
.world-switcher details[open]>div{position:absolute;top:100%;left:0;z-index:30;min-width:min(10rem, 76vw);max-height:65vh;max-width:min(85vw,22rem);width:max-content;overflow:auto;background:var(--ui-bg);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius);padding:.35rem;box-shadow:0 6px 20px #0005}
.world-switcher{position:relative;z-index:5}
.world-switcher a{display:block;padding:.5rem;color:var(--ui-fg)}
.world-switcher [aria-current="location"]{font-weight:bold;text-decoration:underline}
.world-switcher .ui-world-tools>*{flex-shrink:0}
"""

JS = r"""
const shell=document.querySelector('[data-world-shell]');
const panels=[...shell.querySelectorAll('[data-world-space]')];
const nav=[...shell.querySelectorAll('[data-world-nav] a')];
const menu=shell.querySelector('#world-switcher');
const cities=shell.querySelector('#cities-map');
const cityFloors=[...nav].filter(a=>a.dataset.scene==='cities').map(a=>a.hash.slice(1));
const favorites=shell.querySelector('#world-favorites');
const linked=new Map(nav.map(a=>[a.hash.slice(1),a]));
function route(){
 const hash=location.hash.slice(1), spot=document.getElementById(hash);
 const inside=spot?.closest('[data-world-space]')?.dataset.worldSpace;
 const cityPoint=inside==='cities'?cities.querySelector('.ui-floor a[href="#'+CSS.escape(hash)+'"]'):null;
 const floor=cityPoint?.closest('.ui-floor')?.dataset.floor;
 const name=linked.has(hash)?hash:inside==='cities'?(floor||'tokyo'):nav.find(a=>a.dataset.scene===inside)?.hash.slice(1)||'world';
 const entry=linked.get(name),scene=entry.dataset.scene;
 shell.dataset.worldRoute=name;
 for(const panel of panels)panel.hidden=panel.dataset.worldSpace!==scene;
 if(scene==='cities'&&!cityPoint){
   const select=cities.querySelector('.ui-world-goto');
   const radio=document.getElementById('cities-floor-'+name);
   if(radio&&!radio.checked){radio.checked=true;select.value=name;radio.dispatchEvent(new Event('change',{bubbles:true}));}
 }
 for(const a of nav){if(a===entry)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');}
 shell.querySelector('#world-space-name').textContent=entry.textContent;
}
function listFavorites(){
 const links=new Map();
 for(const a of shell.querySelectorAll('.ui-world-favs a')){
   const href=a.getAttribute('href');
   if(links.has(href))continue;
   const link=document.createElement('a');link.href=href;
   link.textContent=a.textContent.trim().replace(/🛗$/, '').trim();
   links.set(href,link);
 }
 favorites.replaceChildren(...(links.size?[...links.values()]:['まだありません']));
}
const observe=new MutationObserver(listFavorites);
for(const list of shell.querySelectorAll('.ui-world-favs'))observe.observe(list,{childList:true});
for(const panel of menu.querySelectorAll('details')){
 panel.addEventListener('toggle',()=>{if(panel.open)for(const other of menu.querySelectorAll('details[open]'))if(other!==panel)other.open=false;});
 panel.addEventListener('click',e=>{if(e.target.closest('a'))panel.open=false;});
}
cities.addEventListener('change',e=>{
 const control=e.target;
 if(!e.isTrusted||!(control.matches('.ui-world-goto')||control.name==='cities-floor')||!cityFloors.includes(control.value))return;
 if(shell.dataset.worldRoute!==control.value){history.pushState(null,'','#'+control.value);route();}
});
function updateRelicsPill(){
 const pill=shell.querySelector('#world-relics-count'),list=shell.querySelector('#world-relics-list');
 if(!pill||!list)return;
 const pressed=[...shell.querySelectorAll('.ui-world-take[aria-pressed="true"]')];
 const relics=pressed.filter(b=>b.dataset.itemId?.includes('-dragon-')||b.dataset.itemId?.includes('-chest-'));
 pill.textContent=`${relics.length}/14`;
 if(!relics.length){
  list.innerHTML='<p class="ui-world-note" style="padding:.5rem;margin:0">リバースロンドンや聖地ナゴヤで龍をお世話して、伝説の秘宝を手に入れよう！</p>';
  return;
 }
 const items=relics.map(b=>{
  const id=b.dataset.itemId,label=b.dataset.itemLabel||id,emoji=b.dataset.itemEmoji||'🏆';
  const targetId=id.replace(/^[a-z0-9-]+-spot-/,'');
  return `<a href="#${CSS.escape(targetId)}">${emoji} ${label}</a>`;
 });
 list.innerHTML=items.join('');
}
window.addEventListener('world-bag-change',updateRelicsPill);
addEventListener('hashchange',route);
shell.addEventListener('world-location',route);
route();listFavorites();updateRelicsPill();
"""


def document(ui, world, maps, places, css_href, js_href):
    specs = {name: world.example_data(name) for name in dict.fromkeys(spec for spec, _ in SPACES.values())}
    sections = []
    for spec, data in specs.items():
        route, *aliases = [key for key, (value, _) in SPACES.items() if value == spec]
        body = world.world_html(data, embedded=True)
        if spec == 'cities':
            body = maps.tokyo_links(ui, body, maps.tokyo_points(data))
        body = ''.join(f'<span id="{alias}"></span>' for alias in aliases) + body
        sections.append(f'<section id="{route}" data-world-space="{spec}" aria-label="{escape(SPACES[route][1])}">{body}</section>')
    nav = ''.join(f'<a href="#{route}" data-scene="{scene}">{escape(label)}</a>' for route, (scene, label) in SPACES.items())
    tools = ''.join(f'<a href="{escape(p["href"], quote=True)}">{escape(p["label"])}</a>' for p in places)
    relics_details = ('<details id="world-relics-menu"><summary id="world-relics-btn">🐉 竜と秘宝 <span id="world-relics-count">0/14</span></summary>'
                      '<div id="world-relics-list"><p class="ui-world-note" style="padding:.5rem;margin:0">リバースロンドンや聖地ナゴヤで龍をお世話して、伝説の秘宝を手に入れよう！</p></div></details>')
    header = ('<header class="ui-world-head"><div id="world-switcher" class="world-switcher"><nav class="ui-world-tools" aria-label="ワールド">'
              f'<details data-world-nav><summary aria-label="空間一覧">☰</summary><div>{nav}</div></details>'
              '<strong id="world-space-name">🌍 ワールド</strong>'
              + relics_details +
              '<details><summary>⭐ お気に入り</summary><div id="world-favorites">まだありません</div></details>'
              f'<details><summary>🧰 道具</summary><div>{tools}</div></details></nav></div></header>')
    body = ('<main><div data-world-shell>' + header + ''.join(sections) + '</div></main>'
            + ui.module_script(JS) + f'<script type="module" src="{js_href}"></script>'
            + ui.module_script(f'import "{js_href}";\n' + world.WORLD_RPG_JS) + maps.tokyo_modules(ui))
    css = ''.join(world.world_css(data, base=False) for data in specs.values()) + f'@layer components{{{CSS}}}'
    page = ui.render_document(title='🌍 ワールド', theme='modern', trusted_html=body, css=ui.bundled_css())
    return page.replace('</head>', f'<link rel="stylesheet" href="{css_href}"><style>{css}</style></head>', 1)
