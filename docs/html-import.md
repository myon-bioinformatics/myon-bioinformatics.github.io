# HTML文書取込 — Issue #32の最初の実機能

`/tools/html-import/` はブラウザだけで動く。ポートフォリオの他ツールは変更しない。
PythonサーバーはPagesの実行基盤ではなく、生成・検証に限る。

## 再利用と所有

- lab PR #110の `html-snapshot/1` / `html_snapshot.extract` を参照。
  Python基準実装はlab main `56982948ba79c070664cf9efe87a3d753e417acf` からコピー。
  最新契約には複数articleと小さいselector集合も含まれる。
- web-ui main `6be1196bc30458b0dc92fa5515aa8c4a494b65f8` の `web_ui.py` が静的ページを生成。
  web-ui PR #49の共通導線・表示適用を含む固定版（未マージ時でもcommitは固定）。
  同repoの `ui.js` の文字列表示・JSON整形とCSSを実利用する。
- `tools/html-import/vendor.lock.json` に完全commit、元パス、SHA-256、ライセンスを記録。
  実行時CDN、外部フレームワーク、Python/WASM配信は不要。
- ブラウザに必要なparser/selectorの伴走実装は `extract.mjs`。現状のweb-uiには
  HTML読取モジュールがないため、UIの表示部品とPython生成基盤を再利用する。
  labのAPI adapterや抽出契約の所有はlabに残す。

## 入出力と再利用

1. 利用者が取得元の絶対HTTP(S) URLを申告して、HTML貼付またはファイル選択。
   URLへアクセスしない。UTF-8 strict decode、2 MiB、最大128階層。
2. 一度だけ読み取り、ブラウザの不活性templateで木構造を構築しメモリ内に保持。
   読取順が前後しても最新操作のみ反映する。
3. 一般 / GitHub README / selectorを同じ木に適用。URL欄や貼付欄を変更しただけでは
   スナップショットは変わらず、明示的な再取込が必要。
4. 本文、見出し、HTTP(S)リンク、申告取得元、取込方法・ファイル名を文字列表示。
   結果JSONを利用者自身がダウンロードできる。エラー時は古い結果を消して保存不可にする。
5. 消去ボタンでデータ・ファイル選択・結果を解放。永続storageや運営者への送信なし。

JSONのsnapshotは `html-snapshot/1` と同じメタデータキーを使う。
`content_sha256` は復号後UTF-8本文のハッシュ。`fetched_at` と `response_sha256` はnull。
**ネット取得・真正性の証明ではない。** 結果downloadは本文HTMLを含まないメタデータ投影であり、
labへそのまま再入力できる完全なsnapshotではない。ファイル名も結果に含むので保存前に確認できる。

## 一致範囲

`generic` は全outermost article、なければmain、なければ文書全体。
`github-readme` は `article.markdown-body` がちょうど1件。空本文・未一致・曖昧な選択はエラー。
selectorはタグ、`*`、`#id`、`.class`、子孫、`>`、`:root`の小集合で、属性・疑似クラス・カンマ等は拒否。
`script/style/template/noscript` の内容は除外。リンクは指定URLで解決し、HTML baseは無視。
CSSの非表示は判定せず、空白を正規化する。リンク・stylesheet参照を取得しない。

共有合成fixture `tests/fixtures/html-import/cases.json` の本文、見出し、URL、scope、title、structure、
stylesheet参照をPython/Chromium/WebKitで比較する。期待値は版固定してdiffでレビュー可能とし、
重要な本文・複数scope・リンク除外の期待値には独立した明示assertも置く。
PythonはHTMLParser、ブラウザはHTML5補正なので**任意HTMLでの同一結果は保証しない**。
ブラウザのtag_countsは公開しない（html/head/bodyや補正ノードの数は比較契約外）。

未保証・未対応：省略/不正なタグ、tableの補正、重複属性、SVG/MathML、特殊な文字参照、
URLのpercent encodeやUnicodeホストなどの正規化差、CSS評価、include_css、JS生成コンテンツ、
PDF、外部アクセス、文字コードの自動判定。通常の保存HTMLを読むが、Python一致はfixture範囲に限る。

## 安全性

入力のDOMノードをlive文書へ挿入しない。表示はweb-ui `setText` によるtextContentのみ。
CSPはconnect/img/frame/objectを禁止し、実行scriptは同梱モジュールだけ。
入力に含まれるscript、onerror、iframe、stylesheet、CSS importを含む攻撃fixtureで
実行なし・取込後の通信なし・local/session storageなしをブラウザ検証する。
結果のリンクもクリック可能な要素に変換しない。
サイト配信自体のアクセスログまで保存なしとは主張しない。

## Docker、CI、公開後検証

```sh
docker build -f Dockerfile.html-import -t html-import-test .
docker run --rm --ipc=host html-import-test
# 公開後のみ（mainでデプロイ済みの機能を確認）
docker run --rm --ipc=host -e HTML_TOOL_BASE_URL=https://myon-bioinformatics.github.io \
  html-import-test npx playwright test --config playwright.html-import.config.js
```

Dockerはビルド・pytest・Playwrightの共通環境。Pagesに配布しない。
Node baseは22-bookworm、JS test依存はpackage-lock、pytestは8.4.2。
画像digest/apt依存までのbit-for-bit固定は主張しない。
CIはDockerをbuildしてからPython共有fixtureと既存portal/lab検証、
Chromium/WebKit各々のdesktop/mobile貼付・ファイル・条件変更・JSON取得を実行。
JUnitとscreenshotsをartifactとして残す。合成ケースのみで実利用者データを保存しない。

既存Pages workflowは変更しない。公開後はその成功を契機に別workflowが同じ実入力・結果取得を
公開URLで検証する。PR内テストが緑でも公開後成功とは数えない。
公開workflowとPRをマージするまでは新ツールの公開受入条件は未完了である。

## 明示的な取得元リンクと共有導線

取得元URLの入力だけでは通信しない。有効なHTTP(S) URLのときだけ「取得元サイトを新しいタブで開く」リンクを表示し、クリックで通常のサイト表示へ移動する。新規タブはnoopener/noreferrer、元HTML・抽出結果は送らない。開いたサイトで保存したHTMLやコピーしたソースを利用者が取り込む。cross-origin fetchや運営proxyの機能ではない。

ボタンのHTML生成はweb-ui `source_link("source-url")`、URL検証と更新は `navigation.js`。独自のURL導線処理をconsumerに複製しない。Wikipedia/Pixiv公開画面のテーマとフォントは同じweb-uiの `adopt_document`、切替は `bindViews`、Pixivの既存article/historyボタンは `openExternalURL` に接続する。記事URLの組立や原文抽出はlabに残す。

`import_lab_pages.py`も同じ変換を再適用し、source_sha/source_sha256とpublished_sha256、presentationのweb-ui pinを分けて記録する。レポートの再実行・新しい取得結果とは表示しない。公開後CIもlab-publication specを実行し、プロバイダーAPI応答は明示した合成fixtureをブラウザrouteで再生する。WikipediaのライブAPI成功とは数えない。
