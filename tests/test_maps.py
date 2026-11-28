"""Map sharing and persistent pins in Chromium; the exercised flow also becomes a CI GIF."""
import base64
import json
import subprocess
from urllib.parse import parse_qs, urlsplit

import pytest

from test_front_page import ROOT, browser, expect, site  # shared staged site and Chromium


def test_map_links_pins_share_and_tokyo_with_gif(site, browser):
    import pysaiyanweboo as ui

    frames, passed = [], False
    context = browser.new_context(viewport={'width': 392, 'height': 840},
                                  permissions=['clipboard-read', 'clipboard-write'])
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.route('https://**', lambda route: route.abort())

    def shot(label):
        frames.append({'png': base64.b64encode(page.screenshot()).decode('ascii'),
                       'caption': label, 'ok': True, 'delay': 1200})

    try:
        page.goto(site[1] + '/tools/#maps')
        expect(page).to_have_title('📍 地図URL・座標ピン留め')
        expect(page.get_by_role('heading', level=1)).to_have_text('📍 地図URL・座標ピン留め')
        page.locator('#radius-preset').select_option('350')
        page.locator('#tokyo-point').select_option('tokyo-kanda')
        expect(page.locator('#point-name')).to_have_value('神田')
        point = '35.691800,139.770900'
        google = page.locator('#google-link').get_attribute('href')
        apple = page.locator('#apple-link').get_attribute('href')
        assert parse_qs(urlsplit(google).query) == {'api': ['1'], 'query': [point]}
        assert parse_qs(urlsplit(apple).query)['ll'] == [point]
        page.locator('#map-result').scroll_into_view_if_needed()
        shot('Kanda: point links and a 350 m region')
        page.locator('#pin').click()
        expect(page.locator('#pins')).to_contain_text('神田')
        page.locator('#pin').click()  # same coordinate updates rather than duplicating
        assert page.locator('#pins li').count() == 1
        page.locator('#copy-share').click()
        expect(page.locator('#map-status')).to_have_text('コピーしました。')
        shared = page.evaluate('navigator.clipboard.readText()')
        assert parse_qs(urlsplit(shared).query)['lat'] == ['35.691800']
        assert parse_qs(urlsplit(shared).query)['radius_m'] == ['350']
        page.reload()
        expect(page.locator('#pins')).to_contain_text('神田')
        page.locator('#pins button').first.click()
        expect(page.locator('#point-name')).to_have_value('神田')
        expect(page.locator('#radius')).to_have_value('350')
        expect(page.locator('#pins')).to_contain_text('半径 350 m')
        page.locator('#pins').scroll_into_view_if_needed()
        shot('Pin retained after reload; duplicate pin updates')

        # A recipient's browser opens the coordinate, without silently saving a pin.
        other = browser.new_context()
        try:
            recipient = other.new_page()
            recipient.goto(shared)
            expect(recipient.locator('#latitude')).to_have_value('35.691800')
            expect(recipient.locator('#point-name')).to_have_value('神田')
            expect(recipient.locator('#radius')).to_have_value('350')
            assert json.loads(recipient.locator('#area-json').text_content())['radius_m'] == 350
            expect(recipient.locator('#pins')).to_have_text('ピンはまだありません。')
        finally:
            other.close()

        page.locator('#tokyo-link').click()
        expect(page.locator('#worlds .map-point-link')).to_have_count(21)    # 🌍 the world is a panel of the same screen
        assert urlsplit(page.url).path == '/tools/'
        assert set(page.locator('#cities-map .ui-floor').evaluate_all('(floors) => floors.map(f => f.dataset.floor)')) >= {'tokyo', 'london', 'paris'}
        # PSWB asks for the walking avatar on entry; choose it through the normal UI.
        expect(page.locator('#cities-map .ui-world-pick')).to_be_visible()
        page.locator('#cities-map .ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#tokyo-range')).to_contain_text('半径 350 m')
        sheet = page.locator('#cities-spot-tokyo-kanda')
        expect(sheet).to_be_visible()
        shot('Parallel Tokyo: Kanda sheet')
        sheet.get_by_role('link', name='この地点の地図URL・座標ピン留め').click()
        expect(page.locator('#latitude')).to_have_value('35.691800')
        expect(page.locator('#tokyo-point')).to_have_value('tokyo-kanda')
        expect(page.locator('#radius')).to_have_value('350')
        page.locator('#map-result').scroll_into_view_if_needed()
        shot('Tokyo sheet returns to the same real coordinates')
        # Native share is verified at its browser API boundary; no external recipient is contacted.
        page.evaluate('Object.defineProperty(navigator,"share",{configurable:true,value:async data=>{window.shared=data}})')
        page.locator('#share').click()
        expect(page.locator('#map-status')).to_have_text('共有しました。')
        payload = page.evaluate('window.shared')
        assert google in payload['text'] and apple in payload['text']
        assert '半径: 350 m' in payload['text']
        assert payload['url'] == shared
        page.get_by_role('button', name='神田のピンを解除').click()
        page.reload()
        expect(page.locator('#pins')).to_have_text('ピンはまだありません。')
        assert errors == []
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        passed = True
    finally:
        if not passed:
            shot('FAILED: last observed browser state')
            frames[-1]['ok'] = False
        if frames:
            # Reuse the same PSWB encoder as the existing home-screen test and BTK recorder.
            encoder = context.new_page()
            encoder.set_content(ui.gif_recorder_document())
            encoder.evaluate('() => {window.rec=new UiGif.Recorder({width:392,height:840,caption:32})}')
            encoder.evaluate('items => rec.add(items)', frames)
            encoded = encoder.evaluate('() => rec.encodeBase64({})')
            target = ui.gif_targets(ROOT / 'test-results/maps', ['map-links-pins'], run_details=['timestamp'])['map-links-pins']
            target.write_bytes(base64.b64decode(encoded['gif']))
            target.with_suffix('.json').write_text(json.dumps({
                'schema': 'portfolio-map-browser/1', 'status': 'success' if passed else 'failure',
                'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'browser': browser.version, 'frames': [f['caption'] for f in frames], 'page_errors': errors,
            }, ensure_ascii=False, indent=2), encoding='utf-8')
        context.close()


@pytest.mark.parametrize('lat,lon', [('', '139'), ('NaN', '139'), ('Infinity', '139'), ('91', '139'), ('35', '-181')])
def test_invalid_coordinates_clear_stale_links(site, browser, lat, lon):
    page = browser.new_page()
    try:
        page.goto(site[1] + '/tools/#maps')
        page.locator('#latitude').fill(lat)
        page.locator('#longitude').fill(lon)
        expect(page.locator('#point-error')).not_to_be_empty()
        assert page.locator('#google-link').get_attribute('href') is None
        assert page.locator('#apple-link').get_attribute('href') is None
        expect(page.locator('#pin')).to_be_disabled()
        expect(page.locator('#share-text')).to_have_value('')
    finally:
        page.close()


def test_maps_url_storage_and_clipboard_fallbacks(site, browser):
    page = browser.new_page()
    try:
        page.add_init_script('''Storage.prototype.setItem=()=>{throw Error('denied')};
            Object.defineProperty(navigator,'clipboard',{value:{writeText:async()=>{throw Error('denied')}}});
            Object.defineProperty(navigator,'share',{value:undefined});''')
        page.goto(site[1] + '/tools/?lat=0&lon=0&name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E#maps')
        expect(page.locator('#latitude')).to_have_value('0')
        page.locator('#pin').click()
        expect(page.locator('#pin-storage')).to_contain_text('保存できません')
        assert page.locator('#pins img').count() == 0
        page.evaluate("""() => {
            document.execCommand = command => {
                if (command !== 'copy') return false;
                window.fallbackCopy = document.activeElement.value;
                return true;
            };
        }""")
        page.locator('#copy-apple').click()
        expect(page.locator('#map-status')).to_have_text('コピーしました。')
        assert page.evaluate('window.fallbackCopy') == page.locator('#apple-link').get_attribute('href')
        page.evaluate("() => { document.execCommand = () => false; }")
        page.locator('#share').click()
        expect(page.locator('#map-status')).to_contain_text('選択したテキスト')
        expect(page.locator('#share-text')).to_be_focused()
        assert page.locator('#share-text').evaluate('(field) => field.selectionEnd - field.selectionStart') == len(
            page.locator('#share-text').input_value()
        )
        assert '0.000000%2C0.000000' in page.locator('#share-text').input_value()
        page.locator('#maps-input').fill('https://maps.apple.com/?ll=35.6918%2C139.7709&q=Kanda')
        page.locator('#read-url').click()
        expect(page.locator('#tokyo-point')).to_have_value('tokyo-kanda')
        page.locator('#maps-input').fill('https://maps.app.goo.gl/example')
        page.locator('#read-url').click()
        expect(page.locator('#point-error')).to_contain_text('読み取れません')
        page.locator('#latitude').fill('－９０')
        page.locator('#longitude').fill('１８０')
        expect(page.locator('#point-error')).to_be_empty()
        expect(page.locator('#tokyo-link')).to_be_hidden()
        assert '-90.000000%2C180.000000' in page.locator('#google-link').get_attribute('href')
        page.locator('#radius').fill('３５０')
        expect(page.locator('#radius-preset')).to_have_value('350')
        assert json.loads(page.locator('#area-json').text_content())['radius_m'] == 350
    finally:
        page.close()


@pytest.mark.parametrize('radius', ['', '-1', 'NaN', 'Infinity', '1e309', 'true'])
def test_invalid_radius_clears_range_and_disables_pin(site, browser, radius):
    page = browser.new_page()
    try:
        page.goto(site[1] + '/tools/#maps')
        expect(page.locator('#area-result')).to_be_visible()
        page.locator('#radius').fill(radius)
        expect(page.locator('#range-error')).not_to_be_empty()
        expect(page.locator('#area-result')).to_be_hidden()
        expect(page.locator('#area-json')).to_be_empty()
        assert page.locator('#apple-area-link').get_attribute('href') is None
        expect(page.locator('#pin')).to_be_disabled()
        expect(page.locator('#share-text')).to_have_value('')
    finally:
        page.close()


@pytest.mark.parametrize('lat,lon,radius,wraps', [(0, 179.99, 3500, True), (90, 0, 100, False)])
def test_range_handles_date_line_and_pole(site, browser, lat, lon, radius, wraps):
    page = browser.new_page()
    try:
        page.goto(site[1] + f'/tools/?lat={lat}&lon={lon}&radius_m={radius}#maps')
        expect(page.locator('#area-result')).to_be_visible()
        area = json.loads(page.locator('#area-json').text_content())
        assert area['radius_m'] == radius
        assert area['bounds']['wraps_antimeridian'] == wraps
        assert -90 <= area['bounds']['south'] <= area['bounds']['north'] <= 90
        apple = parse_qs(urlsplit(page.locator('#apple-area-link').get_attribute('href')).query)
        assert 'spn' not in apple  # a single span cannot describe these two cases
        expect(page.locator('#nearby-status')).to_contain_text('0件')
    finally:
        page.close()


def test_nearby_city_handoff_preserves_radius_and_original_area(site, browser):
    page = browser.new_page()
    try:
        page.goto(site[1] + '/tools/?lat=35.68135&lon=139.7665&name=中心&radius_m=350#maps')
        expect(page.locator('#tokyo-link')).to_be_hidden()  # arbitrary centre, rather than an exact city coordinate
        expect(page.locator('#nearby-list')).to_contain_text('丸の内北口')
        expect(page.locator('#nearby-list')).to_contain_text('八重洲中央口')
        expect(page.locator('#nearby-list')).not_to_contain_text('大手町')
        page.locator('#nearby-list').get_by_role('link', name='丸の内中央口', exact=False).click()
        page.locator('#cities-map .ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#cities-spot-tokyo-marunouchi-c')).to_be_visible()
        page.locator('#area-return').click()
        expect(page.locator('#latitude')).to_have_value('35.681350')
        expect(page.locator('#point-name')).to_have_value('中心')
        expect(page.locator('#radius')).to_have_value('350')
        page.locator('#nearby-list').get_by_role('link', name='丸の内中央口', exact=False).click()
        expect(page.locator('#cities-map .ui-world-pick-grid')).to_be_hidden()   # 🧰 one screen: the world kept its walker (no reload)
        page.locator('#cities-spot-tokyo-marunouchi-c .map-point-link').click()
        expect(page.locator('#latitude')).to_have_value('35.681340')
        expect(page.locator('#radius')).to_have_value('350')
        page.locator('#radius-preset').select_option('0')
        expect(page.locator('#area-result')).to_be_hidden()
        expect(page.locator('#nearby')).to_be_hidden()
    finally:
        page.close()


def test_city_bookmark_restores_spot_and_area(site, browser):
    page = browser.new_page()
    try:
        suffix = '?lat=35.68135&lon=139.7665&name=Centre&radius_m=0#cities-spot-tokyo-kanda'
        assert page.request.get(site[1] + '/tools/maps/tokyo.html').status == 404
        page.goto(site[1] + '/tools/' + suffix)
        page.locator('#cities-map .ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#cities-spot-tokyo-kanda')).to_be_visible()
        page.locator('#area-return').click()
        expect(page.locator('#point-name')).to_have_value('Centre')
        expect(page.locator('#radius')).to_have_value('0')
    finally:
        page.close()


@pytest.mark.parametrize('width', [390, 1280])
def test_world_shell_routes_and_shared_favorites(site, browser, width):
    context = browser.new_context(viewport={'width': width, 'height': 844}, is_mobile=width == 390, has_touch=width == 390)
    context.add_init_script("""if (location.protocol === 'http:' && !sessionStorage.getItem('seeded')) {
      localStorage.setItem('ui-world:cities-map', JSON.stringify({fav:['#cities-spot-tokyo-kanda']}));
      sessionStorage.setItem('seeded','1');
    }""")
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    path = site[1] + '/tools/'                                            # 🧰 the world: a panel of the one screen
    space = page.locator('[data-world-shell]')

    def choose(name):
        page.locator('[data-world-nav] summary').click()
        page.locator(f'[data-world-nav] [href="#{name}"]').click()
        expect(space).to_have_attribute('data-world-route', name)

    try:
        for name, label in [('paris', 'Fake Paris'), ('london', 'Reverse London')]:
            page.goto('about:blank')
            page.goto(path + '#' + name)
            expect(space).to_have_attribute('data-world-route', name)
            expect(page.locator('#world-space-name')).to_contain_text(label)
            expect(page.locator('#cities-map .ui-world-goto')).to_have_value(name)
            expect(page.locator(f'#cities-map [data-floor="{name}"].ui-floor')).to_be_visible()
        page.goto(path + '#school')
        page.evaluate('window.sameWorldDocument = true')
        school = page.locator('#school-map')
        school.locator('.ui-world-pick-grid [data-emoji]').first.click()
        school.locator('.ui-world-menu[data-menu="spots"] > summary').click()
        star = school.locator('.ui-world-spots:visible .ui-world-star:visible').first
        star.click()
        expect(star).to_have_attribute('aria-pressed', 'true')
        choose('london')
        assert page.evaluate('window.sameWorldDocument')
        expect(page.locator('#cities-map .ui-world-goto')).to_have_value('london')
        page.locator('#cities-map .ui-world-pick-grid [data-emoji]').first.click()
        choose('paris')
        expect(page.locator('#cities-map .ui-world-goto')).to_have_value('paris')
        page.go_back()
        expect(page.locator('#cities-map .ui-world-goto')).to_have_value('london')
        page.get_by_text('⭐ お気に入り', exact=True).click()
        expect(page.locator('#world-favorites a')).to_have_count(2)
        page.locator('#world-favorites a[href="#cities-spot-tokyo-kanda"]').click()
        expect(page.locator('#cities-spot-tokyo-kanda')).to_be_visible()
        page.locator('#cities-spot-tokyo-kanda .ui-sheet-close').click()
        expect(page).to_have_url(path + '#tokyo')
        page.reload()
        page.get_by_text('⭐ お気に入り', exact=True).click()
        expect(page.locator('#world-favorites a')).to_have_count(2)
        page.get_by_text('🧰 道具', exact=True).click()
        expect(page.locator('#world-switcher a[href="#maps"]')).to_be_visible()   # 🧰 the map: a panel of the same screen
        choose('camera')
        expect(page.locator('#demo-shots')).to_be_visible()
        choose('world')
        page.locator('#overworld-map .ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#overworld-map .ui-rpg-hud')).to_be_visible()
        page.locator('#overworld-map [data-rpg-explore]').click()
        expect(page.locator('#overworld-map .ui-rpg-battle')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth - document.documentElement.clientWidth') == 0
        assert not errors, errors
    finally:
        context.close()



def test_the_world_is_one_document_entered_by_fragment_with_queries_and_spots(site, browser):
    page = browser.new_page()
    base = site[1] + '/tools/'
    try:
        for old in ('demos/school.html', 'demos/cities.html', 'demos/world-shots.html', 'demos/world.html'):   # 🌍 no pages of its own: the scenes are #…
            assert page.goto(base + old).status == 404
        query = '?lat=35.68135&lon=139.7665&name=Centre&radius_m=0#cities-spot-tokyo-kanda'
        page.goto(base + query)
        expect(page).to_have_url(base + query)
        expect(page.locator('[data-world-shell]')).to_have_attribute('data-world-route', 'tokyo')
    finally:
        page.close()


def test_adventure_transfer_on_unified_world(site, browser, record_property):
    import pysaiyanweboo as ui

    def enter(page):
        page.goto(site[1] + '/tools/#world')
        world = page.locator('#overworld-map')
        world.locator('[data-emoji="🧙"]').click()
        return world

    def journal(world):
        world.locator('[data-rpg-journal-btn]').click()
        world.get_by_role('button', name='💾 セーブ').click()
        return world.get_by_role('textbox', name='冒険データ')

    source = browser.new_page()
    try:
        world = enter(source)
        for item in ('meadow-drop-herb', 'meadow-drop-mana', 'meadow-chest-sword'):
            world.locator('[data-menu="spots"] summary').click()
            world.locator(f'.ui-world-spots a[href="#overworld-spot-{item}"]').click()
            world.locator(f'[data-rpg-spot="{item}"]').click()
            world.get_by_role('button', name='やったね！').click()
        gear = world.locator('[data-rpg-gear]').inner_text()
        box = journal(world)
        world.get_by_text('セーブ文字列を作る', exact=True).click()
        normal = box.input_value()
        saved = ui.save_state(normal)
        assert saved['data']['exp'] > 0
        assert any(k.startswith('completedQuests:') for k in saved['data'])
        world.get_by_text('復活の呪文を作る', exact=True).click()
        expect(world.get_by_role('status').filter(has_text='空白・改行')).to_be_visible()
        spell = box.input_value()
        kana = len(''.join(spell.split()))
        record_property('save_characters', len(normal))
        record_property('spell_kana', kana)
        assert kana < len(normal)
    finally:
        source.close()

    for token in (normal, spell):
        recipient = browser.new_page()  # isolated context with no source storage
        try:
            world = enter(recipient)
            box = journal(world)
            for value in (token, token):  # importing twice cannot re-award loot or quests
                box.fill(value)
                world.get_by_role('button', name='読み込む').click()
                expect(world.get_by_text('冒険データを復元しました')).to_be_visible()
            expect(world.locator('[data-rpg-gear]')).to_have_text(gear)
            bag = world.locator('.ui-world-bag')
            assert 'はじまりの剣' in bag.text_content() and 'やくそう' in bag.text_content()
            assert len(recipient.evaluate('JSON.parse(localStorage["ui-world:overworld-map"]).bag')) == 3
            for bad in (token[:-2], ui.save_text({**saved, 'version': 99}),
                        ui.save_text({**saved, 'world': 'school'}),
                        ui.save_text({**saved, 'data': {**saved['data'], 'hp': -1}})):
                box.fill(bad)
                world.get_by_role('button', name='読み込む').click()
                expect(world.get_by_text('読み込めません', exact=False)).to_be_visible()
                world.get_by_text('セーブ文字列を作る', exact=True).click()
                assert ui.save_state(box.input_value()) == saved
            world.get_by_role('button', name='🧙 ステータス').click()
            world.get_by_role('button', name='やくそう', exact=False).click()
            assert 'やくそう' not in bag.text_content()
            assert 'はじまりの剣' in bag.text_content()
        finally:
            recipient.close()


def test_village_items_work_in_cities_and_on_hero(site, browser):
    import pysaiyanweboo as ui

    page = browser.new_page(reduced_motion='reduce')
    try:
        page.goto(site[1] + '/tools/#world')
        village = page.locator('#overworld-map')
        village.locator('[data-emoji="🧙"]').click()
        for item in ('meadow-drop-mana', 'meadow-hirugaoka'):
            village.locator('[data-menu="spots"] summary').click()
            village.locator(f'.ui-world-spots a[href="#overworld-spot-{item}"]').click()
            village.locator(f'[data-rpg-spot="{item}"]').click()
            village.get_by_role('button', name='やったね！').click()
        village.locator('[data-rpg-journal-btn]').click()
        tab = village.get_by_role('button', name='💾 セーブ')
        tab.click()
        box = village.get_by_role('textbox', name='冒険データ')
        export = village.get_by_text('セーブ文字列を作る', exact=True)
        export.click()
        original = ui.save_state(box.input_value())
        original['data']['mp'] = 0
        token = ui.save_text(original)

        def load(value):
            box.fill(value)
            village.get_by_role('button', name='読み込む').click()
            expect(village.get_by_text('冒険データを復元しました')).to_be_visible()

        load(token)
        village.get_by_role('button', name='🧙 ステータス').click()
        for label in ('癒しの水', 'サツマイモ'):
            village.get_by_role('button', name=label, exact=False).click()
        tab.click()
        export.click()
        used = ui.save_state(box.input_value())['data']
        assert (used['mp'], used['exp']) == (10, original['data']['exp'] + 20)
        load(token)
        village.locator('.ui-rpg-close').click()
        cities = page.locator('#cities-map')

        def travel(route):
            page.evaluate('(route) => location.hash = route', route)
            expect(page.locator('[data-world-shell]')).to_have_attribute('data-world-route', route)

        travel('london')
        cities.locator('.ui-world-pick-grid [data-emoji]').first.click()
        feed = cities.get_by_role('button', name='🍠 ドラゴンにあげる')
        feed.click()
        expect(cities.locator('output').filter(has_text='看板のドラゴン')).to_be_visible()
        sign = cities.locator('.ui-spot[href="#cities-spot-london-nogard"]')
        for _ in range(2):
            sign.evaluate('e => e.click()')
        feed.click()
        expect(cities.locator('output').filter(has_text='累計 20')).to_be_visible()
        expect(sign).to_have_attribute('data-reaction', '😋')
        travel('paris')
        water = cities.get_by_role('button', name='💧 目の前の火を消す')
        water.click()
        expect(cities.locator('output').filter(has_text='目の前に火がありません')).to_be_visible()
        floor = cities.locator('.ui-floor[data-floor="paris"]')
        fires = floor.locator('[data-kind="fire"]:not([hidden])')
        count = fires.count()
        # Walk to a reachable fire with two free tiles west, then face east from one tile away.
        floor.evaluate("""f=>{
          const t=+f.dataset.tile,rows=f.dataset.blocked.split(',');
          const fire=[...f.querySelectorAll('[data-kind="fire"]')].find(n=>{
            const x=parseInt(n.style.left)/t,y=parseInt(n.style.top)/t;
            return rows[y][x-1]==='0' && rows[y][x-2]==='0';
          });
          const form=f.closest('[data-ui-world]').querySelector('.ui-world-walk');
          form.elements.x.value=parseInt(fire.style.left)-1.5*t;
          form.elements.y.value=parseInt(fire.style.top)+0.5*t;
          form.requestSubmit();
        }""")
        cities.locator('[data-step="1,0"]').evaluate('b=>b.click()')
        water.click()
        expect(fires).to_have_count(count - 1)
        travel('world')
        village.locator('[data-rpg-journal-btn]').click()
        tab.click()
        export.click()
        progress = ui.save_state(box.input_value())
        assert progress['version'] == 2 and progress['data']['dragonExp'] == 20
        assert 'spot:meadow-hirugaoka' not in progress['data'] and 'spot:meadow-drop-mana' not in progress['data']
        village.get_by_text('復活の呪文を作る', exact=True).click()
        expect(village.get_by_text('空白・改行を含めてコピーできます')).to_be_visible()
        spell = box.input_value()
        load(token)
        expect(fires).to_have_count(count)
        load(spell)
        expect(fires).to_have_count(count - 1)
        export.click()
        assert ui.save_state(box.input_value()) == progress
    finally:
        page.close()


def test_london_dragon_care_and_colors(site, browser):
    import pysaiyanweboo as ui

    page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
    try:
        page.goto(site[1] + '/tools/#london')
        cities = page.locator('#cities-map')
        cities.locator('.ui-world-pick-grid [data-emoji]').first.tap()
        sign = cities.locator('.ui-spot[href="#cities-spot-london-nogard"]')
        care = cities.locator('.dragon-care')
        expect(care).to_be_hidden()
        for _ in range(2):
            sign.evaluate('e=>e.click()')
        summon = page.get_by_role('button', name='📜 竜の巻物')
        expect(summon).to_be_hidden()
        pet = care.get_by_role('button', name='ドラゴンをなでる')
        expect(care.locator('img')).to_have_js_property('naturalWidth', 20)
        expect(care.locator('img')).to_have_js_property('naturalHeight', 15)
        with page.expect_download() as download:
            care.get_by_text('原画JSONを保存').tap()
        from pathlib import Path
        assert json.loads(Path(download.value.path()).read_text()) == json.loads(
            (ROOT / 'scripts/london-dragon.json').read_text())
        for reaction in ('💕', '🎵', '💤'):
            pet.tap()
            expect(sign).to_have_attribute('data-reaction', reaction)
            expect(care.locator('output')).to_contain_text(reaction)
        hue = care.get_by_label('ドラゴンの体色')
        fill = care.get_by_label('背景の塗りつぶし')
        hue.select_option('2')
        fill.fill('#000000')
        expect(care.locator('.dragon-portrait')).to_have_css('filter', 'hue-rotate(180deg)')
        expect(pet).to_have_css('background-color', 'rgb(0, 0, 0)')
        page.evaluate("location.hash='world'")
        village = page.locator('#overworld-map')
        village.locator('[data-emoji="🧙"]').tap()
        village.locator('[data-rpg-journal-btn]').tap()
        village.get_by_role('button', name='💾 セーブ').tap()
        box = village.get_by_role('textbox', name='冒険データ')
        export = village.get_by_text('セーブ文字列を作る', exact=True)
        export.tap()
        save = ui.save_state(box.input_value())
        assert save['data']['dragonScroll'] == 1
        assert (save['version'], save['data']['dragonHue'], save['data']['dragonFill']) == (4, 2, 1)
        village.get_by_text('復活の呪文を作る', exact=True).tap()
        expect(village.get_by_text('空白・改行を含めてコピーできます')).to_be_visible()
        spell = box.input_value()
        old = {k: v for k, v in save['data'].items() if k not in ('dragonHue', 'dragonFill', 'dragonScroll')}
        box.fill(ui.save_text({**save, 'version': 1, 'data': old}))
        load = village.get_by_role('button', name='読み込む')
        load.tap()
        expect(hue).to_have_value('0')
        expect(summon).to_be_hidden()
        box.fill(spell)
        load.tap()
        expect(hue).to_have_value('2')
        expect(fill).to_have_value('#000000')
        village.locator('.ui-rpg-close').tap()
        page.evaluate("location.hash='london'")
        page.evaluate("location.hash='school'")
        summon.tap()
        visiting = page.get_by_role('dialog', name='竜の巻物')
        visiting.get_by_role('button', name='ドラゴンをなでる').tap()
        expect(visiting.get_by_label('ドラゴンの体色')).to_have_value('2')
        visiting.get_by_role('button', name='🍠 サツマイモを渡す').tap()
        expect(visiting).to_contain_text('サツマイモがありません')
        visiting.get_by_role('button', name='閉じる').tap()
        page.evaluate("location.hash='london'")
        # Reopen the sheet if the scene switch closed it.
        cities.locator('.ui-world-spots a[href="#cities-spot-london-nogard"]').evaluate('a=>a.click()')
        care.get_by_role('button', name='元の色に戻す').tap()
        expect(hue).to_have_value('0')
        expect(fill).to_have_value('#ffffff')
    finally:
        page.close()


def test_shop_rumor_and_optional_world_dialogue(site, browser):
    page = browser.new_page()
    loads = []
    try:
        def engine(route):
            loads.append(route.request.url)
            route.fulfill(content_type='text/javascript', headers={'Access-Control-Allow-Origin': '*'}, body="""
              export class Wllama {
                async loadModelFromUrl(){}
                async createChatCompletion({messages,onData}){
                  window.dialogueMessages=messages;
                  onData({choices:[{delta:{content:'木の看板の陰をのぞいてごらん。'}}]});
                }
              }
            """)
        page.route('**/wllama@*/esm/index.js', engine)
        page.goto(site[1] + '/tools/#world')
        village = page.locator('#overworld-map')
        village.locator('[data-emoji="🧙"]').click()
        village.locator('[data-menu="spots"] summary').click()
        village.locator('.ui-world-spots a[href="#overworld-spot-meadow-npc-smith"]').click()
        village.locator('[data-rpg-spot="meadow-npc-smith"]').click()
        card = village.get_by_role('dialog', name='道具屋の店主')
        card.get_by_role('button', name='サツマイモは誰にあげるといい？').click()
        rumor = card.locator('.ui-rpg-text').inner_text().split('] ', 1)[1]
        assert all(word in rumor for word in ('ドラゴン', '好き', 'リバースロンドン', '木の看板'))
        assert '回' not in rumor and '経験値' not in rumor
        card.get_by_text('もっと話す').click()
        assert loads == []
        card.get_by_label('話しかける').fill('おいもは誰が好き？')
        card.get_by_role('button', name='送る').click()
        expect(card.get_by_text('木の看板の陰をのぞいてごらん。')).to_be_visible()
        messages = page.evaluate('window.dialogueMessages')
        assert rumor in messages[0]['content'] and '道具屋の店主' in messages[0]['content']
        assert messages[1]['content'] == 'おいもは誰が好き？'
        evidence = card.locator('form details')
        evidence.locator('summary').click()
        expect(evidence).to_contain_text('ドラゴン → 好物 → サツマイモ')
        expect(evidence).to_contain_text('ドラゴン → 現れる → 木の看板')
        assert '癒しの水' not in evidence.inner_text()
        for question in ('復活のじゅもんは？', '宇宙船の燃料は？'):
            card.get_by_label('話しかける').fill(question)
            card.get_by_role('button', name='送る').click()
            page.wait_for_function('q=>window.dialogueMessages[1].content===q', arg=question)
            if 'じゅもん' in question:
                assert {link.split('/')[4] for link in evidence.locator('a').evaluate_all('a=>a.map(n=>n.href)')} == {
                    'myon-bioinformatics.github.io', 'PySaiyanWeBoo'}
            else:
                expect(evidence).to_be_hidden()
                system = page.evaluate('window.dialogueMessages[0].content')
                assert 'この質問に対応する関係は台帳にない' in system and rumor not in system
        # The unrelated turn still occupies slot 1, so the spell is two exchanges back.
        for question, expected in [('２回前の話をもう一度', '復活の呪文'), ('3回前の話は？', '復活の呪文')]:
            card.get_by_label('話しかける').fill(question)
            card.get_by_role('button', name='送る').click()
            page.wait_for_function('q=>window.dialogueMessages[1].content===q', arg=question)
            assert expected in page.evaluate('window.dialogueMessages[0].content')
        card.get_by_label('話しかける').fill('探索の巻物の効果は？')
        card.get_by_role('button', name='送る').click()
        expect(evidence).to_contain_text('探索の巻物 → 発見対象 → 未取得のどうぐ')
        expect(evidence).to_contain_text('探索の巻物 → 発見対象 → やくそう')
        assert '竜の巻物' not in evidence.inner_text()
        question = '探索の巻物を戦闘中に使うと？'
        card.get_by_label('話しかける').fill(question)
        card.get_by_role('button', name='送る').click()
        page.wait_for_function('q=>window.dialogueMessages[1].content===q', arg=question)
        grounding = page.evaluate('window.dialogueMessages[0].content')
        assert '30%' in grounding and '1ターン' in grounding and '未取得のどうぐ' not in grounding
        card.locator('.ui-rpg-close').click()
        village.locator('[data-rpg-journal-btn]').click()
        village.get_by_role('button', name='💾 セーブ').click()
        village.get_by_text('セーブ文字列を作る', exact=True).click()
        import pysaiyanweboo as ui
        saved = ui.save_state(village.get_by_label('冒険データ').input_value())
        assert saved['version'] == 4
        assert [saved['data'][f'topic{i}'] for i in (1, 2, 3)] == [13, 13, 11]
        assert len(loads) == 1
    finally:
        page.close()


def test_reusable_scrolls_in_field_and_battle(site, browser):
    import re
    import pysaiyanweboo as ui

    page = browser.new_page(reduced_motion='reduce')
    try:
        page.goto(site[1] + '/tools/#world')
        page.get_by_text('📖 攻略ガイド', exact=True).click()
        guide = page.get_by_role('article', name='探索の巻物をいつ使う？')
        expect(guide).to_contain_text('6マス以内')
        expect(guide).to_contain_text('1ターン使い、30%')
        expect(guide).to_contain_text('次が強攻撃なら、まずぼうぎょ')
        expect(guide.get_by_role('link', name='道具の定義（GitHub）')).to_be_visible()
        page.get_by_text('📖 攻略ガイド', exact=True).click()
        world = page.locator('#overworld-map')
        world.locator('[data-emoji="🧙"]').click()
        world.locator('[data-rpg-journal-btn]').click()
        world.get_by_role('button', name='💾 セーブ').click()
        world.get_by_text('セーブ文字列を作る', exact=True).click()
        box = world.get_by_label('冒険データ')
        saved = ui.save_state(box.input_value())
        # A pre-change save collected and spent the exploration scroll.
        saved.update(version=4)
        saved['data'].update({'looted:meadow-drop-scroll': 1, 'dragonScroll': 1, 'dragonExp': 20, 'seed': 1})
        box.fill(ui.save_text(saved))
        world.get_by_role('button', name='読み込む').click()
        expect(world.get_by_text('冒険データを復元しました')).to_be_visible()
        world.locator('.ui-rpg-close').click()
        menu = page.locator('#world-switcher')
        herb = world.locator('.ui-spot[href="#overworld-spot-meadow-drop-herb"]')
        for _ in range(2):
            menu.get_by_role('button', name='📜 探索の巻物').click()
            expect(herb).to_have_attribute('data-scroll-found', '')
        assert world.locator('.ui-spot[href="#overworld-spot-meadow-drop-scroll"][data-scroll-found]').count() == 0
        world.locator('[data-rpg-explore]').click()
        battle = world.locator('.ui-rpg-battle')
        hp = battle.locator('.ui-rpg-foe-meta').filter(has_text='HP').inner_text()
        log = battle.locator('.ui-rpg-log')
        battle.get_by_role('button', name='💡 ヒント').click()
        expect(log).to_contain_text('探索の巻物で探せます（30%）')
        expect(log).to_contain_text('弱点')
        for result in ('1個拾った', '見つからなかった'):
            battle.get_by_role('button', name='探索の巻物', exact=False).click()
            expect(log).to_contain_text(result)
            assert battle.locator('.ui-rpg-foe-meta').filter(has_text='HP').inner_text() == hp
            battle.get_by_role('button', name='💡 ヒント').click()
            assert '探索の巻物で探せます' not in log.text_content().splitlines()[-1]
        expect(log).to_contain_text('次は強攻撃')
        battle.get_by_role('button', name='📜 竜の巻物').click()
        expect(battle.locator('.ui-rpg-log')).to_contain_text('ドラゴンの加勢')
        assert battle.locator('.ui-rpg-foe-meta').filter(has_text='HP').inner_text() != hp
        battle.locator('.ui-rpg-close').click()
        menu.get_by_role('button', name='📜 竜の巻物').click()
        expect(page.get_by_role('dialog', name='竜の巻物')).to_be_visible()
        page.get_by_role('dialog', name='竜の巻物').get_by_role('button', name='閉じる').click()
        world.locator('[data-rpg-journal-btn]').click()
        world.get_by_role('button', name='💾 セーブ').click()
        world.get_by_text('セーブ文字列を作る', exact=True).click()
        data = ui.save_state(box.input_value())
        assert data['version'] == 5 and data['data']['found:herb'] == 1
        world.get_by_text('復活の呪文を作る', exact=True).click()
        expect(box).to_have_value(re.compile('[ぁ-ヶ]'))
        world.get_by_role('button', name='読み込む').click()
        expect(world.get_by_text('冒険データを復元しました')).to_be_visible()
    finally:
        page.close()
