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
        page.goto(site[1] + '/tools/maps/')
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
        assert urlsplit(page.url).path == '/tools/demos/cities.html'
        assert page.locator('.map-point-link').count() == 21
        assert set(page.locator('.ui-floor').evaluate_all('(floors) => floors.map(f => f.dataset.floor)')) >= {'tokyo', 'london', 'paris'}
        # PSWB asks for the walking avatar on entry; choose it through the normal UI.
        expect(page.locator('.ui-world-pick')).to_be_visible()
        page.locator('.ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#tokyo-range')).to_contain_text('半径 350 m')
        sheet = page.locator('#cities-spot-tokyo-kanda')
        expect(sheet).to_be_visible()
        shot('Parallel Tokyo: Kanda sheet')
        sheet.get_by_role('link', name='この地点の地図URL・ピン留め').click()
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
        page.goto(site[1] + '/tools/maps/')
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
        page.goto(site[1] + '/tools/maps/?lat=0&lon=0&name=%3Cimg%20src%3Dx%20onerror%3Dalert(1)%3E')
        expect(page.locator('#latitude')).to_have_value('0')
        page.locator('#pin').click()
        expect(page.locator('#pin-storage')).to_contain_text('保存できません')
        assert page.locator('#pins img').count() == 0
        page.locator('#share').click()
        expect(page.locator('#map-status')).to_contain_text('選択したテキスト')
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
        page.goto(site[1] + '/tools/maps/')
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
        page.goto(site[1] + f'/tools/maps/?lat={lat}&lon={lon}&radius_m={radius}')
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
        page.goto(site[1] + '/tools/maps/?lat=35.68135&lon=139.7665&name=中心&radius_m=350')
        expect(page.locator('#tokyo-link')).to_be_hidden()  # arbitrary centre, rather than an exact city coordinate
        expect(page.locator('#nearby-list')).to_contain_text('丸の内北口')
        expect(page.locator('#nearby-list')).to_contain_text('八重洲中央口')
        expect(page.locator('#nearby-list')).not_to_contain_text('大手町')
        page.locator('#nearby-list').get_by_role('link', name='丸の内中央口', exact=False).click()
        page.locator('.ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#cities-spot-tokyo-marunouchi-c')).to_be_visible()
        page.locator('#area-return').click()
        expect(page.locator('#latitude')).to_have_value('35.681350')
        expect(page.locator('#point-name')).to_have_value('中心')
        expect(page.locator('#radius')).to_have_value('350')
        page.locator('#nearby-list').get_by_role('link', name='丸の内中央口', exact=False).click()
        page.locator('.ui-world-pick-grid [data-emoji]').first.click()
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
        page.goto(site[1] + '/tools/demos/cities.html' + suffix)
        page.locator('.ui-world-pick-grid [data-emoji]').first.click()
        expect(page.locator('#cities-spot-tokyo-kanda')).to_be_visible()
        page.locator('#area-return').click()
        expect(page.locator('#point-name')).to_have_value('Centre')
        expect(page.locator('#radius')).to_have_value('0')
    finally:
        page.close()
