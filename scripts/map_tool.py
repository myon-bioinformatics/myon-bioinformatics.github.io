"""Portfolio map links and local pins: PySaiyanWeBoo's coordinates, and Parallel Tokyo from scripts/world.py."""
import html
import json
import re
from urllib.parse import urlencode


BODY = '''<main class="ui-page">
<h1>📍地図URL・座標ピン留め</h1>
<p>緯度・経度からApple MapsとGoogle MapsのURLを作成。ピンはこのブラウザに保存できます。</p>
<section class="ui-panel" aria-labelledby="point-title"><h2 id="point-title">地点</h2>
<label for="tokyo-point">パラレル東京の地点</label><select class="ui-input" id="tokyo-point"><option value="">自由入力</option>__OPTIONS__</select>
<p class="ui-muted">東京の地点はPSWBのミニチュア用の概略座標です。施設の正確な入口位置を示すものではありません。</p>
<div class="map-fields"><div><label for="latitude">緯度</label><input class="ui-input" id="latitude" inputmode="decimal" value="35.681340" autocomplete="off"></div>
<div><label for="longitude">経度</label><input class="ui-input" id="longitude" inputmode="decimal" value="139.766500" autocomplete="off"></div></div>
<label for="point-name">地点名（任意）</label><input class="ui-input" id="point-name" maxlength="80" autocomplete="off">
<div class="map-fields"><div><label for="radius-preset">範囲</label><select class="ui-input" id="radius-preset">
<option value="0">指定なし（地点のみ）</option><option value="25">GPS・25 m</option><option value="100" selected>建物・100 m</option>
<option value="350">駅・350 m</option><option value="1000">公園・1,000 m</option><option value="3000">地区・3,000 m</option><option value="custom">自由指定</option></select></div>
<div><label for="radius">半径（m、0は地点のみ）</label><input class="ui-input" id="radius" inputmode="decimal" value="100" autocomplete="off"></div></div>
<p id="range-error" role="alert"></p>
<label for="maps-input">地図URLから読み取る（任意）</label><input class="ui-input" id="maps-input" autocomplete="off" placeholder="Apple Maps / Google Maps の座標を含むURL">
<button class="ui-button" type="button" id="read-url">URLから座標を入力</button>
<p class="ui-muted">短縮URLは展開しません。座標を含む完全なURLを貼り付けてください。</p>
<p id="point-error" role="alert"></p></section>
<section class="ui-panel" id="map-result" aria-labelledby="result-title"><h2 id="result-title">開く・共有</h2>
<p><a class="ui-button" id="google-link" target="_blank" rel="noopener noreferrer">Google Mapsを開く</a>
<a class="ui-button" id="apple-link" target="_blank" rel="noopener noreferrer">Apple Mapsを開く</a></p>
<p><a id="tokyo-link" hidden>パラレル東京の対応地点へ</a></p>
<div id="area-result" hidden><h3>指定範囲</h3><pre class="ui-output" id="area-bounds"></pre>
<p><a class="ui-button" id="google-area-link" target="_blank" rel="noopener noreferrer">Google Mapsで範囲を開く</a>
<a class="ui-button" id="apple-area-link" target="_blank" rel="noopener noreferrer">Apple Mapsで範囲を開く</a></p>
<p class="ui-muted">範囲URLは表示範囲の指定です。地図上に円・矩形を描くものではありません。</p>
<details><summary>範囲データ（JSON）</summary><pre class="ui-output" id="area-json"></pre></details></div>
<div class="map-actions"><button class="ui-button" type="button" id="pin">ピン留め</button>
<button class="ui-button" type="button" id="copy-google">Google URLをコピー</button>
<button class="ui-button" type="button" id="copy-apple">Apple URLをコピー</button>
<button class="ui-button" type="button" id="copy-share">地点リンクをコピー</button>
<button class="ui-button" type="button" id="share">共有</button></div>
<label for="share-text">共有テキスト</label><textarea class="ui-input" id="share-text" rows="7" readonly></textarea>
__STATUS__</section>
<section class="ui-panel" id="nearby" hidden><h2>範囲内の東京の地点</h2><p id="nearby-status"></p><ul id="nearby-list"></ul></section>
<section class="ui-panel"><h2>ピン留めした地点</h2><p id="pin-storage">このブラウザに保存。地点リンクを渡せば、相手も同じ座標を開けます。</p>
<ul id="pins"></ul></section>
<noscript><p>座標の入力・ピン留めにはJavaScriptが必要です。<a href="./#tokyo">パラレル東京を開く</a></p></noscript>
</main>'''

CSS = '''label{display:block;margin:1rem 0 .35rem}.ui-input{width:100%;box-sizing:border-box}
.map-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:1rem}
.map-actions{display:flex;flex-wrap:wrap;gap:.5rem}button,a.ui-button{min-height:44px;margin:.3rem 0}
a.ui-button{display:inline-flex;align-items:center;max-width:100%;box-sizing:border-box}
textarea{overflow-wrap:anywhere}#pins{padding:0;list-style:none}#pins li{display:flex;flex-wrap:wrap;align-items:center;gap:.75rem;margin:.5rem 0}
#point-error,#range-error{color:var(--ui-danger,#c33)}pre{white-space:pre-wrap;overflow-wrap:anywhere}
[hidden]{display:none!important}h1{font-size:1.8rem}'''

# One radius contract for pins, query strings and the Tokyo handoff.
RANGE_HELPERS = r'''
function readRadius(raw){
 const text=String(raw).normalize('NFKC').trim().replace(/\u2212/g,'-');
 if(!/^[+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(text))throw Error('半径は0以上の有限な数値を入力してください。');
 const value=Number(text);if(!Number.isFinite(value)||value<0)throw Error('半径は0以上の有限な数値を入力してください。');return value;
}
'''

SCRIPT = r'''
import { copyText } from './vendor/web-ui/js/ui.js';   // 🧰 from the screen, tools/

const {parseCoordinate,tryParseMapsUrl,mapsUrls,coordinateText,toleranceArea,areaTexts}=globalThis.webUiCoordinates;
const points=__POINTS__, $=id=>document.getElementById(id), key='portfolio-map-pins/1';
const lat=$('latitude'),lon=$('longitude'),name=$('point-name'),picker=$('tokyo-point'),status=$('map-status'),radius=$('radius'),preset=$('radius-preset');
__RANGE_HELPERS__
const round=v=>Number(v).toFixed(6), same=(a,b)=>round(a.lat)===round(b.lat)&&round(a.lon)===round(b.lon);
const distance=(a,b)=>{const rad=v=>v*Math.PI/180,dy=rad(b.lat-a.lat),dx=rad(b.lon-a.lon);
 const h=Math.sin(dy/2)**2+Math.cos(rad(a.lat))*Math.cos(rad(b.lat))*Math.sin(dx/2)**2;
 return 2*__EARTH_RADIUS__*Math.asin(Math.sqrt(Math.min(1,Math.max(0,h))))};
let current=null,pins=[];
const checked=p=>{
 if(!p||typeof p!=='object'||typeof p.lat!=='number'||typeof p.lon!=='number'||typeof p.label!=='string'||typeof p.radius_m!=='number')throw Error('invalid pin');
 const [a,b]=parseCoordinate(String(p.lat),String(p.lon));return {lat:a,lon:b,label:p.label.slice(0,80),radius_m:readRadius(p.radius_m)};
};
try{const saved=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(saved))throw Error('invalid pins');
 for(const item of saved.slice(0,100)){try{const p=checked(item);if(!pins.some(v=>same(v,p)))pins.push(p)}catch{}}
}catch{$('pin-storage').textContent='保存済みピンを読めませんでした。この画面ではピン留めできます。'}
function save(){try{localStorage.setItem(key,JSON.stringify(pins));$('pin-storage').textContent='このブラウザに保存しました。'}
 catch{$('pin-storage').textContent='ブラウザに保存できません。この画面を閉じるまでのピン留めです。'}}
function shareURL(p){const url=new URL(location.href);url.search=new URLSearchParams({lat:round(p.lat),lon:round(p.lon),name:p.label,radius_m:String(p.radius_m)});return url.href}
function tokyoURL(p,spot){const url=new URL(shareURL(p));url.hash='cities-spot-'+spot.id;return url.href}   // 🌍 the world is a panel of this screen
function shareText(p){const links=mapsUrls(p.lat,p.lon),text=[p.label||coordinateText(p.lat,p.lon),'Google Maps: '+links.google,'Apple Maps: '+links.apple];
 if(p.radius_m>0){const area=areaTexts(toleranceArea(p.lat,p.lon,p.radius_m));text.push('半径: '+p.radius_m+' m','Google Maps（範囲）: '+area.google_area_url,'Apple Maps（範囲）: '+area.apple_area_url)}
 text.push('地点リンク: '+shareURL(p));return text.join('\n')}
function show(){
 current=null;status.textContent='';$('point-error').textContent='';$('range-error').textContent='';
 for(const id of ['google-link','apple-link','tokyo-link','google-area-link','apple-area-link'])$(id).removeAttribute('href');
 $('tokyo-link').hidden=true;$('area-result').hidden=true;$('nearby').hidden=true;$('nearby-list').replaceChildren();$('area-json').textContent='';$('area-bounds').textContent='';$('share-text').value='';
 let coordinate;
 try{coordinate=parseCoordinate(lat.value,lon.value)}catch(e){$('point-error').textContent='緯度は−90〜90、経度は−180〜180の数値を入力してください。'}
 try{const r=readRadius(radius.value);preset.value=[...preset.options].some(o=>o.value===String(r))?String(r):'custom';
  if(coordinate){const [a,b]=coordinate;current={lat:a,lon:b,label:name.value.trim().slice(0,80),radius_m:r};
  const spot=points.find(p=>same(current,p));picker.value=spot?spot.id:'';
  const links=mapsUrls(a,b);$('google-link').href=links.google;$('apple-link').href=links.apple;
  if(spot){$('tokyo-link').href=tokyoURL(current,spot);$('tokyo-link').hidden=false}
  if(r>0){const area=toleranceArea(a,b,r),text=areaTexts(area);$('area-result').hidden=false;
   $('area-bounds').textContent='半径: '+r+' m\n南: '+round(area.south)+' / 北: '+round(area.north)+'\n西: '+round(area.west)+' / 東: '+round(area.east)+(area.wraps?'\n日付変更線をまたぎます。':'')+(area.full_longitude?'\n全経度を含みます。':'');
   $('area-json').textContent=text.json;$('google-area-link').href=text.google_area_url;$('apple-area-link').href=text.apple_area_url;
   const nearby=points.map(p=>({point:p,meters:distance(current,p)})).filter(p=>p.meters<=r).sort((a,b)=>a.meters-b.meters);
   $('nearby').hidden=false;$('nearby-status').textContent=nearby.length+'件（中心からの直線距離）';
   for(const item of nearby){const li=document.createElement('li'),a=document.createElement('a');a.href=tokyoURL(current,item.point);a.textContent=item.point.label+'（'+Math.round(item.meters)+' m）';li.append(a);$('nearby-list').append(li)}
  }
  $('share-text').value=shareText(current);
 }}catch(e){$('range-error').textContent=e.message;preset.value='custom'}
 for(const id of ['pin','copy-google','copy-apple','copy-share','share'])$(id).disabled=!current;
 $('pin').textContent=current&&pins.some(p=>same(p,current))?'ピンを更新':'ピン留め';
}
function setPoint(p){lat.value=round(p.lat);lon.value=round(p.lon);name.value=p.label;if(p.radius_m!==undefined)radius.value=String(p.radius_m);show()}
function renderPins(){
 $('pins').replaceChildren();
 if(!pins.length){const li=document.createElement('li');li.textContent='ピンはまだありません。';$('pins').append(li)}
 for(const p of pins){const li=document.createElement('li'),open=document.createElement('button'),remove=document.createElement('button');
  open.type=remove.type='button';open.className=remove.className='ui-button';
  open.textContent=p.label||coordinateText(p.lat,p.lon);open.addEventListener('click',()=>setPoint(p));
  remove.textContent='解除';remove.setAttribute('aria-label',(p.label||coordinateText(p.lat,p.lon))+'のピンを解除');
  const range=document.createElement('span');range.textContent=p.radius_m>0?'半径 '+p.radius_m+' m':'地点のみ';
  remove.addEventListener('click',()=>{pins=pins.filter(v=>!same(v,p));save();renderPins();show()});li.append(open,range,remove);$('pins').append(li);
 }
}
for(const el of [lat,lon,name,radius])el.addEventListener('input',show);
preset.addEventListener('change',()=>{if(preset.value!=='custom')radius.value=preset.value;show()});
picker.addEventListener('change',()=>{const p=points.find(p=>p.id===picker.value);if(p)setPoint(p)});
$('read-url').addEventListener('click',()=>{const p=tryParseMapsUrl($('maps-input').value);if(!p){$('point-error').textContent='URLから座標を読み取れませんでした。';return}
 setPoint({lat:p[0],lon:p[1],label:''})});
$('pin').addEventListener('click',()=>{if(!current)return;const index=pins.findIndex(p=>same(p,current));
 if(index<0){if(pins.length>=100){status.textContent='ピンは100件までです。不要なピンを解除してください。';return}pins.push({...current})}
 else pins[index]={...current};save();renderPins();show();status.textContent='ピン留めしました。'});
async function copy(text){try{await copyText(text);status.textContent='コピーしました。'}
 catch{$('share-text').value=text;$('share-text').focus();$('share-text').select();status.textContent='コピーできませんでした。選択したテキストをコピーしてください。'}}
$('copy-google').addEventListener('click',()=>copy($('google-link').href));
$('copy-apple').addEventListener('click',()=>copy($('apple-link').href));
$('copy-share').addEventListener('click',()=>current&&copy(shareURL(current)));
$('share').addEventListener('click',async()=>{if(!current)return;
 const text=shareText(current);
 if(!navigator.share){await copy(text);return}
 try{await navigator.share({title:current.label||'地図の地点',text,url:shareURL(current)});status.textContent='共有しました。'}
 catch(e){if(e.name!=='AbortError')await copy(text)}
});
const query=new URLSearchParams(location.search);
if(query.has('lat')||query.has('lon')){lat.value=query.get('lat')||'';lon.value=query.get('lon')||'';name.value=(query.get('name')||'').slice(0,80);radius.value=query.get('radius_m')??'100'}
else name.value=points[0].label;
renderPins();show();
'''

TOKYO_SCRIPT = r'''
__RANGE_HELPERS__
const query=new URLSearchParams(location.search),banner=document.getElementById('tokyo-range');
try{const radius=readRadius(query.get('radius_m')??'100');
 for(const link of document.querySelectorAll('.map-point-link')){const url=new URL(link.href);url.searchParams.set('radius_m',String(radius));link.href=url.href}
 if(query.has('lat')||query.has('lon')){
  const [lat,lon]=globalThis.webUiCoordinates.parseCoordinate(query.get('lat')||'',query.get('lon')||'');
  const back=new URL('./',location.href);back.search=new URLSearchParams({lat:lat.toFixed(6),lon:lon.toFixed(6),name:(query.get('name')||'').slice(0,80),radius_m:String(radius)});back.hash='maps';
  document.getElementById('area-return').href=back.href;document.getElementById('area-return').hidden=false;
 }
 if(radius>0&&query.has('radius_m')){banner.hidden=false;document.getElementById('tokyo-range-label').textContent='指定範囲：半径 '+radius+' m。地点を選んだ後も半径を引き継ぎます。'}
}catch{banner.hidden=false;document.getElementById('tokyo-range-label').textContent='指定範囲を読み取れませんでした。'}
'''


COORDINATES_MODULE = '<script type="module" src="./vendor/web-ui/js/coordinates.js"></script>'   # 🧰 from tools/ (the screen)


def tokyo_points(cities):
    tokyo = next(f for f in cities['floors'] if f['id'] == 'tokyo')
    return [dict(id='tokyo-' + p['id'], label=p['label'], lat=p['lat'], lon=p['lon'])
            for p in tokyo['place']['points']]


def map_document(ui, points):
    options = ''.join(f'<option value="{html.escape(p["id"], quote=True)}">{html.escape(p["label"])}</option>' for p in points)
    data = json.dumps(points, ensure_ascii=False).replace('<', '\\u003c')
    body = BODY.replace('__OPTIONS__', options).replace('__STATUS__', ui.status_html(id='map-status'))
    # The two inline modules execute in order; the shared module owns validation and URL encoding.
    script = SCRIPT.replace('__POINTS__', data).replace('__RANGE_HELPERS__', RANGE_HELPERS).replace('__EARTH_RADIUS__', str(ui.EARTH_RADIUS_M))
    body += COORDINATES_MODULE + ui.module_script(script)
    return ui.render_document(title='📍地図URL・座標ピン留め', trusted_html=body, css=ui.bundled_css() + CSS)


def tokyo_links(ui, world, points):
    # Keep PSWB's world behaviour and favorites; add a real-coordinate link to each existing sheet.
    for p in points:
        href = './?' + urlencode({'lat': ui.fixed(p['lat'], 6), 'lon': ui.fixed(p['lon'], 6), 'name': p['label']}) + '#maps'   # 🧰 the screen's map panel
        link = f'<p><a class="ui-button map-point-link" href="{html.escape(href, quote=True)}">この地点の地図URL・座標ピン留め</a></p>'
        pattern = r'(<article\b[^>]*\bid="cities-spot-' + re.escape(p['id']) + r'"[^>]*>.*?)(</article>)'
        world, count = re.subn(pattern, lambda m: m[1] + link + m[2], world, count=1, flags=re.S)
        if count != 1:
            raise ValueError(f'PSWB city sheet missing: {p["id"]}')
    banner = '<p id="tokyo-range" hidden><span id="tokyo-range-label"></span></p><p><a id="area-return" hidden>元の指定範囲へ戻る</a></p>'
    return banner + world


def tokyo_modules(ui):
    return COORDINATES_MODULE + ui.module_script(TOKYO_SCRIPT.replace('__RANGE_HELPERS__', RANGE_HELPERS))
