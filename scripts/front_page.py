"""The portfolio's front page (index.html), built in Python: no index.html, index.js, style.css or renderer.css in the repository.

``document()`` returns the one page that ``scripts/project_pages.py`` writes and locks with the other generated pages.
The page shell, the Tools & Demos cards (``PORTAL``, data), the stylesheet and the page script are all here; the page
script still draws the profile and the projects from profile.json / projects.json / api/repos.json in the browser.
"""
import html

# 🧭 Tools & Demos: one card each. ``points`` are trusted HTML (they carry <code>); everything else is escaped.
PORTAL = [{'title': 'HTML文書取込', 'text': 'HTML貼り付け・ファイル選択から、端末内で本文・見出し・リンクを抽出。', 'links': [('Open HTML Import →', './tools/html-import/')]},
 {'title': 'Ironmate',
  'text': 'ブラウザでスライドを作成し、文字・図形・矢印を編集可能なPPTXへ出力。Image Studio はレイヤー、数値行列のヒートマップ、作業履歴、クリップボード棚、PNG Base64 の受け渡しに対応し、Browser Tools '
          'ではドット絵・比較用の一枚・容量確認ができます。Markdown→PPTX変換と既存PPTXの属性編集はローカルCLIの試作実装です。',
  'id': 'ironmate',
  'links': [('Open Image Studio →', 'https://myon-bioinformatics.github.io/Ironmate/'),
            ('Open Browser Tools →', 'https://myon-bioinformatics.github.io/Ironmate/tools/'),
            ('Open Slide Studio →', 'https://myon-bioinformatics.github.io/Ironmate/slides/')]},
 {'title': 'mcp-toolcall-lab',
  'text': 'Wikipedia表示・Pixiv原文抽出と、ラボの検証結果スナップショット。',
  'id': 'mcp-toolcall-lab',
  'links': [('Open Tool Lab →', './tools/mcp-toolcall-lab/'),
            ('Open Execution Lab →', 'https://myon-bioinformatics.github.io/mcp-toolcall-lab/execution/')]},
 {'title': 'flutter_navigation_basic',
  'text': 'Browser-accessible Flutter utility collection.',
  'links': [('Open Flutter Tools →', 'https://myon-bioinformatics.github.io/flutter_navigation_basic/')]},
 {'title': '🧰 Stubs & mocks',
  'text': '通信しない MCP / API のスタブ、ページ内で動く MCP サーバーのモック、JUnit 結果の読み取り。PySaiyanWeBoo が Python で生成し、このポートフォリオに置いています。',
  'id': 'demos',
  'links': [('Open Demos →', './tools/demos/')]},
 {'title': 'PySaiyanWeBoo',
  'text': 'このポートフォリオのツールページの見た目と表示部品を、ビルド不要の共通UI部品でそろえています。',
  'id': 'web-ui',
  'points': ['見た目の統一：<code>tokens → base → components → themes/modern</code> の CSS 層と <code>ui-*</code> クラス',
             '静的ページ生成：<code>pysaiyanweboo.py</code> の <code>render_document</code>（HTML文書取込をこれで生成）',
             '他リポジトリのページ取り込み：<code>adopt_document</code> で lab 独自クラスを <code>ui-*</code> に置換し、挙動は元のまま',
             '安全な表示：<code>ui.js</code> の <code>setText</code>（textContent のみ）と <code>prettyJson</code>',
             '画面切替と外部リンク：<code>navigation.js</code> の <code>bindViews</code>（Home / Wiki / Pixiv）と <code>openExternalURL</code>',
             '版の固定：<code>requirements-pages.txt</code> で commit を固定し、生成した CSS/JS の SHA-256 を <code>web-ui-assets.lock.json</code> に記録'],
  'links': [('Open UI Catalog →', 'https://myon-bioinformatics.github.io/PySaiyanWeBoo/')]},
 {'title': '📚 Project pages',
  'text': 'GitHub Pages を持たないプロジェクトにも1ページずつ：アイコン、図や GIF、固定したコミットで記録した実行例（Err-o-RoadRunner・search_seq・TalkCompress・BrowserTestKit・NVD、Aoi '
          'の各サブプロジェクト）。',
  'id': 'projects-pages',
  'links': [('Open Project pages →', './tools/projects/')]},
 {'title': '📝 markdown.py',
  'text': '実在のページ（とほほのWWW入門のトップ）を Markdown へ変換し、元の HTML と往復後の HTML を画像で比べるベンチマーク。利用ガイドとリポジトリ診断つき。',
  'id': 'markdown',
  'links': [('Open Benchmark →', 'https://myon-bioinformatics.github.io/markdown/'),
            ('Open Guide →', 'https://myon-bioinformatics.github.io/markdown/guide.html')]},
 {'title': '🧭 統合運用',
  'text': 'リポジトリ横断の運用ダッシュボード：CI の失敗・競合・未解決レビューの優先確認、監査と依存、実行手順、記録と差分。',
  'id': 'operations',
  'links': [('Open Dashboard →', 'https://myon-bioinformatics.github.io/myon-bioinformatics/')]},
 {'title': '📘 利用ガイド',
  'text': '単一ファイル・標準ライブラリ中心の CLI と研究基盤の使い方。',
  'id': 'guides',
  'links': [('Aoi →', 'https://myon-bioinformatics.github.io/Aoi/'),
            ('NagoyAction →', 'https://myon-bioinformatics.github.io/NagoyAction/'),
            ('FluidFullSpeedSimulation →', 'https://myon-bioinformatics.github.io/FluidFullSpeedSimulation/'),
            ('xprobe →', 'https://myon-bioinformatics.github.io/xprobe/'),
            ('gh_identity →', 'https://myon-bioinformatics.github.io/gh_identity/'),
            ('yourself →', 'https://myon-bioinformatics.github.io/yourself/'),
            ('cli_args →', 'https://myon-bioinformatics.github.io/cli_args/'),
            ('ascii_artist →', 'https://myon-bioinformatics.github.io/ascii_artist/')]}]


def portal_cards() -> str:
    out = []
    for card in PORTAL:
        heading = f'<h3 id="{html.escape(card["id"], quote=True)}">' if 'id' in card else '<h3>'
        parts = [heading + html.escape(card['title'], quote=False) + '</h3>', '<p>' + html.escape(card['text'], quote=False) + '</p>']
        if 'points' in card:
            parts.append('<ul class="portal-points">' + ''.join(f'<li>{point}</li>' for point in card['points']) + '</ul>')
        parts += [f'<a href="{html.escape(href, quote=True)}">{html.escape(label, quote=False)}</a>' for label, href in card['links']]
        out.append('        <article class="card portal-card">' + ''.join(parts) + '</article>\n')
    return '      <div class="portal-grid">\n' + ''.join(out)


def document() -> str:
    return SHELL.replace('@@PORTAL@@', portal_cards()).replace('@@STYLE@@', '\n' + STYLE + '\n  ').replace('@@SCRIPT@@', '\n' + SCRIPT + '\n  ')


SHELL = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>myon-bioinformatics — Portfolio</title>
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
      <div class="header-actions">
        <nav class="nav">
          <a href="https://github.com/myon-bioinformatics" target="_blank" rel="noopener noreferrer">GitHub</a>
          <a href="https://lit.link/myon123" target="_blank" rel="noopener noreferrer">lit.link</a>
          <a href="https://linktr.ee/myon123" target="_blank" rel="noopener noreferrer">Linktree</a>
        </nav>
        <div class="view-mode-switch">
          <label for="view-mode-select">Mode</label>
          <select id="view-mode-select" aria-label="Display mode">
            <option value="modern">Modern</option>
            <option value="xml-like">XML-like</option>
            <option value="json">JSON</option>
            <option value="markdown">Markdown</option>
            <option value="github-like">GitHub-like</option>
          </select>
        </div>
      </div>
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
      <p class="section-sub">All public repositories, including archived work. Active projects appear first.</p>
      <div class="projects-controls" id="projects-controls">
        <div class="project-search-wrap">
          <input class="ui-input" type="search" id="project-search-input" placeholder="Search projects by name, description, or topic..." aria-label="Search projects">
          <button type="button" id="project-search-clear" class="btn-clear" hidden aria-label="Clear search">✕</button>
        </div>
        <details class="project-topic-controls">
          <summary>Filter by topic</summary>
          <div class="project-tags-filter" id="project-tags-filter" role="group" aria-label="Filter projects by topic"></div>
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
      <h2>🧭 Tools &amp; Demos</h2>
      <p>Open a project below to use its browser tools.</p>
@@PORTAL@@      </div>
    </section>

    <section class="container outro">
      <h2>📬 Contact</h2>
      <p>Twitter: <a href="https://twitter.com/myonitbusiness" target="_blank" rel="noopener noreferrer">@myonitbusiness</a></p>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container">
      <small>© myon-bioinformatics</small>
    </div>
  </footer>

  <script src="./tools/vendor/web-ui/js/collection.js"></script>
  <script>@@SCRIPT@@</script>
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
.site-header,.site-footer{border-bottom:1px solid var(--border)}
.site-footer{border-top:1px solid var(--border);border-bottom:none}
.site-header .container{display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.site-header h1{display:flex;align-items:center;gap:.75rem;margin:0;max-width:100%;font-size:1.25rem;overflow-wrap:anywhere}
.site-header .brand-icon{display:block;flex:none;width:40px;height:40px}
.header-actions{display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.nav{display:flex;flex-wrap:wrap;gap:8px 12px}
.nav a{text-decoration:none;border-bottom:1px solid transparent}
.nav a:hover{border-bottom-color:currentColor}
.view-mode-switch{display:flex;align-items:center;gap:8px}
.view-mode-switch label{font-size:.85rem;color:var(--muted)}
.view-mode-switch select{
  border:1px solid var(--border);
  border-radius:8px;
  background:var(--bg);
  color:var(--fg);
  padding:4px 8px;
  font:inherit;
}
h2{margin:0 0 .75rem}
.intro,.outro{padding-top:.5rem}

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

/* ── Profile tabs ──────────────────────────────────────────────────────── */
#profile h2 { margin-bottom: 0.75rem; }
.tabs { display: flex; gap: 6px; margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0; }
.tab-btn {
  background: none; border: none; padding: 6px 16px; cursor: pointer;
  font: inherit; color: var(--muted); border-bottom: 2px solid transparent;
  margin-bottom: -1px; transition: color .15s, border-color .15s;
}
.tab-btn:hover { color: var(--fg); }
.tab-btn.active { color: var(--fg); border-bottom-color: currentColor; font-weight: 600; }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

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
  width: 0%;
  transition: width .6s cubic-bezier(.4,0,.2,1);
}

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
body[data-view-mode="modern"] .nav a::before { content: "["; color: var(--terminal-border); }
body[data-view-mode="modern"] .nav a::after { content: "]"; color: var(--terminal-border); }
body[data-view-mode="modern"] .view-mode-switch label { color: var(--terminal-muted); }
body[data-view-mode="modern"] .view-mode-switch select {
  border-radius: 0;
  border-color: var(--terminal-border);
  background: var(--terminal-panel);
  color: var(--terminal-fg);
}
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
body[data-view-mode="modern"] .tabs {
  gap: 0;
  border-color: var(--terminal-border);
  border-style: dashed;
}
body[data-view-mode="modern"] .tab-btn {
  border-right: 1px solid var(--terminal-border);
  border-bottom: 0;
  color: var(--terminal-muted);
}
body[data-view-mode="modern"] .tab-btn::before { content: "[ "; color: var(--terminal-border); }
body[data-view-mode="modern"] .tab-btn::after { content: " ]"; color: var(--terminal-border); }
body[data-view-mode="modern"] .tab-btn.active {
  color: var(--terminal-fg);
  background: rgba(126,231,135,.08);
}
body[data-view-mode="modern"] .tab-btn.active::before { content: "[> "; color: var(--terminal-accent); }
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
body[data-view-mode="xml-like"] .tab-panel,
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
body[data-view-mode="json"] .card,
body[data-view-mode="json"] .tab-panel {
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
body[data-view-mode="markdown"] .card,
body[data-view-mode="markdown"] .tab-panel {
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
body[data-view-mode="github-like"] .tab-panel,
body[data-view-mode="github-like"] .view-mode-switch select {
  background: #ffffff;
}
body[data-view-mode="github-like"] .site-header,
body[data-view-mode="github-like"] .site-footer,
body[data-view-mode="github-like"] .card,
body[data-view-mode="github-like"] .tab-panel,
body[data-view-mode="github-like"] .view-mode-switch select,
body[data-view-mode="github-like"] .tabs {
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
  .skill-bar-fill { transition: none; }
  .card:hover { transform: none; }
}

@media (max-width: 720px) {
  .container { padding: 1.25rem; }
  body[data-view-mode="json"] .container { padding-left: 1rem; }
  .site-header .container,
  .header-actions { align-items: flex-start; }
  .header-actions {
    width: 100%;
    flex-direction: column;
    gap: 12px;
  }
  .nav { width: 100%; }
  .view-mode-switch {
    width: 100%;
    justify-content: space-between;
  }
  .view-mode-switch select {
    width: min(100%, 220px);
    min-width: 0;
  }
  .grid {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }
  .tabs { flex-wrap: wrap; }
  .tab-btn { padding: 10px 14px; }
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
  .view-mode-switch {
    align-items: stretch;
    flex-direction: column;
    gap: 6px;
  }
  .view-mode-switch select { width: 100%; }
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
.project-card-actions { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: .5rem; margin-top: .75rem; }
.project-copy { cursor: pointer; font-size: .8rem; }
.project-copy.copied { background: var(--ui-accent); color: var(--ui-bg); }
#projects-render-root { overflow-wrap: anywhere; }
.project-topic-controls summary { cursor: pointer; margin: .75rem 0; }
.project-topic-controls .project-tags-filter { max-height: 12rem; overflow-y: auto; padding: .25rem; }
.project-status { margin-bottom: .5rem; font-size: .8rem; }

/* ── Tools & Demos portal ──────────────────────────────────────────────── */
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
.portal-points {
  margin: 0 0 12px;
  padding-left: 1.2em;
  font-size: 0.9em;
  overflow-wrap: anywhere;
}
.portal-points li + li { margin-top: 4px; }

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
}'''

SCRIPT = r'''const DEFAULT_VIEW_MODE = 'modern';
const VIEW_MODE_KEY = 'site:view-mode';
const VIEW_MODE_BASE_KEY = 'site:view-mode-base';
const VALID_VIEW_MODES = new Set(['modern', 'xml-like', 'json', 'markdown', 'github-like']);

let sharedData = null;
let configuredViewMode = DEFAULT_VIEW_MODE;
let currentTagFilter = 'all';
let currentSearchQuery = '';
let controlsInitialized = false;

function normalizeViewMode(mode) {
  return VALID_VIEW_MODES.has(mode) ? mode : DEFAULT_VIEW_MODE;
}

function readStoredViewMode(configuredMode) {
  try {
    const base = localStorage.getItem(VIEW_MODE_BASE_KEY);
    if (base !== configuredMode) return null;
    return localStorage.getItem(VIEW_MODE_KEY);
  } catch {
    return null;
  }
}

function saveViewMode(mode, configuredMode) {
  try {
    localStorage.setItem(VIEW_MODE_KEY, mode);
    localStorage.setItem(VIEW_MODE_BASE_KEY, configuredMode);
  } catch {
    // ignore storage failures
  }
}

function clearElement(element) {
  if (element) element.replaceChildren();
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function externalLink(url, text = url) {
  const link = element('a', null, text);
  link.href = url;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  return link;
}

function getCurrentMode() {
  return normalizeViewMode(document.body.dataset.viewMode || configuredViewMode);
}

function applyViewMode(mode) {
  const normalized = normalizeViewMode(mode);
  document.body.dataset.viewMode = normalized;
  document.body.dataset.uiTheme = normalized === 'modern' ? 'modern' : normalized === 'github-like' ? 'github-like' : 'plain';
  const selector = document.getElementById('view-mode-select');
  if (selector && selector.value !== normalized) selector.value = normalized;
  if (sharedData) renderPortfolio(normalized, sharedData);
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

function initViewModeSelector(initialMode, configuredMode) {
  const selector = document.getElementById('view-mode-select');
  applyViewMode(initialMode);
  if (!selector) return;

  selector.addEventListener('change', () => {
    const nextMode = normalizeViewMode(selector.value);
    applyViewMode(nextMode);
    saveViewMode(nextMode, configuredMode);
  });
}

function shuffleItems(items) {
  const shuffled = [...items];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  return shuffled;
}

// Public, non-archived repositories only. The full candidate pool is collected
// first, then shuffled so each page load shows a fresh order.
function buildProjectCatalog(catalog, curated) {
  if (!Array.isArray(catalog?.repos)) throw new Error('Invalid repository catalog');
  const overrides = new Map(curated.map((project) => [project.name, project]));
  const candidates = catalog.repos
    .filter((repo) => repo.archived !== true)
    .map((repo) => {
      const project = overrides.get(repo.name);
      return {
        name: repo.name,
        desc: project?.desc || repo.description || repo.readmeSummary || 'Explore the source and README on GitHub.',
        url: repo.url,
        topics: [...new Set([...(project?.topics || []), ...(repo.topics || [])])],
        archived: false,
      };
    });
  return shuffleItems(candidates);
}

async function loadSharedData() {
  const [profileRes, catalogRes, curated] = await Promise.all([
    fetch('./profile.json', { cache: 'no-store' }),
    fetch('./api/repos.json', { cache: 'no-store' }),
    fetch('./projects.json', { cache: 'no-store' })
      .then((res) => res.ok ? res.json() : [])
      .catch(() => []),
  ]);

  if (!profileRes.ok) throw new Error(`profile.json HTTP ${profileRes.status}`);
  if (!catalogRes.ok) throw new Error(`api/repos.json HTTP ${catalogRes.status}`);

  const [profile, catalog] = await Promise.all([profileRes.json(), catalogRes.json()]);
  return { profile, projects: buildProjectCatalog(catalog, Array.isArray(curated) ? curated : []) };
}

function renderWebProfile(root, profile) {
  root.dataset.renderer = 'web';

  const tabs = element('div', 'tabs');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-label', 'Profile sections');

  const panelWrap = element('div', 'profile-panels');
  const sections = [
    ['about', 'About'],
    ['skills', 'Skills'],
    ['career', 'Career'],
  ];
  const panels = {};
  let skillsAnimated = false;

  function activateTab(key) {
    tabs.querySelectorAll('.tab-btn').forEach((button) => {
      const active = button.id === `tab-${key}`;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
    Object.entries(panels).forEach(([panelKey, panel]) => {
      const active = panelKey === key;
      panel.classList.toggle('active', active);
      panel.hidden = !active;
    });

    if (key === 'skills' && !skillsAnimated) {
      skillsAnimated = true;
      requestAnimationFrame(() => {
        panels.skills.querySelectorAll('.skill-bar-fill').forEach((bar) => {
          bar.style.width = `${bar.dataset.level}%`;
        });
      });
    }
  }

  sections.forEach(([key, label], index) => {
    const button = element('button', `tab-btn${index === 0 ? ' active' : ''}`, label);
    button.type = 'button';
    button.id = `tab-${key}`;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-selected', String(index === 0));
    button.setAttribute('aria-controls', `panel-${key}`);
    button.addEventListener('click', () => activateTab(key));
    tabs.appendChild(button);

    const panel = element('div', `tab-panel${index === 0 ? ' active' : ''}`);
    panel.id = `panel-${key}`;
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', `tab-${key}`);
    panel.hidden = index !== 0;
    panels[key] = panel;
    panelWrap.appendChild(panel);
  });

  panels.about.appendChild(element('p', 'about-text', profile.about));

  profile.skills.forEach(({ category, items }) => {
    const group = element('div', 'skill-group');
    group.appendChild(element('h4', 'skill-category', category));

    items.forEach(({ name, level }) => {
      const row = element('div', 'skill-row');
      row.appendChild(element('span', 'skill-label', name));

      const track = element('div', 'skill-bar-track');
      const fill = element('div', 'skill-bar-fill');
      fill.dataset.level = level;
      fill.style.width = '0%';
      track.appendChild(fill);
      row.appendChild(track);
      group.appendChild(row);
    });

    panels.skills.appendChild(group);
  });

  const timeline = element('ol', 'timeline');
  profile.career.forEach(({ year, title, desc }) => {
    const item = element('li', 'timeline-item');
    item.appendChild(element('span', 'tl-year', year));

    const body = element('div', 'tl-body');
    body.appendChild(element('strong', null, title));
    body.appendChild(element('p', null, desc));
    item.appendChild(body);
    timeline.appendChild(item);
  });
  panels.career.appendChild(timeline);

  root.appendChild(tabs);
  root.appendChild(panelWrap);
}

function renderWebProjects(root, projects) {
  root.dataset.renderer = 'web';
  root.className = 'ui-grid';

  if (!projects || projects.length === 0) {
    const emptyMsg = element('div', 'empty-projects-msg', 'No projects match your filter.');
    root.appendChild(emptyMsg);
    return;
  }

  projects.forEach(({ name, desc, url, topics = [], archived }) => {
    const card = element('article', 'ui-card');
    const title = element('h3', 'ui-title');
    title.appendChild(externalLink(url, name));
    card.appendChild(title);
    if (archived) card.appendChild(element('span', 'ui-tag project-status', 'Archived'));
    card.appendChild(element('p', 'ui-muted', desc || ''));

    const badges = element('div', 'project-topics');
    topics.slice(0, 6).forEach((topic) => {
      const tagSpan = element('span', 'ui-tag', topic);
      tagSpan.dataset.topic = topic;
      tagSpan.style.cursor = 'pointer';
      tagSpan.title = `Filter by ${topic}`;
      tagSpan.addEventListener('click', (e) => {
        e.stopPropagation();
        setTagFilter(topic);
      });
      badges.appendChild(tagSpan);
    });
    card.appendChild(badges);

    const footer = element('div', 'project-card-actions');
    const shields = element('img');
    shields.loading = 'lazy';
    shields.alt = 'GitHub stars';
    shields.src = `https://img.shields.io/github/stars/myon-bioinformatics/${encodeURIComponent(name)}?style=social`;
    footer.appendChild(shields);

    const copyBtn = element('button', 'ui-button project-copy', 'Copy URL');
    copyBtn.type = 'button';
    copyBtn.setAttribute('aria-label', `Copy repository URL for ${name}`);
    copyBtn.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(url);
        } else {
          const textarea = document.createElement('textarea');
          textarea.value = url;
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand('copy');
          document.body.removeChild(textarea);
        }
        copyBtn.textContent = 'Copied!';
        copyBtn.classList.add('copied');
        setTimeout(() => {
          copyBtn.textContent = 'Copy URL';
          copyBtn.classList.remove('copied');
        }, 1500);
      } catch (err) {
        console.error('Copy failed:', err);
      }
    });
    footer.appendChild(copyBtn);

    card.appendChild(footer);
    root.appendChild(card);
  });
}

function xmlLine(parent, indent, parts) {
  const line = element('div', 'xml-line');
  line.style.setProperty('--indent', indent);
  parts.forEach((part) => {
    if (part instanceof Node) line.appendChild(part);
    else line.appendChild(document.createTextNode(part));
  });
  parent.appendChild(line);
}

function xmlTag(text, kind = 'tag') {
  return element('span', `xml-${kind}`, text);
}

function renderXmlProfile(root, profile) {
  root.dataset.renderer = 'xml';
  root.className = 'notation-root xml-renderer';
  xmlLine(root, 0, [xmlTag('<Profile>')]);
  xmlLine(root, 1, [xmlTag('<About>'), document.createTextNode(profile.about), xmlTag('</About>')]);
  xmlLine(root, 1, [xmlTag('<Skills>')]);
  profile.skills.forEach(({ category, items }) => {
    xmlLine(root, 2, [xmlTag(`<SkillGroup category="${category}">`)]);
    items.forEach(({ name, level }) => {
      xmlLine(root, 3, [xmlTag(`<Skill name="${name}" level="${level}" />`)]);
    });
    xmlLine(root, 2, [xmlTag('</SkillGroup>')]);
  });
  xmlLine(root, 1, [xmlTag('</Skills>')]);
  xmlLine(root, 1, [xmlTag('<Career>')]);
  profile.career.forEach(({ year, title, desc }) => {
    xmlLine(root, 2, [xmlTag(`<Entry year="${year}">`)]);
    xmlLine(root, 3, [xmlTag('<Title>'), title, xmlTag('</Title>')]);
    xmlLine(root, 3, [xmlTag('<Description>'), desc, xmlTag('</Description>')]);
    xmlLine(root, 2, [xmlTag('</Entry>')]);
  });
  xmlLine(root, 1, [xmlTag('</Career>')]);
  xmlLine(root, 0, [xmlTag('</Profile>')]);
}

function renderXmlProjects(root, projects) {
  root.dataset.renderer = 'xml';
  root.className = 'notation-root xml-renderer';
  xmlLine(root, 0, [xmlTag('<Projects>')]);
  if (!projects || projects.length === 0) {
    xmlLine(root, 1, [document.createTextNode('<!-- No projects match your filter -->')]);
  } else {
    projects.forEach(({ name, desc, url, topics = [], archived }) => {
      xmlLine(root, 1, [xmlTag(`<Project name="${name}">`)]);
      if (archived) xmlLine(root, 2, [xmlTag('<Status>'), 'Archived', xmlTag('</Status>')]);
      xmlLine(root, 2, [xmlTag('<Description>'), desc || '', xmlTag('</Description>')]);
      const urlLink = externalLink(url, url);
      xmlLine(root, 2, [xmlTag('<Url>'), urlLink, xmlTag('</Url>')]);
      xmlLine(root, 2, [xmlTag('<Topics>')]);
      topics.forEach((topic) => xmlLine(root, 3, [xmlTag('<Topic>'), topic, xmlTag('</Topic>')]));
      xmlLine(root, 2, [xmlTag('</Topics>')]);
      xmlLine(root, 1, [xmlTag('</Project>')]);
    });
  }
  xmlLine(root, 0, [xmlTag('</Projects>')]);
}

function appendJsonValue(parent, value, indent = 0, key = null, trailingComma = false) {
  const line = element('div', 'json-line');
  line.style.setProperty('--indent', indent);
  if (key !== null) {
    line.appendChild(element('span', 'json-key', `"${key}"`));
    line.appendChild(document.createTextNode(': '));
  }

  if (Array.isArray(value)) {
    line.appendChild(element('span', 'json-punctuation', '['));
    parent.appendChild(line);
    value.forEach((item, index) => appendJsonValue(parent, item, indent + 1, null, index < value.length - 1));
    const close = element('div', 'json-line');
    close.style.setProperty('--indent', indent);
    close.appendChild(element('span', 'json-punctuation', `]${trailingComma ? ',' : ''}`));
    parent.appendChild(close);
    return;
  }

  if (value && typeof value === 'object') {
    line.appendChild(element('span', 'json-punctuation', '{'));
    parent.appendChild(line);
    const entries = Object.entries(value);
    entries.forEach(([childKey, childValue], index) => {
      appendJsonValue(parent, childValue, indent + 1, childKey, index < entries.length - 1);
    });
    const close = element('div', 'json-line');
    close.style.setProperty('--indent', indent);
    close.appendChild(element('span', 'json-punctuation', `}${trailingComma ? ',' : ''}`));
    parent.appendChild(close);
    return;
  }

  if (typeof value === 'string') {
    if (/^https?:\/\//.test(value)) {
      line.appendChild(document.createTextNode('"'));
      line.appendChild(externalLink(value, value));
      line.appendChild(document.createTextNode('"'));
    } else {
      line.appendChild(element('span', 'json-string', JSON.stringify(value)));
    }
  } else {
    line.appendChild(element('span', 'json-number', String(value)));
  }
  if (trailingComma) line.appendChild(element('span', 'json-punctuation', ','));
  parent.appendChild(line);
}

function renderJsonProfile(root, profile) {
  root.dataset.renderer = 'json';
  root.className = 'notation-root json-renderer';
  appendJsonValue(root, profile);
}

function renderJsonProjects(root, projects) {
  root.dataset.renderer = 'json';
  root.className = 'notation-root json-renderer';
  appendJsonValue(root, projects);
}

function renderMarkdownProfile(root, profile) {
  root.dataset.renderer = 'markdown';
  root.className = 'notation-root markdown-renderer';

  root.appendChild(element('h3', 'md-heading', '### About'));
  root.appendChild(element('p', 'about-text', profile.about));

  root.appendChild(element('h3', 'md-heading', '### Skills'));
  profile.skills.forEach(({ category, items }) => {
    root.appendChild(element('h4', 'md-heading', `#### ${category}`));
    const list = element('ul', 'md-list');
    items.forEach(({ name, level }) => list.appendChild(element('li', null, `${name} — ${level}%`)));
    root.appendChild(list);
  });

  root.appendChild(element('h3', 'md-heading', '### Career'));
  const career = element('ul', 'md-list');
  profile.career.forEach(({ year, title, desc }) => {
    const item = element('li');
    const strong = element('strong', null, `${year} — ${title}`);
    item.appendChild(strong);
    item.appendChild(document.createTextNode(`: ${desc}`));
    career.appendChild(item);
  });
  root.appendChild(career);
}

function renderMarkdownProjects(root, projects) {
  root.dataset.renderer = 'markdown';
  root.className = 'notation-root markdown-renderer';

  if (!projects || projects.length === 0) {
    root.appendChild(element('p', null, 'No projects match your filter.'));
    return;
  }

  projects.forEach(({ name, desc, url, topics = [], archived }) => {
    const heading = element('h3', 'md-heading');
    heading.appendChild(document.createTextNode('### '));
    heading.appendChild(externalLink(url, name));
    root.appendChild(heading);
    root.appendChild(element('p', null, desc || ''));
    const list = element('ul', 'md-list');
    if (archived) list.appendChild(element('li', null, 'Status: Archived'));
    list.appendChild(element('li', null, `Topics: ${topics.join(', ')}`));
    const sourceItem = element('li');
    sourceItem.appendChild(document.createTextNode('Source: '));
    sourceItem.appendChild(externalLink(url, url));
    list.appendChild(sourceItem);
    root.appendChild(list);
  });
}

const PROFILE_RENDERERS = {
  modern: renderWebProfile,
  'github-like': renderWebProfile,
  'xml-like': renderXmlProfile,
  json: renderJsonProfile,
  markdown: renderMarkdownProfile,
};

const PROJECT_RENDERERS = {
  modern: renderWebProjects,
  'github-like': renderWebProjects,
  'xml-like': renderXmlProjects,
  json: renderJsonProjects,
  markdown: renderMarkdownProjects,
};

function getFilteredProjects(projects) {
  if (!Array.isArray(projects)) return [];
  const facets = {};
  if (currentTagFilter !== 'all') facets.topic = currentTagFilter;
  return WebUICollections.filterItems(projects, {
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

function setTagFilter(tag) {
  currentTagFilter = tag;
  const tagBtns = document.querySelectorAll('#project-tags-filter .tag-btn');
  tagBtns.forEach((btn) => {
    const active = btn.dataset.tag === tag;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
  if (sharedData) {
    renderPortfolio(getCurrentMode(), sharedData);
  }
}

function initProjectControls(projects) {
  if (controlsInitialized || !projects) return;
  controlsInitialized = true;

  const searchInput = document.getElementById('project-search-input');
  const searchClear = document.getElementById('project-search-clear');
  const tagsContainer = document.getElementById('project-tags-filter');
  // Keep input entered while the catalog was still loading.
  currentSearchQuery = searchInput?.value || '';
  if (searchClear) searchClear.hidden = !currentSearchQuery;

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      currentSearchQuery = searchInput.value;
      if (searchClear) searchClear.hidden = !currentSearchQuery;
      if (sharedData) {
        renderPortfolio(getCurrentMode(), sharedData);
      }
    });
  }

  if (searchClear) {
    searchClear.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      currentSearchQuery = '';
      searchClear.hidden = true;
      if (sharedData) {
        renderPortfolio(getCurrentMode(), sharedData);
      }
    });
  }

  if (tagsContainer) {
    const uniqueTopics = Array.from(new Set(projects.flatMap((p) => p.topics || []))).sort();
    const allTags = ['all', ...uniqueTopics];

    allTags.forEach((tag) => {
      const label = tag === 'all' ? 'All' : tag;
      const btn = element('button', `tag-btn${tag === currentTagFilter ? ' active' : ''}`, label);
      btn.type = 'button';
      btn.dataset.tag = tag;
      btn.setAttribute('aria-pressed', String(tag === currentTagFilter));
      btn.addEventListener('click', () => setTagFilter(tag));
      tagsContainer.appendChild(btn);
    });
  }
}

let aiHighlightsPool = [];
let displayedAiHighlights = [];

const FALLBACK_AI_HIGHLIGHTS = [
  {
    name: 'ollama/ollama',
    desc: 'Get up and running with Llama 3.3, DeepSeek-R1, Gemma 2, and other large language models.',
    url: 'https://github.com/ollama/ollama',
    stars: null,
    language: 'Go',
  },
  {
    name: 'vllm-project/vllm',
    desc: 'A high-throughput and memory-efficient inference and serving engine for LLMs.',
    url: 'https://github.com/vllm-project/vllm',
    stars: null,
    language: 'Python',
  },
  {
    name: 'langchain-ai/langchain',
    desc: 'Building applications with LLMs through composability.',
    url: 'https://github.com/langchain-ai/langchain',
    stars: null,
    language: 'Python',
  },
  {
    name: 'huggingface/transformers',
    desc: 'State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.',
    url: 'https://github.com/huggingface/transformers',
    stars: null,
    language: 'Python',
  },
];

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
  if (!live) aiHighlightsPool = [...FALLBACK_AI_HIGHLIGHTS];
  const status = document.getElementById('ai-highlights-status');
  if (status) status.textContent = live
    ? 'Recently updated AI projects from the public GitHub API.'
    : 'Curated examples — live GitHub data is unavailable.';
  pickRandomAiHighlights();
  renderAiHighlights(getCurrentMode());
}

function highlightStars(stars) {
  return stars == null ? 'Curated example' : `★ ${stars.toLocaleString()} stars`;
}

function pickRandomAiHighlights(count = 3) {
  if (!aiHighlightsPool || aiHighlightsPool.length === 0) {
    aiHighlightsPool = [...FALLBACK_AI_HIGHLIGHTS];
  }
  const shuffled = [...aiHighlightsPool];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  displayedAiHighlights = shuffled.slice(0, Math.min(count, shuffled.length));
}

function renderAiHighlights(mode) {
  const root = document.getElementById('ai-highlights-render-root');
  if (!root) return;
  clearElement(root);

  if (mode === 'xml-like') {
    root.dataset.renderer = 'xml';
    root.className = 'notation-root xml-renderer';
    xmlLine(root, 0, [xmlTag('<AiHighlights>')]);
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      xmlLine(root, 1, [xmlTag(`<Highlight name="${name}" stars="${stars}" language="${language}">`)]);
      xmlLine(root, 2, [xmlTag('<Description>'), desc, xmlTag('</Description>')]);
      xmlLine(root, 2, [xmlTag('<Url>'), externalLink(url, url), xmlTag('</Url>')]);
      xmlLine(root, 1, [xmlTag('</Highlight>')]);
    });
    xmlLine(root, 0, [xmlTag('</AiHighlights>')]);
  } else if (mode === 'json') {
    root.dataset.renderer = 'json';
    root.className = 'notation-root json-renderer';
    appendJsonValue(root, displayedAiHighlights);
  } else if (mode === 'markdown') {
    root.dataset.renderer = 'markdown';
    root.className = 'notation-root markdown-renderer';
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      const heading = element('h3', 'md-heading');
      heading.appendChild(document.createTextNode('### '));
      heading.appendChild(externalLink(url, name));
      root.appendChild(heading);
      root.appendChild(element('p', null, desc));
      const list = element('ul', 'md-list');
      list.appendChild(element('li', null, `${highlightStars(stars)} • ${language}`));
      root.appendChild(list);
    });
  } else {
    root.dataset.renderer = 'web';
    root.className = 'grid';
    displayedAiHighlights.forEach(({ name, desc, url, stars, language }) => {
      const card = element('article', 'card ai-card');
      const title = element('h3');
      title.appendChild(externalLink(url, name));
      card.appendChild(title);
      card.appendChild(element('p', null, desc));

      const meta = element('div', 'ai-meta');
      const starTag = element('span', 'tag', highlightStars(stars));
      const langTag = element('span', 'tag', language);
      meta.appendChild(starTag);
      meta.appendChild(langTag);
      card.appendChild(meta);

      root.appendChild(card);
    });
  }
}

function renderPortfolio(mode, data) {
  const profileRoot = document.getElementById('profile-render-root');
  const projectsRoot = document.getElementById('projects-render-root');
  if (!profileRoot || !projectsRoot) return;

  clearElement(profileRoot);
  clearElement(projectsRoot);
  profileRoot.className = '';
  projectsRoot.className = '';

  PROFILE_RENDERERS[mode](profileRoot, data.profile);

  const filteredProjects = getFilteredProjects(data.projects);
  updateProjectsCount(filteredProjects.length, data.projects.length);
  PROJECT_RENDERERS[mode](projectsRoot, filteredProjects);

  renderAiHighlights(mode);
}

function renderLoadError(error) {
  const profileRoot = document.getElementById('profile-render-root');
  const projectsRoot = document.getElementById('projects-render-root');
  if (profileRoot) profileRoot.textContent = 'Failed to load profile.';
  if (projectsRoot) projectsRoot.textContent = 'Failed to load projects. Please refresh.';
  console.error(error);
}

(async () => {
  configuredViewMode = await readConfiguredViewMode();
  const selectedMode = normalizeViewMode(readStoredViewMode(configuredViewMode) || configuredViewMode);
  initViewModeSelector(selectedMode, configuredViewMode);

  const refreshBtn = document.getElementById('ai-highlights-refresh');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => {
      pickRandomAiHighlights();
      renderAiHighlights(getCurrentMode());
    });
  }

  try {
    sharedData = await loadSharedData();
    initProjectControls(sharedData.projects);
    pickRandomAiHighlights();
    renderPortfolio(getCurrentMode(), sharedData);
    void fetchAiHighlights();
  } catch (error) {
    renderLoadError(error);
  }
})();'''
