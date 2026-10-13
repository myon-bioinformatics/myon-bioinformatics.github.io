"""Thin consumer adapter around pinned web-ui; report ownership stays in lab."""
from pathlib import Path
import importlib.util
import json
import re
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('publication_web_ui',ROOT/'tools/vendor/web-ui/web_ui.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
CLASS_MAP={'term-page':'ui-page','term-title':'ui-title','term-muted':'ui-muted',
           'term-tag':'ui-tag','term-panel':'ui-panel','term-card':'ui-card',
           'term-output':'ui-output','term-input':'ui-input','term-button':'ui-button'}
NAVIGATION_BINDING=b"globalThis.webUiNavigation.bindViews(globalThis,{viewAttribute:'data-pages-view',navAttribute:'data-pages-nav',queryAliases:{wiki:'wiki'}});\n"
def presentation_identity():
    lock=json.loads((ROOT/'tools/html-import/vendor.lock.json').read_text())
    return {'owner':'myon-bioinformatics/web-ui','theme':'modern',
            'assets':[x for x in lock['sources'] if x['repository'].endswith('/web-ui')]}
def apply_shared_ui(page):
    page=ui.adopt_document(page,asset_base='../vendor/web-ui',class_aliases=CLASS_MAP,remove_stylesheets=('terminal.css',))
    page=re.sub(r'<script\s+src="pages-hash\.js(?:\?[^"]*)?"\s*></script>','',page)
    if 'src="../vendor/web-ui/js/navigation.js"' not in page:
        page=page.replace('</head>','<script src="../vendor/web-ui/js/navigation.js"></script></head>',1)
    if 'src="shared-navigation.mjs"' not in page:
        page=page.replace('</body>','<script type="module" src="shared-navigation.mjs"></script></body>',1)
    return page.replace('Styling: single lab-owned <code>terminal.css</code> (no external stylesheet chain).',
                        'Styling: pinned local <code>web-ui</code> modern theme; imported report and lab tool behavior retain their source identity.')
def apply_shared_navigation(payload):
    payload['index.html']=apply_shared_ui(payload['index.html'].decode('utf-8')).encode('utf-8')
    # Provider-specific title/URL builders remain in lab. Only the generic new-tab
    # validation/policy is delegated to the shared primitive.
    pixiv=payload['pages-pixiv.js'].decode('utf-8').replace('win.open(url, "_blank", "noopener");','win.webUiNavigation.openExternalURL(url, win);')
    payload['pages-pixiv.js']=pixiv.encode('utf-8')
    payload['shared-navigation.mjs']=NAVIGATION_BINDING
