# Brand assets and concept-review notes

## Installed assets

The profile icon and favicon come from the user-supplied brand sheet, not from a
new design. The replacement concept diagram supplied on 2026-10-22 is included
unchanged in the README. The earlier concept sheets are not installed.
GitHub account-avatar settings are unchanged; this change adds repository and
portfolio presentation only. No PWA manifest or installability claim is added.

- `assets/brand/myon-profile-icon.png`: exact 384×384 RGB crop, used in README and the site header.
- `assets/brand/myon-favicon-source.png`: exact 160×160 RGB crop.
- `assets/brand/favicon-{16,32,48}x{16,32,48}.png`: corresponding square favicon sizes, resized with Pillow LANCZOS.
- `/favicon.ico`: the same 16×16, 32×32 and 48×48 frames, including the conventional root fallback.
- `assets/brand/myon-concept-diagram.jpg`: the supplied 1536×1024 JPEG, used without cropping, resizing or editing. SHA-256: `4b5f4673e1eabe737913828fa54ec101c12d7fb1e4883581b9e8cd96a3f00964`.

The source sheet is 1254×1254 pixels, SHA-256
`64182aa94ff7d53823d461bb5c1fa9858da18416271a10cb0aef8dd7a6a9cfda`.
Crop boxes use `(left, top, right, bottom)` with an exclusive right/bottom:
profile `(57, 22, 441, 406)`, favicon `(504, 178, 664, 338)`.
The supplied JPEG's background and colors are retained; no masking, invented
transparency, generative editing or upscaling was applied.

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
