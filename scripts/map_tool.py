"""Portfolio map links and local pins: PySaiyanWeBoo's coordinates part (places, 📌 pins, share) fed with Parallel Tokyo's points from
scripts/world.py, and the way back from a place of the world to the map."""
import html
import re
from urllib.parse import urlencode


# What the tool says, in the site's language (PySaiyanWeBoo's coordinates part: any word left out stays English).
WORDS = {
    'title': '地点', 'lead': '緯度・経度から Apple Maps と Google Maps の URL を作成。ピンはこのブラウザに保存できます。',
    'place': 'パラレル東京の地点', 'free': '自由入力', 'lat': '緯度', 'lon': '経度', 'name': '地点名（任意）',
    'url': '地図URLから読み取る（任意。短縮URLは展開しません）', 'use': 'URLから座標を入力', 'valid': '有効な座標です。',
    'bad_point': '緯度は−90〜90、経度は−180〜180の数値を入力してください。', 'bad_url': 'URLから座標を読み取れませんでした。',
    'tolerance': '範囲', 'r0': '指定なし（地点のみ）', 'r25': 'GPS', 'r100': '建物', 'r350': '駅', 'r1000': '公園', 'r3000': '地区', 'custom': '自由指定',
    'custom_radius': '半径（m、自由指定のとき）', 'zoom': 'タイルのズーム（0〜22）',
    'open_google': 'Google Mapsを開く', 'open_apple': 'Apple Mapsを開く', 'open_place': 'パラレル東京の対応地点へ',
    'pin': 'ピン留め', 'repin': 'ピンを更新', 'unpin': '解除', 'pins': 'ピン留めした地点', 'no_pins': 'ピンはまだありません。',
    'pin_note': 'このブラウザに保存。地点リンクを渡せば、相手も同じ座標を開けます。', 'saved': 'このブラウザに保存しました。',
    'unsaved': 'ブラウザに保存できません。この画面を閉じるまでのピン留めです。', 'unreadable': '保存済みピンを読めませんでした。この画面ではピン留めできます。',
    'full': 'ピンは100件までです。不要なピンを解除してください。', 'pinned': 'ピン留めしました。',
    'copy_google': 'Google URLをコピー', 'copy_apple': 'Apple URLをコピー', 'copy_link': '地点リンクをコピー', 'share': '共有', 'share_text': '共有テキスト',
    'copied': 'コピーしました。', 'uncopied': 'コピーできませんでした。選択したテキストをコピーしてください。', 'shared': '共有しました。',
    'nearby': '範囲内の東京の地点', 'within': '{n}件（中心からの直線距離）', 'point_only': '地点のみ', 'radius': '半径: {n} m', 'link': '地点リンク',
    'details': '範囲データ・すべての形式', 'json': '範囲データ（JSON）', 'g_area': 'Google Maps（範囲）', 'a_area': 'Apple Maps（範囲）',
}

# One radius contract for the query string and the Tokyo handoff.
RANGE_HELPERS = r'''
function readRadius(raw){
 const text=String(raw).normalize('NFKC').trim().replace(/\u2212/g,'-');
 if(!/^[+]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(text))throw Error('半径は0以上の有限な数値を入力してください。');
 const value=Number(text);if(!Number.isFinite(value)||value<0)throw Error('半径は0以上の有限な数値を入力してください。');return value;
}
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


def map_spec(points):
    """📍 The coordinates part's spec: Tokyo's points are the places (each opens its sheet in the world of this screen), 📌 pins and share on."""
    first = points[0]
    return {'id': 'map', 'point': {'lat': first['lat'], 'lon': first['lon'], 'label': first['label']}, 'radius': 100, 'pins': 'portfolio-map-pins/1', 'share': True,
            'places': [{**point, 'href': '#cities-spot-' + point['id']} for point in points], 'words': WORDS}


def map_document(ui, points):
    body = ('<main class="ui-page"><h1>📍地図URL・座標ピン留め</h1>' + ui.coordinates_html(map_spec(points))
            + '<p class="ui-muted">東京の地点はPSWBのミニチュア用の概略座標です。施設の正確な入口位置を示すものではありません。'
              '範囲URLは表示範囲の指定で、地図上に円・矩形を描くものではありません。</p>'
              '<noscript><p>座標の入力・ピン留めにはJavaScriptが必要です。<a href="./#tokyo">パラレル東京を開く</a></p></noscript></main>')
    # 🧰 The screen shows this panel when asked for: the world may have loaded the module first, so the part is bound here (once).
    bind = ui.module_script('globalThis.webUiCoordinates.bindCoordinates();')
    return ui.render_document(title='📍地図URL・座標ピン留め', trusted_html=body + COORDINATES_MODULE + bind, css=ui.bundled_css())


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
