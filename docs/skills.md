# Skills バーの決め方

ポートフォリオ先頭の Skills は `profile.json` が正本です。バーの幅は `level`（0–100）で、合計 100% の円グラフではありません。

Domain と Tools & Infra は自己評価です（経験に基づく）。Languages だけ、公開リポジトリの実データで現行の比重を整えます。

## Languages の規則（2026-11-25 JST 時点の観測）

証拠の範囲:

- 公開・非アーカイブ・非フォークのリポジトリ（30 件）
- GitHub Linguist の言語バイト（GraphQL `languages`）
- JavaScript（`.js` / `.cjs` / `.mjs` を含む）は **Node.js** として数える
- アーカイブ・フォークは入れない（TypeScript / Go / JavaScript を押し上げるため）
- 非公開リポジトリは入れない

使わないもの:

- アーカイブ済みの `flutter_navigation_basic`（TypeScript 約 164 KB、JavaScript 約 288 KB、Dart 約 3.8 MB）
- アーカイブ済みの `HelpYouBuildServer`（多言語の入門テンプレート。Go はここだけ、2.5 KB の `main.go`）
- Linguist が既に除外している vendor / generated。子リポジトリの `vendor/py_launch.cjs` なども Linguist 上は多く除外済み

公開・現行 30 件の Linguist バイト（2026-11-25）:

| 言語 | バイト | リポジトリ数 |
| --- | ---: | ---: |
| Python | 26,235,991 | 30 |
| Node.js (JavaScript) | 500,501 | 8 |
| TypeScript | 79,007 | 2（mcp-toolcall-lab の deploy、BrowserTestKit の Playwright 試験） |
| Bash (Shell) | 12,707 | 2 |
| Go | 0 | 0 |

換算（Python を現行どおり 90 に固定）:

1. `score = 90 * log10(1 + bytes) / log10(1 + bytes_Python)`
2. 現行リポジトリが 1 件または 2 件だけの言語は、狭い足跡として `score × 0.75`
3. 現行バイトが 0 でも、経歴に残る言語（Go）は残差 35 を下限にする（消さない）
4. Bash は `.sh` の分量だけでは日常の CLI 作業を表せないので、70 を維持する（Tools の Linux / CLI とは別項目）
5. 5 の倍数に丸める

| 言語 | 以前 | 規則による値 | 採用 |
| --- | ---: | ---: | ---: |
| Python | 90 | 90 | 90 |
| Node.js | （項目なし） | 69.1 → 70 | 70 |
| Bash | 70 | （例外） | 70 |
| TypeScript | 60 | 59.4 × 0.75 → 45 | 45 |
| Go | 65 | 残差 | 35 |

TypeScript の現行 79 KB のうち約 52 KB は mcp-toolcall-lab の deploy、約 27 KB は BrowserTestKit の試験です。主言語として触っている分量ではない、という自己評価と一致します。Go の公開現行バイトは 0 です。

Tools の Flutter / Dart は、この Languages の再計算対象ではありません。Dart の Linguist バイトはほぼアーカイブ済みリポジトリにあります。

数値が古くなったら、同じ範囲で Linguist を取り直し、この規則で `profile.json` を更新します。親 README の Skills ブロックは生成結果なので、手では直しません（`scripts/sync-readme.mjs` が `profile.json` を読みます）。
