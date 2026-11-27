"""The Portfolio's one published world. Individual specs and standalone exports stay in world.py."""
import base64
import json
from html import escape
from pathlib import Path
from urllib.parse import quote

# Public fragments are stable and independent of the map engine's internal IDs.
SPACES = {
    'world': ('overworld', '🌍 村'),
    'school': ('school', '🏫 学校'),
    'tokyo': ('cities', '🗼 パラレル東京'),
    'london': ('cities', '🎡 Reverse London'),
    'paris': ('cities', '🥖 Fake Paris'),
    'camera': ('world', '🎬 カメラ'),
}

CSS = """
[data-world-shell]:not([data-world-route="paris"]) [data-city-item="paris"],
[data-world-shell]:not([data-world-route="london"]) [data-city-item="london"],
[data-world-space][hidden],[data-world-shell] [data-menu="favorites"],
[data-world-route]:not([data-world-route="tokyo"]) :is(#tokyo-range,#area-return){display:none!important}
[data-world-shell]>header{position:sticky;top:0;z-index:10;background:var(--ui-bg)}
[data-world-space]{position:relative;isolation:isolate;scroll-margin-top:5rem}
.world-switcher .ui-world-tools{flex-wrap:wrap;gap:.35rem}
.world-switcher details{position:relative}
.world-switcher summary{cursor:pointer;padding:.45rem;min-height:44px;display:grid;align-items:center}
.world-switcher details[open]>div{position:absolute;top:100%;left:0;z-index:30;min-width:min(10rem, 76vw);max-height:65vh;max-width:min(85vw,22rem);width:max-content;overflow:auto;background:var(--ui-bg);color:var(--ui-fg);border:1px solid var(--ui-border);border-radius:var(--ui-radius);padding:.35rem;box-shadow:0 6px 20px #0005}
.world-switcher details[data-world-guide]{position:static}
.world-switcher details[data-world-guide][open]>div{left:0;right:0;width:auto;max-width:34rem;padding:1rem}
.world-switcher{position:relative;z-index:5}
.dragon-care{display:none}
.dragon-scroll-dialog .dragon-care,#cities-map:has(.ui-spot[data-flip="🐉"][data-show="flip"]) .dragon-care{display:flex;align-items:center;gap:.5rem;flex-wrap:wrap}
.dragon-care button,.dragon-care input,.dragon-care select{min-height:44px}
.dragon-portrait{display:block;width:80px;image-rendering:pixelated}
#cities-map .ui-spot[data-flip="🐉"][data-show="flip"]{font-size:0;background-color:var(--dragon-fill,var(--ui-panel))}
#cities-map .ui-spot[data-flip="🐉"][data-show="flip"]::before{content:"";display:inline-block;width:32px;height:24px;background:var(--dragon-sprite) center/contain no-repeat;image-rendering:pixelated;filter:var(--dragon-hue)}
#cities-map .ui-spot[data-reaction]::after{font-size:1rem}
.ui-spot[data-show="flip"][data-reaction]::after{content:attr(data-reaction)}
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
addEventListener('hashchange',route);
shell.addEventListener('world-location',route);
route();listFavorites();
"""


EXPLORATION_SCROLL_SOURCE = "https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/904cff96506cb6b8d8e2afeaeb171d0da63f41eb/scripts/world.py#L2280-L2287"


def exploration_scroll_guide(world):
    effects = world.exploration_scroll_text()
    label = escape(world.EXPLORATION_SCROLL["label"])
    return (
        '<article aria-labelledby="exploration-guide-title">'
        f'<h2 id="exploration-guide-title">{label}をいつ使う？</h2>'
        '<h3>効果</h3>'
        f'<p>{escape(effects["reuse"])}</p>'
        f'<ul><li>{escape(effects["field"])}</li><li>{escape(effects["battle"])}</li></ul>'
        '<h3>戦闘での使いどころ</h3>'
        '<ul><li>巻物を持っていて薬草を補充したいとき、次が通常攻撃でHPに余裕があれば、薬草を探す手があります。</li>'
        '<li>次が強攻撃なら、まずぼうぎょを優先します。</li>'
        '<li>次の攻撃が分からなければ、敵の予告や「💡 ヒント」を確認します。</li></ul>'
        f'<p><a href="{EXPLORATION_SCROLL_SOURCE}">道具の定義（GitHub）</a>'
        '<a href="https://github.com/myon-bioinformatics/OnTautoLogy/pull/72">攻略判断の検証例（GitHub）</a></p></article>'
    )


def dialogue_graph(world):
    """Compile the GitHub-backed world facts into bounded paths using the pinned ONTO / OTL APIs."""
    from ontautology import reach
    from ontautology_shared.ontology import violations

    source = "https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/88954d2a64d4776a6291ddf6ef9796531c01c7ac/scripts/world.py"
    scrolls = "https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/831cf43785329c799966775153147b82ddc28638/scripts/world.py"
    reusable = "https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/blob/2f27ccdf682ad02d717b894889f1dc225d894925/scripts/world.py"
    pswb = "https://github.com/myon-bioinformatics/PySaiyanWeBoo/blob/e249a7c33071a5e70ff4866492506ebfd7719875/pysaiyanweboo.py"
    scroll = world.EXPLORATION_SCROLL
    scroll_text = world.exploration_scroll_text()
    field_target, battle_target = (scroll[mode]["target"] for mode in ("field", "battle"))
    nodes = {
        "昼ヶ丘": ("場所", ["ヒルガオカ"]), "サツマイモ": ("道具", ["さつまいも", "おいも", "いも", "🍠"]),
        "ドラゴン": ("住人", ["竜", "りゅう", "🐉"]), "木の看板": ("目印", ["看板", "nogard"]),
        "リバースロンドン": ("場所", ["ロンドン", "London"]), "癒しの水": ("道具", ["いやしの水", "マナのしずく"]),
        "火": ("地形", ["炎", "🔥"]), "パリ": ("場所", ["Paris"]), "MP": ("能力", ["魔力"]),
        "竜の巻物": ("道具", ["竜のまきもの"]), scroll["label"]: ("道具", ["探索のまきもの"]), "敵": ("相手", ["魔物"]),
        field_target: ("道具", ["未取得のアイテム"]), battle_target: ("道具", ["薬草"]),
        "冒険手帳": ("道具", ["手帳"]), "復活の呪文": ("形式", ["呪文", "じゅもん"]),
    }
    vocabulary = {"産物": (["場所"], "道具"), "好物": (["住人"], "道具"), "現れる": (["住人"], "目印"),
                  "所在地": (["目印", "地形"], "場所"), "消す": (["道具"], "地形"), "回復": (["道具"], "能力"),
                  "保存形式": (["道具"], "形式")}
    vocabulary.update({"発見対象": (["道具"], "道具"), "呼べる": (["道具"], "住人"), "攻撃対象": (["道具"], "相手")})
    facts = [
        ("竜の巻物", "呼べる", "ドラゴン", "ロンドンで初めてドラゴンをなでると竜の巻物を受け取る。旅先でも同じドラゴンを呼べる。", scrolls + "#L2571", scrolls + "#L2604"),
        (scroll["label"], "発見対象", field_target, scroll_text["field"] + scroll_text["reuse"], EXPLORATION_SCROLL_SOURCE),
        (scroll["label"], "発見対象", battle_target, scroll_text["battle"] + scroll_text["reuse"], EXPLORATION_SCROLL_SOURCE),
        ("竜の巻物", "攻撃対象", "敵", "戦闘中はドラゴンが敵1体を攻撃する。巻物は何度でも使える。", reusable + "#L2925"),
        ("昼ヶ丘", "産物", "サツマイモ", "昼ヶ丘でサツマイモが育つ。", source + "#L3322"),
        ("ドラゴン", "好物", "サツマイモ", world.POTATO_RUMOR, source + "#L3302"),
        ("ドラゴン", "現れる", "木の看板", "木の看板の陰にドラゴンがいるらしい。", source + "#L2580"),
        ("木の看板", "所在地", "リバースロンドン", "ロンドンには nogard と書かれた木の看板がある。", source + "#L3259"),
        ("癒しの水", "消す", "火", "癒しの水は正面の火を一つ消す。", source + "#L2540"),
        ("火", "所在地", "パリ", "パリでは村で拾った水を火に使える。", source + "#L2540"),
        ("癒しの水", "回復", "MP", "人に使うとMPを10回復する。", source + "#L3482"),
        ("冒険手帳", "保存形式", "復活の呪文", "冒険手帳はPSWBのかなの呪文で進捗を保存できる。", source + "#L2838", pswb + "#L86"),
    ]
    edges = [{"source": a, "relation": r, "target": b} for a, r, b, *_ in facts]
    findings = violations({"nodes": [{"id": n, "type": t} for n, (t, _) in nodes.items()], "edges": edges}, vocabulary)
    if findings:
        raise ValueError(f"invalid world dialogue graph: {findings}")
    walks = [dict(source=start, kind=r, target=end, fact=i) for i, (a, r, b, *_) in enumerate(facts)
             for start, end in ((a, b), (b, a))]
    paths = {}
    for start in nodes:
        steps = {}
        for row in reach(walks, [start])["rows"]:
            if row["depth"] <= 2:
                chain = row["via"]
                steps[row["node"]] = [*steps.get(chain[-2], []), row["edge"]["fact"]]
        paths[start] = list(steps.values())
    records = [{"edge": f"{a} → {r} → {b}", "text": msg, "urls": urls} for a, r, b, msg, *urls in facts]
    contexts = {
        field_target: ("field", "移動", "探索中", "非戦闘"),
        battle_target: ("battle", "戦闘", "バトル"),
    }
    for index, (subject, _, target, *_) in enumerate(facts):
        if subject == scroll["label"]:
            mode, *aliases = contexts[target]
            records[index].update(mode=mode, context=[scroll[mode]["context"], *aliases])
    return {"terms": {name: [name, *aliases] for name, (_, aliases) in nodes.items()}, "facts": records, "paths": paths}


def document(ui, world, maps, places, css_href, js_href, dialogue=""):
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
    header = ('<header class="ui-world-head"><div id="world-switcher" class="world-switcher"><nav class="ui-world-tools" aria-label="ワールド">'
              f'<details data-world-nav><summary aria-label="空間一覧">☰</summary><div>{nav}</div></details>'
              '<strong id="world-space-name">🌍 ワールド</strong>'
              '<details><summary>⭐ お気に入り</summary><div id="world-favorites">まだありません</div></details>'
              f'<details><summary>🧰 道具</summary><div>{tools}</div></details>'
              f'<details data-world-guide><summary>📖 攻略ガイド</summary><div>{exploration_scroll_guide(world)}</div></details>'
              '</nav></div></header>')
    knowledge = json.dumps(dialogue_graph(world), ensure_ascii=False, separators=(",", ":")).replace("<", r"\u003c")
    dialogue += f"\nconst worldKnowledge={knowledge};\n"
    grid = Path(__file__).with_name("london-dragon.json").read_text(encoding="utf-8")
    png = base64.b64encode(ui.pixel_grid_png(json.loads(grid))).decode("ascii")
    sprite = (f'<template id="dragon-art"><img class="dragon-portrait" alt="" src="data:image/png;base64,{png}">'
              f'<a download="london-dragon.json" href="data:application/json,{quote(grid, safe="")}">原画JSONを保存</a></template>')
    body = ('<main><div data-world-shell>' + sprite + header + ''.join(sections) + '</div></main>'
            + ui.module_script(JS) + f'<script type="module" src="{js_href}"></script>'
            + ui.module_script(f'import "{js_href}";\n' + dialogue + world.rpg_module("../vendor/web-ui/js/records.js")) + maps.tokyo_modules(ui))
    css = ''.join(world.world_css(data, base=False) for data in specs.values()) + f'@layer components{{{CSS}}}'
    page = ui.render_document(title='🌍 ワールド', theme='modern', trusted_html=body, css=ui.bundled_css())
    return page.replace('</head>', f'<link rel="stylesheet" href="{css_href}"><style>{css}</style></head>', 1)
