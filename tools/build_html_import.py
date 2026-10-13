"""Generate the static tool with the exact-pinned web-ui wrapper. No visitor input."""
from pathlib import Path
import importlib.util
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('web_ui', ROOT / 'tools/vendor/web-ui/web_ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)
BODY = '''<main class="ui-page">
<a href="../../index.html#tools">← Tools &amp; Demos</a>
<h1>📄 HTML文書取込</h1>
<p>貼り付けたHTMLやローカルファイルから本文・見出し・リンクを取り出します。入力と結果はこのページのメモリ内で処理し、運営者へ自動送信・保存しません。HTML内のスクリプトや画像は実行・取得しません。</p>
<section class="ui-panel" aria-labelledby="input-title"><h2 id="input-title">1. 取り込む</h2>
<label for="source-url">取得元URL（絶対HTTP(S)、相対リンクの基準）</label>
<input class="ui-input" id="source-url" type="url" placeholder="https://example.org/page" autocomplete="off">
<p>URLは出典の申告です。このツールはアクセスしません。元URLが不明な場合は明示した仮のURLを使用してください。ダウンロード済みの証明にはなりません。</p>
<label for="html-input">HTMLを貼り付ける</label><textarea class="ui-input" id="html-input" rows="8" spellcheck="false" placeholder="&lt;article&gt;&lt;h1&gt;見出し&lt;/h1&gt;&lt;p&gt;本文&lt;/p&gt;&lt;/article&gt;"></textarea>
<button class="ui-button" id="paste-load" type="button">貼り付けを取り込む</button>
<label for="file-input">またはHTMLファイルを選択（UTF-8、2 MiBまで）</label>
<input class="ui-input" id="file-input" type="file" accept=".html,.htm,text/html">
</section>
<section class="ui-panel" aria-labelledby="options-title"><h2 id="options-title">2. 抽出条件</h2>
<label for="profile">抽出プロファイル</label><select class="ui-input" id="profile"><option value="generic">一般（article → main → 文書全体）</option><option value="github-readme">GitHub README（article.markdown-bodyが1件）</option></select>
<label for="selector">一般プロファイルのセレクター（任意）</label><input class="ui-input" id="selector" placeholder="main > article.note" autocomplete="off">
<p>対応：タグ、#id、.class、子孫、&gt;、:root。CSS・外部参照は読み込みません。条件変更は取込済みデータを使い、ファイルを再読込しません。</p>
<button class="ui-button" id="apply" type="button">条件を適用</button> <button class="ui-button" id="clear" type="button">入力と結果を消去</button>
</section>
<p id="status" role="status" aria-live="polite">まず取得元URLとHTMLを指定してください。</p>
<section class="ui-panel"><h2>3. 結果</h2><button class="ui-button" id="download" type="button" disabled>結果JSONをダウンロード</button>
<h3>取得元・取込方法</h3><pre class="ui-output" id="provenance"></pre>
<h3>本文</h3><pre class="ui-output" id="body-result"></pre>
<h3>見出し</h3><pre class="ui-output" id="headings-result"></pre>
<h3>リンク（表示のみ、追跡しません）</h3><pre class="ui-output" id="links-result"></pre></section>
<details class="ui-panel"><summary>対応範囲と制約</summary>
<p>通常のHTML文書・整形式のarticle/main、見出しh1〜h6、HTTP(S)リンクを対象にします。script/style/template/noscriptの内容は除外します。HTMLのbase要素は無視します。隠された文字もCSSで判定せず、空白は正規化します。</p>
<p>ブラウザはHTML5として木構造を補正します。省略・不正なタグ、tableの補正、重複属性、SVG/MathML、特殊な文字参照、URLの正規化ではPythonと差が出る場合があります。Python/JS一致は共有fixtureで確認した範囲です。完全なCSS、計算済みスタイル、PDF、JS生成ページ、外部ファイルの取得、文字コード自動判定は未対応です。</p>
<p>JSONはhtml-snapshot/1のメタデータと抽出結果を含み、元HTML本文は含みません。fetched_atとresponse_sha256はnullです。入力はページを離れると失われます。保存は利用者がダウンロードを選んだ場合のみです。<a href="../../docs/html-import.md">抽出契約と検証方法</a></p></details>
</main>'''
CSS = 'label{display:block;margin:1rem 0 .3rem}input,textarea,select{width:100%;max-width:100%}button{margin:.3rem 0;min-height:44px}pre{overflow-wrap:anywhere}h1{font-size:1.8rem}'
def generate():
    document = ui.render_document(title='HTML文書取込', trusted_html=BODY, css=CSS,
        stylesheets=ui.shared_stylesheets('../vendor/web-ui'), scripts=('./app.mjs',))
    csp = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'none'; connect-src 'none'; frame-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    return document.replace('<head>', '<head><meta http-equiv="Content-Security-Policy" content="'+csp+'">', 1).replace('<html lang="en">','<html lang="ja">')
if __name__ == '__main__':
    (ROOT / 'tools/html-import/index.html').write_text(generate(), encoding='utf-8')
