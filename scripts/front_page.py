"""The portfolio's front page (index.html), built in Python: no index.html, index.js, style.css or renderer.css in the repository.

``document()`` returns the one page that ``scripts/project_pages.py`` writes at build time. Everything a visitor reads is
made here from ``profile.json``, ``api/repos.json`` and ``projects.json``: the page shell, the 🧰 Tools cards
(``PORTAL``), and the profile and projects in each notation (cards, XML-like, JSON, Markdown). The colour themes are
PySaiyanWeBoo's palettes, picked in the site chrome's ⚙️ 🎨, beside 🧾 the display mode (``SETTINGS``). The page script only switches between what Python built, filters projects and fills the AI
highlight slots with what the public GitHub API returns in the browser.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import quote

# Service endpoints come from the same catalog for both tool cards and the footer.
_services = json.loads((Path(__file__).resolve().parents[1] / 'services.json').read_text(encoding='utf-8'))['services']
_site_url = _services['portfolio']['pages']['url']


def _service_url(project: str, endpoint: str, *, relative: bool = False) -> str:
    url = _services['projects'][project][endpoint]['url']
    return './' + url.removeprefix(_site_url) if relative and url.startswith(_site_url) else url


# 🧰 Tools: one card each, named for what it does — practical tools only. ``from`` names the repositories a card is built from (🧩, plain
# text; 🚀 Projects links them): the card is a tool made of their parts, not those projects. ``points`` are trusted HTML (they carry <code>);
# everything else is escaped.
PORTAL = [{'title': 'HTML文書取込', 'text': 'HTML貼り付け・ファイル選択から、端末内で本文・見出し・リンクを抽出。', 'id': 'html-import', 'words': {'HTML文書取込': ['HTML import', 'Import HTML', 'Importar HTML', 'Importar HTML', 'استيراد HTML', 'HTML 导入', 'Импорт HTML', 'Impor HTML', 'HTML-Import', 'Kuingiza HTML']}, 'links': [('Open HTML Import →', './tools/#html-import')]},
 {'title': '🗃️ 形式変換・検証',
  'id': 'format-lab', 'words': {'形式変換・検証': ['Format conversion & checks', 'Conversion et vérification de formats', 'Conversión y verificación de formatos', 'Conversão e verificação de formatos', 'تحويل الصيغ والتحقق منها', '格式转换与校验', 'Преобразование и проверка форматов', 'Konversi dan pemeriksaan format', 'Formatumwandlung und Prüfung', 'Ubadilishaji na ukaguzi wa miundo'], 'Format Lab を開く': ['Open Format Lab', 'Ouvrir Format Lab', 'Abrir Format Lab', 'Abrir o Format Lab', 'افتح Format Lab', '打开 Format Lab', 'Открыть Format Lab', 'Buka Format Lab', 'Format Lab öffnen', 'Fungua Format Lab']},
  'text': 'ファイルや貼り付けた原文を静的検査し、Base64の復元差分と検証記録を確認。CaChereCyCleのJSONLは資産のSHA-256も照合。',
  'from': ('myon-bioinformatics', 'PySaiyanWeBoo'),
  'links': [('Format Lab を開く →', './tools/#format-lab')]},
 {'title': '📍地図URL・座標ピン留め',
  'text': '緯度・経度からApple MapsとGoogle MapsのURLを作成。地点のピン留め・共有と、パラレル東京の対応地点へ。',
  'id': 'maps', 'words': {'地図URL・座標ピン留め': ['Map URLs & coordinate pins', 'URL de carte et épingles de coordonnées', 'URL de mapa y chinchetas de coordenadas', 'URL de mapa e alfinetes de coordenadas', 'روابط الخرائط ودبابيس الإحداثيات', '地图 URL 与坐标图钉', 'URL карт и метки координат', 'URL peta dan penanda koordinat', 'Karten-URLs und Koordinaten-Pins', 'URL za ramani na pini za kuratibu'], '地図URLを作成': ['Make a map URL', 'Créer une URL de carte', 'Crear una URL de mapa', 'Criar uma URL de mapa', 'أنشئ رابط خريطة', '生成地图 URL', 'Создать URL карты', 'Buat URL peta', 'Karten-URL erstellen', 'Tengeneza URL ya ramani'], 'パラレル東京': ['Parallel Tokyo', 'Tokyo parallèle', 'Tokio paralelo', 'Tóquio paralela', 'طوكيو الموازية', '平行东京', 'Параллельный Токио', 'Tokyo Paralel', 'Paralleles Tokio', 'Tokyo sambamba']},
  'links': [('地図URLを作成 →', './tools/#maps'), ('パラレル東京 →', './tools/#tokyo')]},
 {'title': '🖼️ スライド・画像工房',
  'text': 'ブラウザでスライドを作成し、文字・図形・矢印を編集可能なPPTXへ出力。Image Studio はレイヤー、数値行列のヒートマップ、作業履歴、クリップボード棚、PNG Base64 の受け渡しに対応し、Browser Tools '
          'ではドット絵・比較用の一枚・容量確認ができます。Markdown→PPTX変換と既存PPTXの属性編集はローカルCLIの試作実装です。',
  'id': 'studios', 'words': {'スライド・画像工房': ['Slide & image studio', 'Atelier diapos et images', 'Taller de diapositivas e imágenes', 'Estúdio de slides e imagens', 'استوديو الشرائح والصور', '幻灯片与图像工坊', 'Студия слайдов и изображений', 'Studio slide dan gambar', 'Folien- und Bildwerkstatt', 'Studio ya slaidi na picha']},
  'from': ('Ironmate',),
  'links': [('Open Image Studio →', _service_url('Ironmate', 'pages')),
            ('Open Browser Tools →', _service_url('Ironmate', 'browserTools')),
            ('Open Slide Studio →', _service_url('Ironmate', 'slides'))]},
 {'title': '🌡️ ヒートマップ',
  'text': '数値行列か Plotly の heatmap を貼って描き、色の段階・値の表示を変えて SVG・PNG・シーン JSON に。'
          'シーンは Ironmate の Image Studio でレイヤーとして編集できます。',
  'id': 'heatmap', 'words': {'ヒートマップ': ['Heatmap', 'Carte de chaleur', 'Mapa de calor', 'Mapa de calor', 'خريطة حرارية', '热图', 'Тепловая карта', 'Peta panas', 'Heatmap', 'Ramani ya joto'], 'ヒートマップを描く': ['Draw a heatmap', 'Dessiner une carte de chaleur', 'Dibujar un mapa de calor', 'Desenhar um mapa de calor', 'ارسم خريطة حرارية', '绘制热图', 'Нарисовать тепловую карту', 'Gambar peta panas', 'Heatmap zeichnen', 'Chora ramani ya joto'], 'Image Studio で編集': ['Edit in Image Studio', 'Modifier dans Image Studio', 'Editar en Image Studio', 'Editar no Image Studio', 'حرّر في Image Studio', '在 Image Studio 中编辑', 'Редактировать в Image Studio', 'Edit di Image Studio', 'In Image Studio bearbeiten', 'Hariri katika Image Studio']},
  'from': ('DRAgoWing', 'Ironmate'),
  'links': [('ヒートマップを描く →', './tools/#heatmap'), ('Image Studio で編集 →', _service_url('Ironmate', 'pages', relative=True))]},
 {'title': '🔌 MCP 実験室',
  'text': 'AI が MCP で呼ぶ道具（Wikipedia 表示・Pixiv 原文抽出・ニコニコ検索・ポケモン）をブラウザで試し、ツール呼び出しの記録（JSONL）を集計。'
          '検証の結果は、ラボの Actions の写し。接続試験は、新旧の protocol・PKCE・Bearer・OAuth メタデータを端末の中で確かめる。',
  'id': 'mcp', 'words': {'MCP 実験室': ['MCP lab', 'Labo MCP', 'Laboratorio MCP', 'Laboratório MCP', 'مختبر MCP', 'MCP 实验室', 'Лаборатория MCP', 'Lab MCP', 'MCP-Labor', 'Maabara ya MCP'], 'MCP 接続試験': ['MCP connection test', 'Test de connexion MCP', 'Prueba de conexión MCP', 'Teste de conexão MCP', 'اختبار اتصال MCP', 'MCP 连接测试', 'Проверка подключения MCP', 'Uji koneksi MCP', 'MCP-Verbindungstest', 'Jaribio la muunganisho wa MCP']},
  'from': ('mcp-toolcall-lab',),
  'links': [('Open Tool Lab →', './tools/#mcp'),
            ('Open Execution Lab →', _service_url('mcp-toolcall-lab', 'execution')),
            ('MCP 接続試験 →', './tools/#protocol')]},
 {'title': '🧾 テスト結果',
  'text': 'JUnit の結果を貼るか開いて読み、前回と比べて新規・再発・解消を分ける。端末の中で完結し、結果はどこにも送らない。',
  'id': 'test-report', 'words': {'テスト結果': ['Test results', 'Résultats de tests', 'Resultados de pruebas', 'Resultados de testes', 'نتائج الاختبار', '测试结果', 'Результаты тестов', 'Hasil pengujian', 'Testergebnisse', 'Matokeo ya majaribio'], '結果を読む': ['Read the results', 'Lire les résultats', 'Leer los resultados', 'Ler os resultados', 'اقرأ النتائج', '读取结果', 'Прочитать результаты', 'Baca hasil', 'Ergebnisse lesen', 'Soma matokeo']},
  'from': ('PySaiyanWeBoo',),
  'links': [('結果を読む →', './tools/#test-report')]},
 {'title': '💬 横断チャット',
  'text': 'リポジトリ横断の道具をチャットで：Markdown の表示・表、ASCII アートと流れ図、会話の圧縮、MCP の道具呼び出しの確認、'
          '全リポジトリの JSON / JSONL（オントロジーの台帳も）の索引と中身。ページの中の Python（Pyodide）で、それぞれのリポジトリのコードがそのまま動く。',
  'id': 'chat', 'words': {'横断チャット': ['Cross-repo chat', 'Chat inter-dépôts', 'Chat entre repositorios', 'Chat entre repositórios', 'دردشة عبر المستودعات', '跨仓库聊天', 'Чат по всем репозиториям', 'Obrolan lintas repo', 'Repo-übergreifender Chat', 'Gumzo la hazina zote'], '話しかける': ['Talk to it', 'Lui parler', 'Hablarle', 'Falar com ele', 'تحدّث إليه', '和它聊聊', 'Поговорить', 'Ajak bicara', 'Ansprechen', 'Zungumza nayo']},
  'from': ('markdown', 'ascii_artist', 'cli_args', 'TalkCompress', 'mcp-toolcall-lab'),
  'links': [('💬 話しかける →', './tools/#chat')]},
 {'title': '🧭 統合運用',
  'text': 'リポジトリ横断の運用ダッシュボード：CI の失敗・競合・未解決レビューの優先確認、監査と依存、実行手順、記録と差分。',
  'id': 'operations', 'words': {'統合運用': ['Operations', 'Opérations', 'Operaciones', 'Operações', 'العمليات', '综合运维', 'Эксплуатация', 'Operasi', 'Betrieb', 'Uendeshaji']},
  'from': ('myon-bioinformatics',),
  'links': [('Open Dashboard →', 'https://myon-bioinformatics.github.io/myon-bioinformatics/')]},
 {'title': '🎞 GIF工房',
  'text': '手持ちの画像を並べて GIF に。端末の中で完結し、画像はどこにも送らず保存もしない（PySaiyanWeBoo の gif.js）。',
  'id': 'gif', 'words': {'GIF工房': ['GIF studio', 'Atelier GIF', 'Taller GIF', 'Oficina GIF', 'استوديو GIF', 'GIF 工坊', 'Студия GIF', 'Studio GIF', 'GIF-Werkstatt', 'Studio ya GIF'], 'GIF をつくる': ['Make a GIF', 'Créer un GIF', 'Crear un GIF', 'Criar um GIF', 'أنشئ GIF', '制作 GIF', 'Сделать GIF', 'Buat GIF', 'GIF erstellen', 'Tengeneza GIF']},
  'from': ('PySaiyanWeBoo',),
  'links': [('GIF をつくる →', './tools/#gif')]},
 {'title': '🌊 流れの実験室',
  'text': 'FFSS の全場面を 🌊 動く像（流れと遅れ）で、その記録から描ける DRAgoWing の全図を 📊 静止図（行き先の内訳）で。水回り・流しそうめん・お金・からだ・火力・ヒートポンプまで。',
  'id': 'flow', 'words': {'流れの実験室': ['Flow lab', 'Labo des flux', 'Laboratorio de flujos', 'Laboratório de fluxos', 'مختبر التدفق', '流动实验室', 'Лаборатория потоков', 'Lab aliran', 'Strömungslabor', 'Maabara ya mtiririko'], '実験室へ': ['To the lab', 'Vers le labo', 'Al laboratorio', 'Ao laboratório', 'إلى المختبر', '前往实验室', 'В лабораторию', 'Ke lab', 'Zum Labor', 'Kwenda maabara']},
  'from': ('FluidFullSpeedSimulation', 'DRAgoWing'),
  'links': [('実験室へ →', './tools/#flow')]},
 {'title': '🧠 リポジトリ地図',
  'text': 'どのリポジトリが、どのリポジトリのファイルを写して使っているか。各リポジトリの vendor.lock.json と Aoi の subtree から、公開のたびに描き直す。',
  'id': 'repo-map', 'words': {'リポジトリ地図': ['Repository map', 'Carte des dépôts', 'Mapa de repositorios', 'Mapa de repositórios', 'خريطة المستودعات', '仓库地图', 'Карта репозиториев', 'Peta repositori', 'Repository-Karte', 'Ramani ya hazina'], '地図へ': ['To the map', 'Vers la carte', 'Al mapa', 'Ao mapa', 'إلى الخريطة', '前往地图', 'К карте', 'Ke peta', 'Zur Karte', 'Kwenda ramani']},
  'links': [('地図へ →', './tools/#repo-map')]}]


# 🔗 The front page's own emoji in the shared header (scripts/project_pages.py ``add_site_chrome``): where else to find the author.
LINKS = {'🔗': {'label': 'リンク', 'label_en': 'Links', 'links': [
    {'label': '🐙 GitHub', 'href': 'https://github.com/myon-bioinformatics'}, {'label': '🔆 lit.link', 'href': 'https://lit.link/myon123'},
    {'label': '🌳 Linktree', 'href': 'https://linktr.ee/myon123'}, {'label': '🐦 X (Twitter)', 'href': 'https://twitter.com/myonitbusiness'}]}}


def portal_cards(samples=frozenset()) -> str:
    """The 🧰 Tools cards (each repository's own Pages are linked from its 🚀 Projects card). 🎥 A card whose moving sample this
    build recorded (``tools/<id>`` in ``samples``: media/pages/tools/<id>.gif) shows it, and the picture opens the card's first
    link, as a 🚀 Projects card's does. The picture is the way in: the links in words stay only where a card opens several pages
    of a kind (its relatives, side by side), or where no picture was recorded."""
    out = []
    for card in PORTAL:
        key = html.escape(card['id'], quote=True)
        parts = [f'<h3 id="{key}">' + html.escape(card['title'], quote=False) + '</h3>']
        shown = f'tools/{card["id"]}' in samples
        if shown:
            parts.append(f'<a class="project-sample" href="{html.escape(card["links"][0][1], quote=True)}"><img src="./media/pages/tools/{key}.gif" '
                         f'alt="🎥 {html.escape(card["title"], quote=True)}" loading="lazy" width="240" height="456"></a>')
        parts.append('<p>' + html.escape(card['text'], quote=False) + '</p>')
        if 'from' in card:
            parts.append('<p class="portal-from">🧩 出どころ: ' + ' · '.join(html.escape(name, quote=False) for name in card['from']) + '</p>')
        if 'points' in card:
            parts.append('<ul class="portal-points">' + ''.join(f'<li>{point}</li>' for point in card['points']) + '</ul>')
        if not shown or len(card['links']) > 1:
            parts += [f'<a href="{html.escape(href, quote=True)}">{html.escape(label, quote=False)}</a>' for label, href in card['links']]
        out.append('        <article class="card portal-card">' + ''.join(parts) + '</article>\n')
    return '      <div class="portal-grid">\n' + ''.join(out)


# ── data ────────────────────────────────────────────────────────────────────────────────────────────────────────────

# 🤖 Shown until (and unless) the public GitHub API answers in the browser; they claim no star counts.
AI_FALLBACK = [
    {'name': 'ollama/ollama', 'desc': 'Get up and running with Llama 3.3, DeepSeek-R1, Gemma 2, and other large language models.',
     'url': 'https://github.com/ollama/ollama', 'stars': None, 'language': 'Go'},
    {'name': 'vllm-project/vllm', 'desc': 'A high-throughput and memory-efficient inference and serving engine for LLMs.',
     'url': 'https://github.com/vllm-project/vllm', 'stars': None, 'language': 'Python'},
    {'name': 'langchain-ai/langchain', 'desc': 'Building applications with LLMs through composability.',
     'url': 'https://github.com/langchain-ai/langchain', 'stars': None, 'language': 'Python'},
    {'name': 'huggingface/transformers', 'desc': 'State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.',
     'url': 'https://github.com/huggingface/transformers', 'stars': None, 'language': 'Python'},
]
# 👁️ display mode -> the notation it draws (modern and github-like differ in colour only).
MODES = {'modern': 'web', 'xml-like': 'xml', 'json': 'json', 'markdown': 'markdown', 'github-like': 'web'}
# ⚙️ this page's own row, beside 🌐 and 🎨: 🧾 the notation the profile and projects are shown in (its name follows 🌐: WORDS)
SETTINGS = [{'label': '🧾 Display mode', 'key': 'mode', 'options': [
    {'label': label, 'value': mode} for mode, label in zip(MODES, ('Modern', 'XML-like', 'JSON', 'Markdown', 'GitHub-like'))]}]
WORDS = {'表示形式': ['Display mode', "Mode d'affichage", 'Modo de visualización', 'Modo de exibição', 'وضع العرض', '显示模式',
                      'Режим отображения', 'Mode tampilan', 'Anzeigemodus', 'Hali ya kuonyesha']}
NOTATION_CLASS = {'web': '', 'xml': 'notation-root xml-renderer', 'json': 'notation-root json-renderer', 'markdown': 'notation-root markdown-renderer'}


def project_catalog(catalog: dict, curated: list, samples=frozenset()) -> list[dict]:
    """The projects to show: every public, non-archived repository of ``api/repos.json``, with ``projects.json`` curation.

    The catalog owns name and URL; curation only adds a description and topics, and entries for repositories that are
    not in the catalog are ignored. ``samples`` (lower-case names) are the repositories whose 🎥 moving sample of their
    Pages was recorded for this build (``media/pages/<name>.gif``, project_pages.py --record-samples)."""
    if not isinstance(catalog.get('repos'), list):
        raise ValueError('Invalid repository catalog')
    overrides = {project['name']: project for project in curated}
    projects = []
    for repo in catalog['repos']:
        if repo.get('archived') is True:
            continue
        project = overrides.get(repo['name'], {})
        projects.append({
            'name': repo['name'],
            'desc': project.get('desc') or repo.get('description') or repo.get('readmeSummary') or 'Explore the source and README on GitHub.',
            'url': repo['url'],
            'topics': list(dict.fromkeys([*(project.get('topics') or []), *(repo.get('topics') or [])])),
            'archived': False,
            **({'pages': repo['pages']} if repo.get('pages') else {}),                     # 🌐 the repository's own Pages
            **({'sample': f"./media/pages/{repo['name'].lower()}.gif"} if repo.get('pages') and repo['name'].lower() in samples else {}),
        })
    return projects


# ── notations: the same data as cards (web), XML-like, JSON and Markdown ────────────────────────────────────────────
# Everything a reader sees in a notation is written here. The page script only shows one of them, removes the projects
# a search hides, and fills the AI highlight templates with what the GitHub API returns.

def _e(text) -> str:
    return html.escape(str(text), quote=False)


def _a(text) -> str:
    return html.escape(str(text), quote=True)


def _link(url: str, text: str | None = None, attrs: str = '') -> str:
    return f'<a href="{_a(url)}" target="_blank" rel="noopener noreferrer"{attrs}>{_e(url if text is None else text)}</a>'


def _xml(indent: int, *parts: str, attrs: str = '') -> str:
    return f'<div class="xml-line" style="--indent: {indent}"{attrs}>{"".join(parts)}</div>'


def _tag(text: str, slots: bool = False) -> str:
    """One XML-like tag; with ``slots``, ``{field}`` becomes a slot the page script fills (AI highlights)."""
    text = _e(text)
    return '<span class="xml-tag">' + (re.sub(r'\{(\w+)\}', r'<span data-field="\1"></span>', text) if slots else text) + '</span>'


def _json_scalar(value) -> str:
    if isinstance(value, str):
        if re.match(r'https?://', value):
            return '"' + _link(value) + '"'
        return f'<span class="json-string">{_e(json.dumps(value, ensure_ascii=False))}</span>'
    return f'<span class="json-number">{_e(json.dumps(value))}</span>'


def json_lines(value, indent: int = 0, key: str | None = None, comma: str = '') -> str:
    """``value`` as indented JSON lines (what ``JSON.stringify(value, null, 2)`` would print, with links for URLs).

    ``comma`` is the HTML after the value: ``_COMMA`` between siblings, ``_LAST_COMMA`` where the page script decides."""
    head = f'<div class="json-line" style="--indent: {indent}">' + (f'<span class="json-key">"{_e(key)}"</span>: ' if key is not None else '')
    close = lambda mark: f'<div class="json-line" style="--indent: {indent}"><span class="json-punctuation">{mark}</span>{comma}</div>'
    if isinstance(value, list):
        return (head + '<span class="json-punctuation">[</span></div>'
                + ''.join(json_lines(item, indent + 1, None, _COMMA if at < len(value) - 1 else '') for at, item in enumerate(value)) + close(']'))
    if isinstance(value, dict):
        return (head + '<span class="json-punctuation">{</span></div>'
                + ''.join(json_lines(item, indent + 1, name, _COMMA if at < len(value) - 1 else '') for at, (name, item) in enumerate(value.items()))
                + close('}'))
    return head + _json_scalar(value) + comma + '</div>'


_COMMA = '<span class="json-punctuation">,</span>'
_LAST_COMMA = '<span class="json-punctuation" data-comma>,</span>'      # the page script drops the one after the last shown item


def profile_html(profile: dict, notation: str) -> str:
    if notation == 'xml':
        lines = [_xml(0, _tag('<Profile>')), _xml(1, _tag('<About>'), _e(profile['about']), _tag('</About>')), _xml(1, _tag('<Skills>'))]
        for group in profile['skills']:
            lines.append(_xml(2, _tag(f'<SkillGroup category="{group["category"]}">')))
            lines += [_xml(3, _tag(f'<Skill name="{item["name"]}" level="{item["level"]}" />')) for item in group['items']]
            lines.append(_xml(2, _tag('</SkillGroup>')))
        lines += [_xml(1, _tag('</Skills>')), _xml(1, _tag('<Career>'))]
        for entry in profile['career']:
            lines += [_xml(2, _tag(f'<Entry year="{entry["year"]}">')), _xml(3, _tag('<Title>'), _e(entry['title']), _tag('</Title>')),
                      _xml(3, _tag('<Description>'), _e(entry['desc']), _tag('</Description>')), _xml(2, _tag('</Entry>'))]
        return ''.join(lines + [_xml(1, _tag('</Career>')), _xml(0, _tag('</Profile>'))])
    if notation == 'json':
        return json_lines(profile)
    if notation == 'markdown':
        out = ['<h3 class="md-heading">### About</h3>', f'<p class="about-text">{_e(profile["about"])}</p>', '<h3 class="md-heading">### Skills</h3>']
        for group in profile['skills']:
            out.append(f'<h4 class="md-heading">#### {_e(group["category"])}</h4><ul class="md-list">'
                       + ''.join(f'<li>{_e(item["name"])} — {_e(item["level"])}%</li>' for item in group['items']) + '</ul>')
        return ''.join(out) + '<h3 class="md-heading">### Career</h3><ul class="md-list">' + ''.join(
            f'<li><strong>{_e(entry["year"])} — {_e(entry["title"])}</strong>: {_e(entry["desc"])}</li>' for entry in profile['career']) + '</ul>'
    import pysaiyanweboo as ui
    skills = ''.join(
        f'<div class="skill-group"><h4 class="skill-category">{_e(group["category"])}</h4>' + ''.join(
            f'<div class="skill-row"><span class="skill-label">{_e(item["name"])}</span><div class="skill-bar-track">'
            f'<div class="skill-bar-fill" style="--level:{int(item["level"])}%"></div></div></div>' for item in group['items']) + '</div>'
        for group in profile['skills'])
    career = '<ol class="timeline">' + ''.join(
        f'<li class="timeline-item"><span class="tl-year">{_e(entry["year"])}</span><div class="tl-body"><strong>{_e(entry["title"])}</strong>'
        f'<p>{_e(entry["desc"])}</p></div></li>' for entry in profile['career']) + '</ol>'
    return ui.tabs_html((('About', f'<p class="about-text">{_e(profile["about"])}</p>'), ('Skills', skills), ('Career', career)), id='profile')


def projects_html(projects: list[dict], notation: str) -> str:
    """Every project in ``notation``; each one is a ``data-project`` unit the page script can drop, ``data-empty`` shows when none is left."""
    unit = lambda project, inner, tag='div', cls='': f'<{tag}{cls} data-project="{_a(project["name"])}">{inner}</{tag}>'
    if notation == 'xml':
        body = ''.join(unit(p, ''.join([
            _xml(1, _tag(f'<Project name="{p["name"]}">')),
            *([_xml(2, _tag('<Status>'), 'Archived', _tag('</Status>'))] if p['archived'] else []),
            _xml(2, _tag('<Description>'), _e(p['desc']), _tag('</Description>')),
            _xml(2, _tag('<Url>'), _link(p['url']), _tag('</Url>')),
            *([_xml(2, _tag('<Pages>'), _link(p['pages']), _tag('</Pages>'))] if p.get('pages') else []),
            _xml(2, _tag('<Topics>')), *[_xml(3, _tag('<Topic>'), _e(topic), _tag('</Topic>')) for topic in p['topics']], _xml(2, _tag('</Topics>')),
            _xml(1, _tag('</Project>'))])) for p in projects)
        return (_xml(0, _tag('<Projects>')) + _xml(1, _e('<!-- No projects match your filter -->'), attrs=' data-empty')
                + body + _xml(0, _tag('</Projects>')))
    if notation == 'json':
        return ('<div class="json-line" style="--indent: 0"><span class="json-punctuation">[</span></div>'
                + ''.join(unit(p, json_lines(p, 1, None, _LAST_COMMA)) for p in projects)
                + '<div class="json-line" style="--indent: 0"><span class="json-punctuation">]</span></div>')
    if notation == 'markdown':
        return '<p data-empty>No projects match your filter.</p>' + ''.join(unit(p, (
            f'<h3 class="md-heading">### {_link(p["url"], p["name"])}</h3><p>{_e(p["desc"])}</p><ul class="md-list">'
            + ('<li>Status: Archived</li>' if p['archived'] else '') + f'<li>Topics: {_e(", ".join(p["topics"]))}</li>'
            + (f'<li>Pages: {_link(p["pages"])}</li>' if p.get('pages') else '')
            + f'<li>Source: {_link(p["url"])}</li></ul>')) for p in projects)
    cards = ''.join(unit(p, (
        f'<h3 class="ui-title">{_link(p["url"], p["name"])}</h3>' + ('<span class="ui-tag project-status">Archived</span>' if p['archived'] else '')
        + (f'<a class="project-sample" href="{_a(p["pages"])}"><img src="{_a(p["sample"])}" alt="🎥 {_a(p["name"])} の Pages" '
           'loading="lazy" width="240" height="456"></a>' if p.get('sample') else '')
        + f'<p class="ui-muted">{_e(p["desc"])}</p><div class="project-topics">' + ''.join(
            f'<span class="ui-tag" data-topic="{_a(topic)}" style="cursor: pointer" title="Filter by {_a(topic)}">{_e(topic)}</span>'
            for topic in p['topics'][:6])
        + '</div><div class="project-card-actions">'
        + (f'<a class="ui-button project-pages" href="{_a(p["pages"])}" aria-label="Open the GitHub Pages of {_a(p["name"])}">🌐 Pages</a>' if p.get('pages') else '')
        + '<img loading="lazy" alt="GitHub stars" '
          f'src="https://img.shields.io/github/stars/myon-bioinformatics/{_a(quote(p["name"], safe=""))}?style=social">'
          f'<button type="button" class="ui-button project-copy" data-copy="{_a(p["url"])}" aria-label="Copy repository URL for {_a(p["name"])}">Copy URL</button></div>'
    ), 'article', ' class="ui-card"') for p in projects)
    return '<div class="empty-projects-msg" data-empty>No projects match your filter.</div>' + cards


def highlights_html(notation: str) -> str:
    """AI highlights in ``notation`` for data that only exists in the browser: the frame, and one ``<template data-item>``
    whose ``data-field`` slots (and ``data-href`` links) the page script fills per highlight."""
    item = lambda inner: f'<template data-item>{inner}</template>'
    slot = lambda field, cls='', fmt='': f'<span{cls} data-field="{field}"{fmt}></span>'
    link = '<a target="_blank" rel="noopener noreferrer" data-href="url" data-field="{}"></a>'
    if notation == 'xml':
        return (_xml(0, _tag('<AiHighlights>')) + item(
            _xml(1, _tag('<Highlight name="{name}" stars="{stars}" language="{language}">', slots=True))
            + _xml(2, _tag('<Description>'), slot('desc'), _tag('</Description>')) + _xml(2, _tag('<Url>'), link.format('url'), _tag('</Url>'))
            + _xml(1, _tag('</Highlight>'))) + _xml(0, _tag('</AiHighlights>')))
    if notation == 'json':
        line = lambda key, value, comma=_COMMA: f'<div class="json-line" style="--indent: 2"><span class="json-key">"{key}"</span>: {value}{comma}</div>'
        text = lambda field: slot(field, ' class="json-string"', ' data-format="json"')
        return ('<div class="json-line" style="--indent: 0"><span class="json-punctuation">[</span></div>' + item(
            '<div class="json-line" style="--indent: 1"><span class="json-punctuation">{</span></div>'
            + line('name', text('name')) + line('desc', text('desc')) + line('url', '"' + link.format('url') + '"')
            + line('stars', slot('stars', ' class="json-number"', ' data-format="json"')) + line('language', text('language'), '')
            + f'<div class="json-line" style="--indent: 1"><span class="json-punctuation">}}</span>{_LAST_COMMA}</div>')
            + '<div class="json-line" style="--indent: 0"><span class="json-punctuation">]</span></div>')
    if notation == 'markdown':
        return item(f'<h3 class="md-heading">### {link.format("name")}</h3><p data-field="desc"></p>'
                    f'<ul class="md-list"><li>{slot("starsLabel")} • {slot("language")}</li></ul>')
    return item(f'<article class="card ai-card"><h3>{link.format("name")}</h3><p data-field="desc"></p>'
                '<div class="ai-meta"><span class="tag" data-field="starsLabel"></span><span class="tag" data-field="language"></span></div></article>')


def views_html(profile: dict, projects: list[dict]) -> str:
    """Every section in every notation, as inert ``<template>`` elements the page script mounts (``tpl-<section>-<notation>``)."""
    section_class = {'projects': {'web': 'ui-grid'}, 'highlights': {'web': 'grid'}}
    out = []
    for notation in dict.fromkeys(MODES.values()):
        for section, body in (('profile', profile_html(profile, notation)), ('projects', projects_html(projects, notation)),
                              ('highlights', highlights_html(notation))):
            cls = section_class.get(section, {}).get(notation, NOTATION_CLASS[notation])
            out.append(f'<template id="tpl-{section}-{notation}" data-class="{cls}">{body}</template>\n')
    return ''.join(out)


def topic_buttons(projects: list[dict]) -> str:
    topics = sorted({topic for project in projects for topic in project['topics']})
    return ''.join(f'<button type="button" class="tag-btn{" active" if tag == "all" else ""}" data-tag="{_a(tag)}" '
                   f'aria-pressed="{str(tag == "all").lower()}">{_e("All" if tag == "all" else tag)}</button>' for tag in ['all', *topics])


def _inline_json(value) -> str:
    """JSON that is safe inside a <script> element."""
    return json.dumps(value, ensure_ascii=False).replace('<', '\\u003c')


def markdown_fragment(root: Path, relative: str) -> str:
    """📄 A reviewed repository .md file (never visitor-supplied HTML) as HTML at build time, by the pinned markdown.py."""
    import markdown as md_market
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file() or path.suffix.lower() != '.md':
        raise ValueError('Markdown source must be an existing repository .md file')
    return md_market.markdown_to_html(path.read_text(encoding='utf-8'))


def table_bars(fragment: str) -> str:
    """📊 A table column whose every cell is a number gets a bar per row, as long as the number against the column's largest (the
    👩‍💻 Skills bars' rules, no script). The .md stays an ordinary table: the picture is made from it at build time."""
    number = re.compile(r'\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?')
    value = lambda cell: float(cell.strip().replace(',', ''))

    def draw(body: re.Match) -> str:
        rows = [re.findall(r'<td>(.*?)</td>', row, re.S) for row in re.findall(r'<tr>(.*?)</tr>', body[2], re.S)]
        if not rows or '<td ' in body[2] or len({len(row) for row in rows}) != 1:
            return body[0]
        tops = {at: max(value(row[at]) for row in rows) for at in range(len(rows[0])) if all(number.fullmatch(row[at].strip()) for row in rows)}
        if not any(tops.values()):
            return body[0]
        bar = lambda at, cell: (f'<td class="document-number">{cell}<span class="skill-bar-track" aria-hidden="true"><span class="skill-bar-fill" '
                                f'style="--level:{value(cell) / tops[at] * 100 if tops[at] else 0:.0f}%"></span></span></td>')
        return body[1] + '\n' + ''.join('<tr>' + ''.join(bar(at, cell) if at in tops else f'<td>{cell}</td>' for at, cell in enumerate(row)) + '</tr>\n'
                                        for row in rows) + body[3]
    return re.sub(r'(<tbody>)(.*?)(</tbody>)', draw, fragment, flags=re.S)


def documents_html(root: Path, documents) -> str:
    """📄 The reviewed .md files site.config.json lists (``documents``: ``[{"id", "title", "source", "note"?}]``), each one a section
    of this page at ``#id`` (so ☰ lists it), turned into HTML at build time. A new document is a new row there, not a new page.
    📊 A table's number columns are drawn as bars (``table_bars``)."""
    if not isinstance(documents, list) or len(documents) > 8:
        raise ValueError('documents lists up to 8 {id, title, source, note}')
    seen, parts = set(), []
    for entry in documents:
        if not isinstance(entry, dict) or set(entry) - {'id', 'title', 'source', 'note'} or not all(
                isinstance(entry.get(key), str) and entry[key].strip() for key in ('id', 'title', 'source', *(('note',) if 'note' in entry else ()))):
            raise ValueError('a document has id, title, source and an optional note')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', entry['id']) or entry['id'] in seen:
            raise ValueError('a document id is a unique lowercase token')
        seen.add(entry['id'])
        note = f'      <p class="section-sub">{_e(entry["note"])}</p>\n' if 'note' in entry else ''
        parts.append(f'    <section id="{entry["id"]}" class="container document" aria-label="{_a(entry["title"])}">\n      <h2>{_e(entry["title"])}</h2>\n{note}'
                     f'      <article class="document-markdown">{table_bars(markdown_fragment(root, entry["source"]))}</article>\n    </section>\n\n')
    return ''.join(parts)


def document(root: Path | None = None, ui=None, samples=frozenset()) -> str:
    root = Path(__file__).resolve().parents[1] if root is None else Path(root)
    if ui is None:
        import pysaiyanweboo as ui
    read = lambda name: json.loads((root / name).read_text(encoding='utf-8'))
    profile, projects = read('profile.json'), project_catalog(read('api/repos.json'), read('projects.json'), samples)
    palettes = ''.join(ui.theme_css(name, tokens) for name, tokens in ui.theme_palettes().items())
    data = (f'<script type="application/json" id="projects-data">{_inline_json([{k: p[k] for k in ("name", "desc", "topics")} for p in projects])}</script>\n'
            f'<script type="application/json" id="page-data">{_inline_json({"modes": MODES, "fallback": AI_FALLBACK})}</script>\n')
    script = ui.module_script('\n'.join((ui.js_source('collection.js'), SCRIPT)))
    page = SHELL
    documents = documents_html(root, read('site.config.json').get('documents', []))
    for mark, value in (('@@PORTAL@@', portal_cards(samples)), ('@@TOPICS@@', topic_buttons(projects)),
                        ('@@VIEWS@@', views_html(profile, projects) + data), ('@@STYLE@@', '\n' + palettes + '\n' + ui.tabs_css() + '\n' + STYLE + '\n  '),
                        ('@@DOCUMENTS@@', documents), ('@@SCRIPT@@', script)):
        assert page.count(mark) == 1, mark
        page = page.replace(mark, value)
    return page



SHELL = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>myon-bioinformatics — Portfolio</title>
  <meta name="description" content="Bioinformatics → Security/Backend engineer. Practical CLI and browser tools in Python, plus Node.js and Dart/Flutter.">
  <link rel="icon" href="./favicon.ico" sizes="16x16 32x32 48x48">
  <link rel="icon" type="image/png" sizes="32x32" href="./assets/brand/favicon-32x32.png">
  <link rel="icon" type="image/png" sizes="16x16" href="./assets/brand/favicon-16x16.png">
  <!-- 📱 Home screen / shortcut: label, icon and destination (tests/test_site.py checks them against manifest.webmanifest) -->
  <link rel="manifest" href="./manifest.webmanifest">
  <link rel="apple-touch-icon" sizes="170x170" href="./assets/brand/myon-profile-icon.png">
  <meta name="apple-mobile-web-app-title" content="🧬 myon">
  <meta name="application-name" content="🧬 myon">
  <link rel="stylesheet" href="./tools/vendor/web-ui/css/tokens.css">
  <link rel="stylesheet" href="./tools/vendor/web-ui/css/base.css">
  <link rel="stylesheet" href="./tools/vendor/web-ui/css/components.css">
  <link rel="stylesheet" href="./tools/vendor/web-ui/css/themes/modern.css">
  <style>@@STYLE@@</style>
</head>
<body data-ui-theme="modern">
  <header class="site-header">
    <div class="container">
      <h1><img class="brand-icon" src="./assets/brand/myon-profile-icon.png" alt="" width="40" height="40">myon-bioinformatics</h1>
    </div>
  </header>

  <main>
    <section class="container intro">
      <h2>👋 Hello</h2>
      <p>Bioinformatics → Security/Backend engineer. I build practical CLI and browser tools in Python, plus Node.js and Dart/Flutter.</p>
    </section>

    <section id="profile" class="container">
      <h2>🧑‍💻 Profile</h2>
      <div id="profile-render-root"></div>
    </section>

    <section id="projects" class="container">
      <h2>🚀 Projects</h2>
      <p class="section-sub">Each card is a public repository: the title opens GitHub, 🌐 Pages opens the live site when there is one, and 📄 opens a recorded example on this portfolio.</p>
      <div class="projects-controls" id="projects-controls">
        <div class="project-search-wrap">
          <input class="ui-input" type="search" id="project-search-input" placeholder="Search projects by name, description, or topic..." aria-label="Search projects">
          <button type="button" id="project-search-clear" class="btn-clear" hidden aria-label="Clear search">✕</button>
        </div>
        <details class="project-topic-controls">
          <summary>Filter by topic</summary>
          <div class="project-tags-filter" id="project-tags-filter" role="group" aria-label="Filter projects by topic">@@TOPICS@@</div>
        </details>
      </div>
      <div id="projects-count" class="projects-count" aria-live="polite"></div>
      <div id="projects-render-root"></div>
      <p class="more">
        More on <a href="https://github.com/myon-bioinformatics" target="_blank" rel="noopener noreferrer">GitHub</a>
      </p>
    </section>

    <section id="ai-highlights" class="container">
      <div class="section-header-wrap">
        <h2>🤖 AI &amp; Tech Highlights</h2>
        <button type="button" id="ai-highlights-refresh" class="btn-refresh" aria-label="Refresh AI highlights">🎲 Shuffle</button>
      </div>
      <p id="ai-highlights-status" class="section-sub" role="status">Curated examples — checking live GitHub data.</p>
      <div id="ai-highlights-render-root"></div>
    </section>

    <section id="tools" class="container">
      <h2>🧰 Tools</h2>
      <p>ブラウザで使う道具。🧩 は作りに使ったリポジトリ（それぞれの使い方・検証・GIF は 🚀 Projects の 🌐 Pages）。</p>
@@PORTAL@@      </div>
    </section>

@@DOCUMENTS@@  </main>

@@VIEWS@@  @@SCRIPT@@
</body>
</html>

'''

STYLE = ''':root {
  --fg:#0b0b0c;
  --bg:#ffffff;
  --muted:#444;
  --border:#e5e7eb;
  --syntax-xml:#087ea4;
  --syntax-json-punctuation:#8250df;
  --syntax-json-key:#0550ae;
  --syntax-json-string:#116329;
  --syntax-json-number:#953800;
  --syntax-markdown-marker:#8250df;
  --syntax-markdown-link:#0969da;
  --terminal-bg:#0d1117;
  --terminal-panel:#101820;
  --terminal-fg:#d1f7c4;
  --terminal-muted:#8b949e;
  --terminal-border:#58a6ff;
  --terminal-accent:#7ee787;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fg:#e6e6e6;
    --bg:#0b0b0c;
    --muted:#c9c9c9;
    --border:#222;
    --syntax-xml:#79c0ff;
    --syntax-json-punctuation:#d2a8ff;
    --syntax-json-key:#79c0ff;
    --syntax-json-string:#a5d6ff;
    --syntax-json-number:#ffa657;
    --syntax-markdown-marker:#d2a8ff;
    --syntax-markdown-link:#58a6ff;
  }
}
*{box-sizing:border-box} body{margin:0;color:var(--fg);background:var(--bg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,'Helvetica Neue',Arial}
a{color:inherit}
.container{max-width:960px;margin:0 auto;padding:1.5rem}
.site-header{border-bottom:1px solid var(--border)}
.site-header .container{display:grid;grid-template-columns:minmax(0,1fr);align-items:center;gap:1rem}
.site-header h1{display:flex;align-items:center;gap:.75rem;margin:0;max-width:100%;font-size:1.25rem;overflow-wrap:anywhere}
.site-header .brand-icon{display:block;flex:none;width:40px;height:40px}
h2{margin:0 0 .75rem}
.document{scroll-margin-top:1rem}
.document-markdown{border:1px solid var(--border);border-radius:10px;padding:1rem;overflow-wrap:anywhere}
.document-markdown a{overflow-wrap:anywhere}
.document-markdown pre{overflow:auto}
.document-markdown table{border-collapse:collapse;max-width:100%;margin:0 0 16px}
.document-markdown th,.document-markdown td,.document-markdown td a{padding:4px 16px 4px 0;text-align:left;vertical-align:middle;overflow-wrap:break-word}
.document-markdown td a{padding:0}
.document-markdown td.document-number{min-width:160px;font-variant-numeric:tabular-nums}
.document-markdown td.document-number .skill-bar-track,.document-markdown td.document-number .skill-bar-fill{display:block}

.intro{padding-top:.5rem}

#projects h2 { margin-bottom: 0.75rem; }

/* AI Highlights section & refresh button */
.section-header-wrap {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.25rem;
  flex-wrap: wrap;
  gap: 8px;
}
.section-header-wrap h2 {
  margin: 0;
}
.section-sub {
  font-size: 0.9rem;
  color: var(--muted);
  margin-top: 0;
  margin-bottom: 0.85rem;
}
.btn-refresh {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 12px;
  font: inherit;
  font-size: 0.85rem;
  color: var(--muted);
  cursor: pointer;
  transition: all .15s ease;
}
.btn-refresh:hover {
  color: var(--fg);
  border-color: var(--fg);
}
.ai-meta {
  display: flex;
  gap: 6px;
  margin-top: 10px;
}

/* Projects controls: Search & Tag Filter */
.projects-controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 0.75rem;
}
.project-search-wrap {
  position: relative;
  width: 100%;
  max-width: 480px;
}
#project-search-input {
  width: 100%;
  padding: 6px 30px 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font: inherit;
  font-size: 0.9rem;
}
.btn-clear {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  padding: 2px 6px;
  font-size: 0.9rem;
  line-height: 1;
}
.btn-clear:hover {
  color: var(--fg);
}
.project-tags-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
  font: inherit;
  font-size: 0.8rem;
  color: var(--muted);
  cursor: pointer;
  transition: background .15s, color .15s, border-color .15s;
}
.tag-btn:hover {
  color: var(--fg);
  border-color: var(--fg);
}
.tag-btn.active {
  background: var(--fg);
  color: var(--bg);
  border-color: var(--fg);
  font-weight: 600;
}
.projects-count {
  font-size: 0.85rem;
  color: var(--muted);
  margin-bottom: 0.75rem;
}
.empty-projects-msg {
  padding: 1rem 0;
  color: var(--muted);
  font-style: italic;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 10px;
  gap: 8px;
}
.copy-btn {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 3px 8px;
  font: inherit;
  font-size: 0.75rem;
  color: var(--muted);
  cursor: pointer;
  transition: all .15s ease;
}
.copy-btn:hover {
  color: var(--fg);
  border-color: var(--fg);
}
.copy-btn.copied {
  background: #2da44e;
  border-color: #2da44e;
  color: #ffffff;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill,minmax(260px,1fr));
  gap: 12px;
}
.card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  transition: transform .08s ease, box-shadow .12s ease;
  background: var(--bg);
}
.card:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0,0,0,.06); }
.card h3 { margin: 0 0 6px; font-size: 1.05rem; }
.card p { margin: 0 0 10px; color: var(--muted); line-height: 1.4; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; }
.badges .tag {
  font-size: .75rem; background: #f3f4f6; border: 1px solid var(--border);
  padding: 2px 8px; border-radius: 999px; color: #333;
}
@media (prefers-color-scheme: dark) {
  .badges .tag { background: #141417; color: #ddd; }
}
.more { margin-top: 8px; font-size: .95rem; }

/* ── Profile tabs (PySaiyanWeBoo's tabs_html: a radio and a label each, no script) ── */
#profile h2 { margin-bottom: 0.75rem; }
.ui-tabs { display: flex; flex-wrap: wrap; gap: 0 6px; margin: 0; }
.ui-tab {
  position: relative; background: none; border: 0; border-radius: 0; padding: 6px 16px; margin: 0;
  font: inherit; color: var(--muted); border-bottom: 2px solid transparent;
  transition: color .15s, border-color .15s;
}
.ui-tab:hover { color: var(--fg); }
.ui-tab-input:checked + .ui-tab { color: var(--fg); background: none; border-bottom-color: currentColor; font-weight: 600; }
.ui-tab-panel { flex: 0 0 100%; margin-top: -1px; padding-top: 1rem; border-top: 1px solid var(--border); }

/* About */
.about-text { line-height: 1.7; white-space: pre-line; }

/* Skills */
.skill-group { margin-bottom: 1.25rem; }
.skill-category { margin: 0 0 .5rem; font-size: .85rem; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); }
.skill-row { display: grid; grid-template-columns: 140px 1fr; align-items: center; gap: 10px; margin-bottom: 8px; }
.skill-label { font-size: .9rem; }
.skill-bar-track {
  height: 8px; border-radius: 999px;
  background: var(--border); overflow: hidden;
}
.skill-bar-fill {
  height: 100%; border-radius: 999px;
  background: var(--fg);
  width: var(--level);
  animation: skill-grow .6s cubic-bezier(.4,0,.2,1);
}
@keyframes skill-grow { from { width: 0; } }

/* Career timeline */
.timeline { list-style: none; margin: 0; padding: 0; position: relative; }
.timeline::before {
  content: ''; position: absolute; left: 52px; top: 6px; bottom: 6px;
  width: 2px; background: var(--border);
}
.timeline-item {
  display: grid; grid-template-columns: 64px 1fr; gap: 12px;
  position: relative; margin-bottom: 1.25rem;
}
.timeline-item::before {
  content: ''; position: absolute; left: 48px; top: 5px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--fg); border: 2px solid var(--bg);
  box-shadow: 0 0 0 2px var(--border);
}
.tl-year { font-size: .8rem; color: var(--muted); padding-top: 3px; text-align: right; }
.tl-body strong { display: block; margin-bottom: 2px; }
.tl-body p { margin: 0; color: var(--muted); font-size: .9rem; line-height: 1.5; }

/* ── Modern terminal / ASCII-inspired mode ─────────────────────────────── */
body[data-view-mode="modern"] {
  background: var(--terminal-bg);
  color: var(--terminal-fg);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
body[data-view-mode="modern"] .site-header,
body[data-view-mode="modern"] .site-footer {
  border-color: var(--terminal-border);
  border-style: dashed;
}
body[data-view-mode="modern"] .site-header h1::before { content: "$ "; color: var(--terminal-accent); }
body[data-view-mode="modern"] .intro h2::before,
body[data-view-mode="modern"] #profile h2::before,
body[data-view-mode="modern"] #projects h2::before,
body[data-view-mode="modern"] .outro h2::before {
  content: "> ";
  color: var(--terminal-accent);
}
body[data-view-mode="modern"] #profile,
body[data-view-mode="modern"] #projects,
body[data-view-mode="modern"] #ai-highlights {
  position: relative;
  margin-top: 1rem;
  margin-bottom: 1rem;
  border: 1px solid var(--terminal-border);
  background: var(--terminal-panel);
  box-shadow: 6px 6px 0 rgba(88,166,255,.18);
}
body[data-view-mode="modern"] #profile::before,
body[data-view-mode="modern"] #projects::before,
body[data-view-mode="modern"] #ai-highlights::before {
  position: absolute;
  top: -.9rem;
  left: 1rem;
  padding: 0 .45rem;
  background: var(--terminal-bg);
  color: var(--terminal-border);
  font-size: .78rem;
}
body[data-view-mode="modern"] #profile::before { content: "+--[ profile ]--+"; }
body[data-view-mode="modern"] #projects::before { content: "+--[ projects ]--+"; }
body[data-view-mode="modern"] #ai-highlights::before { content: "+--[ ai highlights ]--+"; }
body[data-view-mode="modern"] .btn-refresh {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: var(--terminal-panel);
  color: var(--terminal-fg);
}
body[data-view-mode="modern"] .btn-refresh::before { content: "[ "; color: var(--terminal-border); }
body[data-view-mode="modern"] .btn-refresh::after { content: " ]"; color: var(--terminal-border); }
body[data-view-mode="modern"] .ui-tabs { gap: 0; }
body[data-view-mode="modern"] .ui-tab-panel { border-top: 1px dashed var(--terminal-border); }
body[data-view-mode="modern"] .ui-tab {
  border-right: 1px solid var(--terminal-border);
  border-bottom: 0;
  color: var(--terminal-muted);
}
body[data-view-mode="modern"] .ui-tab::before { content: "[ "; color: var(--terminal-border); }
body[data-view-mode="modern"] .ui-tab::after { content: " ]"; color: var(--terminal-border); }
body[data-view-mode="modern"] .ui-tab-input:checked + .ui-tab {
  border-right-color: var(--terminal-border);
  color: var(--terminal-fg);
  background: rgba(126,231,135,.08);
}
body[data-view-mode="modern"] .ui-tab-input:checked + .ui-tab::before { content: "[> "; color: var(--terminal-accent); }
body[data-view-mode="modern"] .card {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: var(--terminal-panel);
  box-shadow: 3px 3px 0 rgba(88,166,255,.16);
}
body[data-view-mode="modern"] .card h3::before { content: "> "; color: var(--terminal-accent); }
body[data-view-mode="modern"] .card p,
body[data-view-mode="modern"] .tl-body p,
body[data-view-mode="modern"] .tl-year,
body[data-view-mode="modern"] .skill-category { color: var(--terminal-muted); }
body[data-view-mode="modern"] .badges .tag {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: transparent;
  color: var(--terminal-fg);
}
body[data-view-mode="modern"] .badges .tag::before { content: "#"; color: var(--terminal-accent); }
body[data-view-mode="modern"] .skill-bar-track {
  height: 10px;
  border: 1px solid var(--terminal-border);
  border-radius: 0;
  background: transparent;
}
body[data-view-mode="modern"] .skill-bar-fill {
  border-radius: 0;
  background: repeating-linear-gradient(90deg, var(--terminal-accent) 0 6px, transparent 6px 8px);
}
body[data-view-mode="modern"] .timeline::before {
  background: none;
  border-left: 2px dashed var(--terminal-border);
}
body[data-view-mode="modern"] .timeline-item::before {
  border-radius: 0;
  background: var(--terminal-accent);
  border-color: var(--terminal-panel);
  box-shadow: 0 0 0 1px var(--terminal-border);
}
body[data-view-mode="modern"] a { color: inherit; }
body[data-view-mode="modern"] #project-search-input {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: var(--terminal-panel);
  color: var(--terminal-fg);
}
body[data-view-mode="modern"] .btn-clear {
  color: var(--terminal-muted);
}
body[data-view-mode="modern"] .tag-btn {
  border-radius: 0;
  border-color: var(--terminal-border);
  color: var(--terminal-muted);
}
body[data-view-mode="modern"] .tag-btn::before { content: "[ "; color: var(--terminal-border); }
body[data-view-mode="modern"] .tag-btn::after { content: " ]"; color: var(--terminal-border); }
body[data-view-mode="modern"] .tag-btn.active {
  background: rgba(126, 231, 135, .12);
  color: var(--terminal-fg);
  border-color: var(--terminal-accent);
}
body[data-view-mode="modern"] .tag-btn.active::before { content: "[> "; color: var(--terminal-accent); }
body[data-view-mode="modern"] .projects-count,
body[data-view-mode="modern"] .empty-projects-msg {
  color: var(--terminal-muted);
}
body[data-view-mode="modern"] .copy-btn {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: transparent;
  color: var(--terminal-fg);
}
body[data-view-mode="modern"] .copy-btn.copied {
  background: var(--terminal-accent);
  color: var(--terminal-bg);
  border-color: var(--terminal-accent);
}

/* ── XML-like mode ───────────────────────────────────────────────────────── */
body[data-view-mode="xml-like"] {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
body[data-view-mode="xml-like"] h2[data-tag]::before {
  content: "<" attr(data-tag) ">";
  margin-right: .4rem;
  color: var(--syntax-xml);
  font-size: .9em;
}
body[data-view-mode="xml-like"] h2[data-tag]::after {
  content: "</" attr(data-tag) ">";
  margin-left: .4rem;
  color: var(--syntax-xml);
  font-size: .9em;
}
body[data-view-mode="xml-like"] .card,
body[data-view-mode="xml-like"] .timeline-item,
body[data-view-mode="xml-like"] .skill-group {
  border-radius: 0;
}

/* ── JSON mode ───────────────────────────────────────────────────────────── */
body[data-view-mode="json"] {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}
body[data-view-mode="json"] h2[data-tag]::before {
  content: '"' attr(data-tag) '": ';
  color: var(--syntax-json-punctuation);
}
body[data-view-mode="json"] h2[data-tag]::after {
  content: ",";
  color: var(--syntax-json-punctuation);
}
body[data-view-mode="json"] .container {
  border-left: 3px solid var(--border);
  padding-left: 1rem;
}
body[data-view-mode="json"] .card {
  border-radius: 4px;
}

/* ── Markdown mode ───────────────────────────────────────────────────────── */
body[data-view-mode="markdown"] h2::before {
  content: "## ";
  color: var(--syntax-markdown-marker);
}
body[data-view-mode="markdown"] .card h3::before {
  content: "### ";
  color: var(--syntax-markdown-marker);
}
body[data-view-mode="markdown"] a {
  text-decoration: underline;
  text-underline-offset: 2px;
}
body[data-view-mode="markdown"] .card {
  border-radius: 6px;
  border-style: dashed;
}

/* ── GitHub-like mode ────────────────────────────────────────────────────── */
body[data-view-mode="github-like"] {
  background: #f6f8fa;
  color: #24292f;
}
body[data-view-mode="github-like"] .site-header,
body[data-view-mode="github-like"] .site-footer,
body[data-view-mode="github-like"] .card,
body[data-view-mode="github-like"] .ui-tab-panel {
  background: #ffffff;
}
body[data-view-mode="github-like"] .site-header,
body[data-view-mode="github-like"] .site-footer,
body[data-view-mode="github-like"] .card,
body[data-view-mode="github-like"] .ui-tab-panel {
  border-color: #d0d7de;
}
body[data-view-mode="github-like"] .card {
  border-radius: 6px;
  box-shadow: none;
}
body[data-view-mode="github-like"] .card:hover {
  transform: none;
  box-shadow: 0 1px 0 rgba(27, 31, 36, 0.04);
}
body[data-view-mode="github-like"] .badges .tag {
  background: #f6f8fa;
  color: #57606a;
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    scroll-behavior: auto !important;
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
  .card:hover { transform: none; }
}

@media (max-width: 720px) {
  .container { padding: 1.25rem; }
  body[data-view-mode="json"] .container { padding-left: 1rem; }
  .site-header .container { grid-template-columns:1fr; }
  .grid {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }
  .ui-tab { padding: 10px 14px; }
  .skill-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .timeline::before {
    left: 12px;
    top: 8px;
    bottom: 8px;
  }
  .timeline-item {
    grid-template-columns: 1fr;
    gap: 6px;
    padding-left: 32px;
  }
  .timeline-item::before { left: 8px; }
  .tl-year {
    text-align: left;
    padding-top: 0;
    font-weight: 600;
  }
  .card { padding: 14px; }
}

@media (max-width: 520px) {
  .container { padding: 1rem; }
  .site-header h1 { font-size: 1.1rem; }
  .grid { grid-template-columns: 1fr; }
}


/* Projects extends the pinned web-ui components used by the tool pages. */
body[data-ui-theme="modern"] {
  --terminal-bg: var(--ui-bg);
  --terminal-panel: var(--ui-panel);
  --terminal-fg: var(--ui-fg);
  --terminal-muted: var(--ui-muted);
  --terminal-border: var(--ui-border);
  --terminal-accent: var(--ui-accent);
}
body[data-ui-theme="plain"] {
  --ui-bg: var(--bg); --ui-panel: var(--bg); --ui-fg: var(--fg);
  --ui-muted: var(--muted); --ui-border: var(--border);
}
body[data-ui-theme="github-like"] {
  --ui-bg: #f6f8fa; --ui-panel: #ffffff; --ui-fg: #24292f;
  --ui-muted: #57606a; --ui-border: #d0d7de;
}
body[data-ui-theme="github-like"] #projects .ui-card { background: var(--ui-panel); }
body[data-view-mode="modern"] #projects .section-sub { color: var(--terminal-muted); }
#projects .ui-card { min-width: 0; overflow-wrap: anywhere; }
#projects .ui-title { margin: 0 0 .5rem; font-size: 1.05rem; }
#projects .ui-button, #projects .ui-input { min-height: 44px; }
.project-topics { display: flex; flex-wrap: wrap; gap: .4rem; font-size: .75rem; }
.project-sample { display: block; margin: .5rem 0; }
.project-sample img { display: block; width: 100%; max-width: 240px; height: auto; border-radius: 8px; }
.project-card-actions { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem; margin-top: .75rem; }
.project-copy { cursor: pointer; font-size: .8rem; }
.project-copy.copied { background: var(--ui-accent); color: var(--ui-bg); }
#projects-render-root { overflow-wrap: anywhere; }
.project-topic-controls summary { cursor: pointer; margin: .75rem 0; }
.project-topic-controls .project-tags-filter { max-height: 12rem; overflow-y: auto; padding: .25rem; }
.project-status { margin-bottom: .5rem; font-size: .8rem; }

/* ── 🧰 Tools portal ──────────────────────────────────────────────── */
.portal-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.portal-card {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.portal-card > a {
  margin-top: auto;
  font-weight: 600;
}
.portal-card > a.project-sample { margin: 0 0 8px; }
.portal-points {
  margin: 0 0 12px;
  padding-left: 1.2em;
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.portal-points li + li { margin-top: 4px; }
.portal-from { margin: 0 0 8px; font-size: 0.8em; color: var(--ui-muted); overflow-wrap: anywhere; }

/* Dedicated notation renderers. Layout lives here; content still comes from profile.json/projects.json. */
.notation-root {
  margin: .5rem 0 1rem;
}

.xml-renderer,
.json-renderer,
.markdown-renderer {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

.xml-renderer,
.json-renderer {
  font-size: .92rem;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.xml-line,
.json-line {
  padding-left: calc(var(--indent, 0) * 1.25rem);
  white-space: pre-wrap;
}

.xml-tag {
  color: var(--syntax-xml);
}

.xml-renderer a,
.json-renderer a {
  text-decoration: underline;
  text-underline-offset: 2px;
}

.json-line {
  color: var(--syntax-json-punctuation);
}

.json-key {
  color: var(--syntax-json-key);
  font-weight: 600;
}

.json-string {
  color: var(--syntax-json-string);
}

.json-number {
  color: var(--syntax-json-number);
}

.json-punctuation {
  color: var(--syntax-json-punctuation);
}

.json-renderer a {
  color: var(--syntax-json-string);
}

.markdown-renderer .md-heading {
  margin: 1rem 0 .4rem;
  color: var(--syntax-markdown-marker);
}

.markdown-renderer .md-heading:first-child {
  margin-top: 0;
}

.markdown-renderer .md-list {
  margin-top: .35rem;
  list-style-type: "-  ";
}

.markdown-renderer .md-list ::marker {
  color: var(--syntax-markdown-marker);
}

.markdown-renderer .md-list li,
.markdown-renderer p {
  color: var(--fg);
}

.markdown-renderer a {
  color: var(--syntax-markdown-link);
  text-decoration: underline;
  text-underline-offset: 2px;
}

@media (max-width: 520px) {
  .xml-line,
  .json-line {
    padding-left: calc(var(--indent, 0) * .75rem);
  }
}

/* 🎨 A palette chosen in ⚙️ (PySaiyanWeBoo's, body[data-ui-theme=NAME]) drives this page's own colours too; Modern and GitHub-like are
   this page's own looks (body[data-ui-theme=modern] above). */
body[data-ui-theme-chosen]:not([data-ui-theme-chosen="modern"], [data-ui-theme-chosen="github-like"]) {
  --fg: var(--ui-fg); --bg: var(--ui-bg); --muted: var(--ui-muted); --border: var(--ui-border);
  --terminal-bg: var(--ui-bg); --terminal-panel: var(--ui-panel); --terminal-fg: var(--ui-fg);
  --terminal-muted: var(--ui-muted); --terminal-border: var(--ui-accent); --terminal-accent: var(--ui-accent);
  --syntax-xml: var(--ui-accent); --syntax-json-punctuation: var(--ui-muted); --syntax-json-key: var(--ui-accent);
  --syntax-json-string: var(--ui-fg); --syntax-json-number: var(--ui-danger);
  --syntax-markdown-marker: var(--ui-accent); --syntax-markdown-link: var(--ui-accent);
}'''

SCRIPT = '''// The page script. What each notation looks like is decided in Python (scripts/front_page.py) and arrives as <template>
// elements; this script shows one, drops the projects a search hides, and fills the AI highlight slots.
import { copyText } from './tools/vendor/web-ui/js/ui.js';

const DEFAULT_VIEW_MODE = 'modern';
const VIEW_MODE_KEY = 'site:view-mode';
const VIEW_MODE_BASE_KEY = 'site:view-mode-base';
const PAGE = JSON.parse(document.getElementById('page-data').textContent);
const PROJECTS = JSON.parse(document.getElementById('projects-data').textContent);

let configuredViewMode = DEFAULT_VIEW_MODE;
let currentTagFilter = 'all';
let currentSearchQuery = '';
let aiHighlightsPool = [];
let displayedAiHighlights = [];

function shuffleItems(items) {
  const shuffled = [...items];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

// A fresh project order on each page load, the same in every notation.
const projectOrder = shuffleItems(PROJECTS.map((project) => project.name));

function normalizeViewMode(mode) {
  return Object.hasOwn(PAGE.modes, mode) ? mode : DEFAULT_VIEW_MODE;
}

function readStored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function store(key, value) {
  try {
    if (value) localStorage.setItem(key, value); else localStorage.removeItem(key);
  } catch {
    // ignore storage failures
  }
}

function getCurrentMode() {
  return normalizeViewMode(document.body.dataset.viewMode || configuredViewMode);
}

// The notation of a section, from its Python-built template.
function mount(root, section, notation) {
  const template = document.getElementById(`tpl-${section}-${notation}`);
  root.replaceChildren(template.content.cloneNode(true));
  root.className = template.dataset.class;
  root.dataset.renderer = notation;
}

function dropLastComma(root) {
  const commas = root.querySelectorAll('[data-comma]');
  if (commas.length) commas[commas.length - 1].remove();
}

// 🎨 is ⚙️'s (PySaiyanWeBoo's bindTheme: one choice for every page of the site, so tools/ has it too); its "this page's own" is the
// display mode's look. The page tells bindTheme which look is its own (pageTheme's contract: data-ui-theme-page).
function applyOwnColours() {
  const mode = getCurrentMode(), body = document.body;
  body.dataset.uiThemePage = mode === 'modern' || mode === 'github-like' ? mode : 'plain';
  if (body.dataset.uiThemeChosen === undefined) body.dataset.uiTheme = body.dataset.uiThemePage;
}

function applyViewMode(mode) {
  const normalized = normalizeViewMode(mode);
  document.body.dataset.viewMode = normalized;
  applyOwnColours();
  const choice = document.querySelector('[data-chrome-choice="mode"]');   // ⚙️ 🧾 says the mode in effect
  if (choice && choice.value !== normalized) choice.value = normalized;
  renderPortfolio();
}

async function readConfiguredViewMode() {
  try {
    const res = await fetch('./site.config.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const config = await res.json();
    return normalizeViewMode(config?.defaultViewMode);
  } catch {
    return DEFAULT_VIEW_MODE;
  }
}

function getFilteredProjects() {
  const facets = {};
  if (currentTagFilter !== 'all') facets.topic = currentTagFilter;
  return WebUICollections.filterItems(PROJECTS, {
    query: currentSearchQuery,
    text: project => [project.name, project.desc, ...(project.topics || [])],
    facets,
    facetValues: { topic: project => project.topics || [] },
  });
}

function updateProjectsCount(filteredCount, totalCount) {
  const countEl = document.getElementById('projects-count');
  if (!countEl) return;
  if (filteredCount === totalCount) {
    countEl.textContent = `Showing all ${totalCount} projects`;
  } else if (filteredCount > 0) {
    countEl.textContent = `Showing ${filteredCount} of ${totalCount} projects`;
  } else {
    countEl.textContent = 'No matching projects found.';
  }
}

function renderProjects(notation) {
  const root = document.getElementById('projects-render-root');
  mount(root, 'projects', notation);
  const shown = new Set(getFilteredProjects().map((project) => project.name));
  const units = new Map([...root.querySelectorAll('[data-project]')].map((unit) => [unit.dataset.project, unit]));
  const first = units.values().next().value;
  const parent = first ? first.parentNode : root;
  const after = first ? [...units.values()].pop().nextSibling : null;
  for (const name of projectOrder) {
    const unit = units.get(name);
    if (shown.has(name)) parent.insertBefore(unit, after); else unit.remove();
  }
  if (shown.size) root.querySelectorAll('[data-empty]').forEach((note) => note.remove());
  dropLastComma(root);
  updateProjectsCount(shown.size, PROJECTS.length);
}

function setTagFilter(tag) {
  currentTagFilter = tag;
  document.querySelectorAll('#project-tags-filter .tag-btn').forEach((btn) => {
    const active = btn.dataset.tag === tag;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  renderPortfolio();
}

async function copyUrl(button) {
  const url = button.dataset.copy;
  try {
    await copyText(url);
    button.textContent = 'Copied!';
    button.classList.add('copied');
    setTimeout(() => {
      button.textContent = 'Copy URL';
      button.classList.remove('copied');
    }, 1500);
  } catch (err) {
    console.error('Copy failed:', err);
  }
}

function highlightStars(stars) {
  return stars == null ? 'Curated example' : `★ ${stars.toLocaleString()} stars`;
}

function pickRandomAiHighlights(count = 3) {
  if (!aiHighlightsPool.length) aiHighlightsPool = [...PAGE.fallback];
  displayedAiHighlights = shuffleItems(aiHighlightsPool).slice(0, count);
}

function renderAiHighlights(notation) {
  const root = document.getElementById('ai-highlights-render-root');
  mount(root, 'highlights', notation);
  const slot = root.querySelector('template[data-item]');
  for (const highlight of displayedAiHighlights) {
    const values = { ...highlight, starsLabel: highlightStars(highlight.stars) };
    const item = slot.content.cloneNode(true);
    item.querySelectorAll('[data-field]').forEach((node) => {
      const value = values[node.dataset.field];
      node.textContent = node.dataset.format === 'json' ? JSON.stringify(value) : String(value);
    });
    item.querySelectorAll('[data-href]').forEach((link) => { link.href = values[link.dataset.href]; });
    slot.before(item);
  }
  slot.remove();
  dropLastComma(root);
}

async function fetchAiHighlights() {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 2000);
  let live = false;
  try {
    const res = await fetch('https://api.github.com/search/repositories?q=topic:ai+stars:>1000&sort=updated&order=desc&per_page=12', {
      headers: { Accept: 'application/vnd.github.v3+json' }, signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    aiHighlightsPool = items.filter(item => {
      try {
        const url = new URL(item.html_url);
        return url.protocol === 'https:' && url.hostname === 'github.com' && typeof item.full_name === 'string';
      } catch { return false; }
    }).map(item => ({
      name: item.full_name, desc: item.description || '', url: item.html_url,
      stars: Number.isFinite(item.stargazers_count) ? item.stargazers_count : null,
      language: item.language || 'Code',
    }));
    live = aiHighlightsPool.length > 0;
  } catch {
    aiHighlightsPool = [];
  } finally {
    clearTimeout(timeoutId);
  }
  if (!live) aiHighlightsPool = [...PAGE.fallback];
  const status = document.getElementById('ai-highlights-status');
  if (status) status.textContent = live
    ? 'Recently updated AI projects from the public GitHub API.'
    : 'Curated examples — live GitHub data is unavailable.';
  pickRandomAiHighlights();
  renderAiHighlights(PAGE.modes[getCurrentMode()]);
}

function renderPortfolio() {
  const notation = PAGE.modes[getCurrentMode()];
  const profileRoot = document.getElementById('profile-render-root');
  if (profileRoot.dataset.renderer !== notation) mount(profileRoot, 'profile', notation);
  renderProjects(notation);
  renderAiHighlights(notation);
}

function bindControls() {
  const searchInput = document.getElementById('project-search-input');
  const searchClear = document.getElementById('project-search-clear');
  // Keep input entered before the script ran.
  currentSearchQuery = searchInput.value || '';
  searchClear.hidden = !currentSearchQuery;
  searchInput.addEventListener('input', () => {
    currentSearchQuery = searchInput.value;
    searchClear.hidden = !currentSearchQuery;
    renderPortfolio();
  });
  searchClear.addEventListener('click', () => {
    searchInput.value = '';
    currentSearchQuery = '';
    searchClear.hidden = true;
    renderPortfolio();
  });
  document.getElementById('project-tags-filter').addEventListener('click', (event) => {
    const button = event.target.closest('.tag-btn');
    if (button) setTagFilter(button.dataset.tag);
  });
  document.getElementById('projects-render-root').addEventListener('click', (event) => {
    const topic = event.target.closest('.ui-tag[data-topic]');
    const copy = event.target.closest('.project-copy');
    if (topic) setTagFilter(topic.dataset.topic);
    else if (copy) void copyUrl(copy);
  });
  document.addEventListener('ui-chrome-action', (event) => {              // ⚙️ 🧾: the chrome tells the mode picked
    if (event.detail.key !== 'mode') return;
    const nextMode = normalizeViewMode(event.detail.value);
    applyViewMode(nextMode);
    store(VIEW_MODE_KEY, nextMode);
    store(VIEW_MODE_BASE_KEY, configuredViewMode);
  });
  document.getElementById('ai-highlights-refresh').addEventListener('click', () => {
    pickRandomAiHighlights();
    renderAiHighlights(PAGE.modes[getCurrentMode()]);
  });
}

(async () => {
  configuredViewMode = await readConfiguredViewMode();
  const stored = readStored(VIEW_MODE_BASE_KEY) === configuredViewMode ? readStored(VIEW_MODE_KEY) : null;
  bindControls();
  pickRandomAiHighlights();
  applyViewMode(normalizeViewMode(stored || configuredViewMode));
  void fetchAiHighlights();
})();'''
