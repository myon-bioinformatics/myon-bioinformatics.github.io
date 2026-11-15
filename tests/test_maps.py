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
        page.locator('#tokyo-point').select_option('tokyo-kanda')
        expect(page.locator('#point-name')).to_have_value('神田')
        point = '35.691800,139.770900'
        google = page.locator('#google-link').get_attribute('href')
        apple = page.locator('#apple-link').get_attribute('href')
        assert parse_qs(urlsplit(google).query) == {'api': ['1'], 'query': [point]}
        assert parse_qs(urlsplit(apple).query)['ll'] == [point]
        page.locator('#map-result').scroll_into_view_if_needed()
        shot('Kanda: Google Maps + Apple Maps links')
        page.locator('#pin').click()
        expect(page.locator('#pins')).to_contain_text('神田')
        page.locator('#pin').click()  # same coordinate updates rather than duplicating
        assert page.locator('#pins li').count() == 1
        page.locator('#copy-share').click()
        expect(page.locator('#map-status')).to_have_text('コピーしました。')
        shared = page.evaluate('navigator.clipboard.readText()')
        assert parse_qs(urlsplit(shared).query)['lat'] == ['35.691800']
        page.reload()
        expect(page.locator('#pins')).to_contain_text('神田')
        page.locator('#pins button').first.click()
        expect(page.locator('#point-name')).to_have_value('神田')
        page.locator('#pins').scroll_into_view_if_needed()
        shot('Pin retained after reload; duplicate pin updates')

        # A recipient's browser opens the coordinate, without silently saving a pin.
        other = browser.new_context()
        try:
            recipient = other.new_page()
            recipient.goto(shared)
            expect(recipient.locator('#latitude')).to_have_value('35.691800')
            expect(recipient.locator('#point-name')).to_have_value('神田')
            expect(recipient.locator('#pins')).to_have_text('ピンはまだありません。')
        finally:
            other.close()

        page.locator('#tokyo-link').click()
        # PSWB asks for the walking avatar on entry; choose it through the normal UI.
        expect(page.locator('.ui-world-pick')).to_be_visible()
        page.locator('.ui-world-pick-grid [data-emoji]').first.click()
        sheet = page.locator('#cities-spot-tokyo-kanda')
        expect(sheet).to_be_visible()
        shot('Parallel Tokyo: Kanda sheet')
        sheet.get_by_role('link', name='この地点の地図URL・ピン留め').click()
        expect(page.locator('#latitude')).to_have_value('35.691800')
        expect(page.locator('#tokyo-point')).to_have_value('tokyo-kanda')
        page.locator('#map-result').scroll_into_view_if_needed()
        shot('Tokyo sheet returns to the same real coordinates')
        # Native share is verified at its browser API boundary; no external recipient is contacted.
        page.evaluate('Object.defineProperty(navigator,"share",{configurable:true,value:async data=>{window.shared=data}})')
        page.locator('#share').click()
        expect(page.locator('#map-status')).to_have_text('共有しました。')
        payload = page.evaluate('window.shared')
        assert google in payload['text'] and apple in payload['text']
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
    finally:
        page.close()
