"""Portfolio map links and local pins, using the pinned PSWB coordinate and city data."""
import html
import json
import re
from urllib.parse import urlencode


BODY = '''<main class="ui-page">
<h1>地図URL・ピン留め</h1>
<p>緯度・経度からApple MapsとGoogle MapsのURLを作成。ピンはこのブラウザに保存できます。</p>
<section class="ui-panel" aria-labelledby="point-title"><h2 id="point-title">地点</h2>
<label for="tokyo-point">パラレル東京の地点</label><select class="ui-input" id="tokyo-point"><option value="">自由入力</option>__OPTIONS__</select>
<p class="ui-muted">東京の地点はPSWBのミニチュア用の概略座標です。施設の正確な入口位置を示すものではありません。</p>
<div class="map-fields"><div><label for="latitude">緯度</label><input class="ui-input" id="latitude" inputmode="decimal" value="35.681340" autocomplete="off"></div>
<div><label for="longitude">経度</label><input class="ui-input" id="longitude" inputmode="decimal" value="139.766500" autocomplete="off"></div></div>
<label for="point-name">地点名（任意）</label><input class="ui-input" id="point-name" maxlength="80" autocomplete="off">
<label for="maps-input">地図URLから読み取る（任意）</label><input class="ui-input" id="maps-input" autocomplete="off" placeholder="Apple Maps / Google Maps の座標を含むURL">
<button class="ui-button" type="button" id="read-url">URLから座標を入力</button>
<p class="ui-muted">短縮URLは展開しません。座標を含む完全なURLを貼り付けてください。</p>
<p id="point-error" role="alert"></p></section>
<section class="ui-panel" id="map-result" aria-labelledby="result-title"><h2 id="result-title">開く・共有</h2>
<p><a class="ui-button" id="google-link" target="_blank" rel="noopener noreferrer">Google Mapsを開く</a>
<a class="ui-button" id="apple-link" target="_blank" rel="noopener noreferrer">Apple Mapsを開く</a></p>
<p><a id="tokyo-link" hidden>パラレル東京の対応地点へ</a></p>
<div class="map-actions"><button class="ui-button" type="button" id="pin">ピン留め</button>
<button class="ui-button" type="button" id="copy-google">Google URLをコピー</button>
<button class="ui-button" type="button" id="copy-apple">Apple URLをコピー</button>
<button class="ui-button" type="button" id="copy-share">地点リンクをコピー</button>
<button class="ui-button" type="button" id="share">共有</button></div>
<label for="share-text">共有テキスト</label><textarea class="ui-input" id="share-text" rows="7" readonly></textarea>
<p id="map-status" role="status" aria-live="polite"></p></section>
<section class="ui-panel"><h2>ピン留めした地点</h2><p id="pin-storage">このブラウザに保存。地点リンクを渡せば、相手も同じ座標を開けます。</p>
<ul id="pins"></ul></section>
<noscript><p>座標の入力・ピン留めにはJavaScriptが必要です。<a href="./tokyo.html">パラレル東京を開く</a></p></noscript>
</main>'''

CSS = '''label{display:block;margin:1rem 0 .35rem}.ui-input{width:100%;box-sizing:border-box}
.map-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:1rem}
.map-actions{display:flex;flex-wrap:wrap;gap:.5rem}button,a.ui-button{min-height:44px;margin:.3rem 0}
textarea{overflow-wrap:anywhere}#pins{padding:0;list-style:none}#pins li{display:flex;flex-wrap:wrap;align-items:center;gap:.75rem;margin:.5rem 0}
#point-error{color:var(--ui-danger,#c33)}[hidden]{display:none!important}h1{font-size:1.8rem}'''

SCRIPT = r'''
const {parseCoordinate,tryParseMapsUrl,mapsUrls,coordinateText}=globalThis.webUiCoordinates;
const points=__POINTS__, $=id=>document.getElementById(id), key='portfolio-map-pins/1';
const lat=$('latitude'),lon=$('longitude'),name=$('point-name'),picker=$('tokyo-point'),status=$('map-status');
const round=v=>Number(v).toFixed(6), same=(a,b)=>round(a.lat)===round(b.lat)&&round(a.lon)===round(b.lon);
let current=null,pins=[];
const checked=p=>{
 if(!p||typeof p!=='object'||typeof p.lat!=='number'||typeof p.lon!=='number'||typeof p.label!=='string')throw Error('invalid pin');
 const [a,b]=parseCoordinate(String(p.lat),String(p.lon));return {lat:a,lon:b,label:p.label.slice(0,80)};
};
try{const saved=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(saved))throw Error('invalid pins');
 for(const item of saved.slice(0,100)){try{const p=checked(item);if(!pins.some(v=>same(v,p)))pins.push(p)}catch{}}
}catch{$('pin-storage').textContent='保存済みピンを読めませんでした。この画面ではピン留めできます。'}
function save(){try{localStorage.setItem(key,JSON.stringify(pins));$('pin-storage').textContent='このブラウザに保存しました。'}
 catch{$('pin-storage').textContent='ブラウザに保存できません。この画面を閉じるまでのピン留めです。'}}
function shareURL(p){const url=new URL('./',location.href);url.search=new URLSearchParams({lat:round(p.lat),lon:round(p.lon),name:p.label});return url.href}
function show(){
 current=null;status.textContent='';$('point-error').textContent='';
 for(const id of ['google-link','apple-link','tokyo-link'])$(id).removeAttribute('href');
 $('tokyo-link').hidden=true;$('share-text').value='';
 try{const [a,b]=parseCoordinate(lat.value,lon.value);current={lat:a,lon:b,label:name.value.trim().slice(0,80)};
  const spot=points.find(p=>same(current,p));picker.value=spot?spot.id:'';
  const links=mapsUrls(a,b);$('google-link').href=links.google;$('apple-link').href=links.apple;
  if(spot){$('tokyo-link').href='./tokyo.html#cities-spot-'+spot.id;$('tokyo-link').hidden=false}
  $('share-text').value=[current.label||coordinateText(a,b),'Google Maps: '+links.google,'Apple Maps: '+links.apple,'地点リンク: '+shareURL(current)].join('\n');
 }catch(e){$('point-error').textContent='緯度は−90〜90、経度は−180〜180の数値を入力してください。'}
 for(const id of ['pin','copy-google','copy-apple','copy-share','share'])$(id).disabled=!current;
 $('pin').textContent=current&&pins.some(p=>same(p,current))?'ピンを更新':'ピン留め';
}
function setPoint(p){lat.value=round(p.lat);lon.value=round(p.lon);name.value=p.label;show()}
function renderPins(){
 $('pins').replaceChildren();
 if(!pins.length){const li=document.createElement('li');li.textContent='ピンはまだありません。';$('pins').append(li)}
 for(const p of pins){const li=document.createElement('li'),open=document.createElement('button'),remove=document.createElement('button');
  open.type=remove.type='button';open.className=remove.className='ui-button';
  open.textContent=p.label||coordinateText(p.lat,p.lon);open.addEventListener('click',()=>setPoint(p));
  remove.textContent='解除';remove.setAttribute('aria-label',(p.label||coordinateText(p.lat,p.lon))+'のピンを解除');
  remove.addEventListener('click',()=>{pins=pins.filter(v=>!same(v,p));save();renderPins();show()});li.append(open,remove);$('pins').append(li);
 }
}
for(const el of [lat,lon,name])el.addEventListener('input',show);
picker.addEventListener('change',()=>{const p=points.find(p=>p.id===picker.value);if(p)setPoint(p)});
$('read-url').addEventListener('click',()=>{const p=tryParseMapsUrl($('maps-input').value);if(!p){$('point-error').textContent='URLから座標を読み取れませんでした。';return}
 setPoint({lat:p[0],lon:p[1],label:''})});
$('pin').addEventListener('click',()=>{if(!current)return;const index=pins.findIndex(p=>same(p,current));
 if(index<0){if(pins.length>=100){status.textContent='ピンは100件までです。不要なピンを解除してください。';return}pins.push({...current})}
 else pins[index]={...current};save();renderPins();show();status.textContent='ピン留めしました。'});
async function copy(text){try{await navigator.clipboard.writeText(text);status.textContent='コピーしました。'}
 catch{$('share-text').value=text;$('share-text').focus();$('share-text').select();status.textContent='コピーできませんでした。選択したテキストをコピーしてください。'}}
$('copy-google').addEventListener('click',()=>copy($('google-link').href));
$('copy-apple').addEventListener('click',()=>copy($('apple-link').href));
$('copy-share').addEventListener('click',()=>current&&copy(shareURL(current)));
$('share').addEventListener('click',async()=>{if(!current)return;
 const text=$('share-text').value;
 if(!navigator.share){await copy(text);return}
 try{await navigator.share({title:current.label||'地図の地点',text,url:shareURL(current)});status.textContent='共有しました。'}
 catch(e){if(e.name!=='AbortError')await copy(text)}
});
const query=new URLSearchParams(location.search);
if(query.has('lat')||query.has('lon')){lat.value=query.get('lat')||'';lon.value=query.get('lon')||'';name.value=(query.get('name')||'').slice(0,80)}
else name.value=points[0].label;
renderPins();show();
'''


def render(ui) -> dict[str, str]:
    cities = ui.example_data('cities')
    tokyo = next(f for f in cities['floors'] if f['id'] == 'tokyo')
    points = [dict(id='tokyo-' + p['id'], label=p['label'], lat=p['lat'], lon=p['lon'])
              for p in tokyo['place']['points']]
    options = ''.join(f'<option value="{html.escape(p["id"], quote=True)}">{html.escape(p["label"])}</option>' for p in points)
    data = json.dumps(points, ensure_ascii=False).replace('<', '\\u003c')
    body = BODY.replace('__OPTIONS__', options)
    # The two inline modules execute in order; the shared module owns validation and URL encoding.
    body += ui.module_script(ui.js_source('coordinates.js')) + ui.module_script(SCRIPT.replace('__POINTS__', data))
    page = ui.render_document(title='地図URL・ピン留め', trusted_html=body, css=ui.bundled_css() + CSS)
    cities['title'], cities['floors'] = 'パラレル東京', [tokyo]
    cities['tools'] = {k: v for k, v in cities['tools'].items() if v.get('floor', 'tokyo') == 'tokyo'}
    world = ui.world_document(cities)
    # Keep PSWB's world behaviour and favorites; add a real-coordinate link to each existing sheet.
    for p in points:
        href = './?' + urlencode({'lat': ui.fixed(p['lat'], 6), 'lon': ui.fixed(p['lon'], 6), 'name': p['label']})
        link = f'<p><a class="ui-button" href="{html.escape(href, quote=True)}">この地点の地図URL・ピン留め</a></p>'
        pattern = r'(<article\b[^>]*\bid="cities-spot-' + re.escape(p['id']) + r'"[^>]*>.*?)(</article>)'
        world, count = re.subn(pattern, lambda m: m[1] + link + m[2], world, count=1, flags=re.S)
        if count != 1:
            raise ValueError(f'PSWB city sheet missing: {p["id"]}')
    world = world.replace('<body data-ui-theme="modern">', '<body data-ui-theme="modern"><main>', 1).replace('</body>', '</main></body>', 1)
    return {path: document.replace('<html lang="en">', '<html lang="ja">', 1) for path, document in
            [('tools/maps/index.html', page), ('tools/maps/tokyo.html', world)]}
