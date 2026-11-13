# Brand assets and concept-review notes

## Installed assets (2026-10-23)

The user assigned the bottom-right cat/code/plant pair from the new project sheet
to this portfolio, even though the sheet labels that pair `yourself`.
The parent profile and Yourself repository retain their existing icons.
No new design, masking, invented transparency or upscaling was applied.
GitHub account-avatar settings are unchanged. No PWA/installability claim is added (home screen: see below).

- `assets/brand/myon-profile-icon.png`: exact 170×170 RGB crop, used in README and site header.
- `assets/brand/myon-favicon-source.png`: exact 77×77 RGB crop.
- `assets/brand/favicon-{16,32,48}x{16,32,48}.png`: Pillow LANCZOS downscales of the supplied favicon crop.
- `/favicon.ico`: the same PNG bytes embedded as 16×16, 32×32 and 48×48 frames.
- `assets/brand/myon-concept-diagram.jpg`: earlier supplied 1536×1024 JPEG preserved without any change, SHA-256 `4b5f4673e1eabe737913828fa54ec101c12d7fb1e4883581b9e8cd96a3f00964`.

The new source sheet is 1536×1024 pixels, SHA-256
`5b01ec2dcf793ffc28335e2da1ce6842b8767aa6c1727ceec4a72f983ae98c50`.
Crop boxes `(left, top, right, bottom)`, exclusive right/bottom:
profile `(1232, 633, 1402, 803)`, favicon `(1423, 721, 1500, 798)`.
The JPEG's light background and colors are retained. Surrounding labels and
neighboring projects are excluded. Crop coordinates and asset hashes are also
recorded in `assets/brand/portfolio-brand-manifest.json`.

## 📱 Home screen and shortcuts (2026-11-13)

- `manifest.webmanifest` gives the label `🧬 myon` and the existing 48×48 and 170×170 PNGs. It sets `start_url`/`scope` `./`, so the shortcut opens `index.html`, and `display: browser`, so the portfolio opens in the browser and the other repositories' Pages keep their back button. Chromium reports nothing missing, only that this is a shortcut rather than an app window. A one-word change (`minimal-ui`) would make it an installable app.
- iOS reads the same 170×170 icon (`apple-touch-icon`) and label (`apple-mobile-web-app-title`) from `index.html`; nothing is upscaled.
- Tool pages link no manifest, so their shortcuts open the page itself. `portfolio_nav.add_home_label()` gives each one a label that fits under the icon: `📄 HTML取込`, `🧪 MCP Lab`, `🩺 Lab診断`. HTML import shows the portfolio icons; its CSP now has `img-src 'self'` so they load.
- `tests/test_site.py` (📱 home screen) checks all of this, and also that every local link and asset resolves. The Chromium part records `test-results/home-screen/home-screen-shortcut-<UTC>.gif`.

## 概念図の確認メモ（2026-10-22）

今回指定された新しい概念図を、そのまま README に掲載しました。
CI・再利用、テスト／レンダリング／記録、GitHub Pages での公開が明記され、
更新中の README・`profile.json`・`projects.json` の内容と対応しています。
そのうえで、残る確認点だけを記録します。図や本文は勝手に修正していません。

- **主な言語**：新しい図も Python / Go / TypeScript の表記です。このブランチの現在の紹介は Python / Node.js / Dart (Flutter)。Go / TypeScript はスキル自己評価や過去の経歴にも残るので、「今の主軸」と「経験あり」の区別が確認点です。スキル点数や職歴をリポジトリの比率だけから変えるものではありません。
- **扱う対象**：図は生命科学を起点にしていますが、現在の活動には Aoi 系の野球データ研究、開発者向けの単一ファイルツール、LLM / MCP の実験も含まれます。README の短い About も GUI/CLI・security & backend 中心のため、詳しい現状は `profile.json.currentFocus` と `projects.json` を参照してください。
- **成果と目標**：「医療・創薬への貢献」などの Impact は、確認済みの実装実績と同一視せず、目指す方向として読むのが安全です。

親プロフィール README は自動生成部分があり、`profile.json` と
`projects.json` が正本です。今後図の文言を見直す場合は、マージ済みの正本を
改めて確認してください（[SSOT](SSOT.md)）。
