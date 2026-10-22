<h1 align="center">🧭 myon-bioinformatics.github.io</h1>
<p align="center">Personal site & portfolio — built and maintained by <a href="https://github.com/myon-bioinformatics">myon</a></p>

<p align="center">
  <img alt="Last commit" src="https://img.shields.io/github/last-commit/myon-bioinformatics/myon-bioinformatics.github.io">
  <img alt="License" src="https://img.shields.io/github/license/myon-bioinformatics/myon-bioinformatics.github.io">
  <a href="https://github.com/myon-bioinformatics"><img alt="GitHub followers" src="https://img.shields.io/github/followers/myon-bioinformatics?style=social"></a>
  <a href="https://twitter.com/myonitbusiness"><img alt="Twitter Follow" src="https://img.shields.io/twitter/follow/myonitbusiness?style=social"></a>
</p>

---

## 📍 Live
- **Site:** https://myon-bioinformatics.github.io
- **Intro/Profile:** https://github.com/myon-bioinformatics
- **Links:** <a href="https://lit.link/myon123">lit.link</a> / <a href="https://linktr.ee/myon123">Linktree</a>

> If you’re a beginner or recruiter and want a quick overview of me, the **Intro/Profile** link above is the fastest route.

---

## 🖼️ Latest successful render

The latest successful GitHub Pages deployment publishes deterministic Chromium
screenshots at stable URLs:

- [Desktop 1440×900](https://myon-bioinformatics.github.io/evidence/latest/desktop.png)
- [Mobile 390×844](https://myon-bioinformatics.github.io/evidence/latest/mobile.png)
- [Evidence metadata (SHA / timestamp / viewport)](https://myon-bioinformatics.github.io/evidence/latest/meta.json)

[![Latest desktop render](https://myon-bioinformatics.github.io/evidence/latest/desktop.png?v=25e9697c)](https://myon-bioinformatics.github.io/evidence/latest/desktop.png)

These URLs are replaced only by a **successful Pages deployment**, so they act as
a human-readable `latest` view rather than a per-run artifact archive.

The inline README preview uses a cache-busting query only for GitHub's image
proxy. The link target remains the stable `/evidence/latest/desktop.png` URL.

---

## 🧭 Tools & Demos portal
The top page also contains a hand-maintained **Tools & Demos** discovery catalog
for selected live GitHub Pages applications. This is intentionally separate from
the JSON-driven repository cards: adding a new live tool requires updating both
`index.html` and `tests/test_portal_links.py`, so the destination and its HTTPS
Pages-host contract are reviewed together.

Ironmate now has a local metadata card (`project-ironmate.json`) and a repository link;
its retired MCP stub does not need a dedicated Pages deployment. Live destinations include mcp-toolcall-lab,
flutter_navigation_basic, and web-ui.

## 🚀 Projects (JSON-driven cards)
Projects displays every repository in the public `api/repos.json` catalog, including archived work. Active repositories appear first, then archived repositories; each group is ordered by name. Search, topic and status filters work together across all five display modes. Topic controls expand on demand so the full catalog remains easy to reach on mobile. Cards, tags, inputs and copy buttons use the same pinned web-ui stylesheets already used by this portfolio’s tool pages (`tools/vendor/web-ui/`, source identity in `tools/html-import/vendor.lock.json`). Local CSS only adds catalog layout, mode mapping and filter state; no second component stylesheet is vendored.

`projects.json` supplies optional curated descriptions and extra topics for matching repositories. It never limits catalog membership, and repository URLs always come from `api/repos.json`. If curation is unavailable, repository descriptions (then README summaries) are used. A missing catalog shows a load error instead of a misleading partial list.

The catalog refresh runs daily at 06:00 JST. A successful `Update repos API` run on `main` triggers the existing Pages deployment through `workflow_run`, which checks out the refreshed `main`. This explicit handoff is required because catalog commits pushed with `GITHUB_TOKEN` do not trigger `push` workflows. Failed or cancelled refreshes do not publish a new site.

Changes to the Pages workflow also trigger a catalog refresh to exercise this handoff. Render evidence records the actual checked-out commit, including when the refresh or a concurrent update has advanced `main` beyond the event's original SHA.

## 🎛️ Display mode
- Default mode is **modern**
- Repository default can be changed via `site.config.json`:
  - `defaultViewMode`: `modern`, `xml-like`, `json`, `markdown`, or `github-like`
- Users can switch mode from the page header, and their choice is saved in browser local storage.

---

## 🚀 Quick start (Local)
```bash
git clone https://github.com/myon-bioinformatics/myon-bioinformatics.github.io
cd myon-bioinformatics.github.io
python -m http.server 8080
# → http://localhost:8080
```

---

## 🧑‍🎤 About me (short)
I started coding through **Bioinformatics**. Main tools: **Python**, plus **Go/TypeScript**.  
I like building **GUI/CLI tools** for security & backend.

- Skills (JP): https://myon-bioinformatics.github.io  
- Tips (JP): https://qiita.com/myon-bioinformatics  
- Career (JP): https://job-draft.jp/users/58541  
- Composer Portfolio: https://www.youtube.com/@freez-myon  
- Wantedly: https://www.wantedly.com/id/myon123

---

## 🔄 Maintaining project cards

Edit `projects.json` and validate its canonical shape using the instructions in
[docs/SSOT.md](docs/SSOT.md). The current repository has no
`update-projects.yml` workflow or scheduled pinned-repository card update.
`scripts/generate_projects_from_pinned.py` is a standalone legacy helper; its
presence does not mean it runs automatically.

## 🧪 CI evidence

[portal](.github/workflows/portal.yml) and the Python job in
[Stagehand v4 dual-SDK reference](.github/workflows/stagehand-v4-reference.yml)
produce pytest JUnit and call the parent's pinned shared failure-identity
collector. Raw artifacts are `junit-portal-py3.12` and
`junit-stagehand-python-py3.12`, retained for 14 days. Compact artifacts are
`portal-failure-identity` and `stagehand-python-failure-identity`; the shared
collector does not set `retention-days`, so repository-default retention applies. Missing or invalid expected XML fails collection; the original
test exit code remains authoritative.

The Stagehand reference checks SDK surfaces. Its separate screenshot job uses
Playwright Chromium; it does not demonstrate Stagehand agent execution. See
[STAGEHAND.md](STAGEHAND.md) for the reference scope. Pages deployment owns the
stable `evidence/latest/` screenshots described above.

---

<details>
<summary>🇯🇵 日本語版 (クリックで展開)</summary>

このリポジトリは**GitHub Pagesサイト**です。`projects.json` を編集するだけでトップのプロジェクトカードが更新されます。  
ローカル確認は `python -m http.server` でOK。`projects.json` のピン留めからの定期自動更新workflowは現在ありません。編集・検証手順は [docs/SSOT.md](docs/SSOT.md) を参照してください。
</details>

## Lab public tools and reports

The portfolio now receives the lab's public Wiki/Pixiv interfaces and exported
Actions report under `tools/mcp-toolcall-lab/` (`#wiki` and `#pixiv`). MCP servers,
Docker execution, raw traces, and test generation remain in mcp-toolcall-lab.
Flutter's working Pages application is unchanged.

The initial import is the public export observed on 2026-10-08, with source
identity `3b15b7911695fc76fa8cd01f514e57133fb02d83` (2026-10-05).
Its original `dirty: true` observation is preserved, not silently corrected.
It is explicitly labelled an imported snapshot, not the latest Actions result.
`publication.json` records source and published file hashes and import time.
Only public report files are admitted; raw MCP/anti-pattern logs are excluded.
Existing source copyright and repository LICENSE apply to transferred assets.

To update, obtain a trusted lab `stub-pages-observations` artifact, extract its
`_site/` public export, then run:

```sh
python -S scripts/import_lab_pages.py --source /path/to/export/_site
python -m pytest tests/test_portal_links.py tests/test_lab_publication.py
```

Review and commit the imported output in a PR. No untrusted archive is extracted
by this helper; it receives an already extracted trusted directory. There is no
automatic claim that an imported snapshot equals the newest run. The lab-side
legacy redirect must land only after this portfolio receiving change is deployed.

### Shared browser controls

HTML Import exposes an explicit HTTP(S) source link in a new tab; pasting or changing extraction options stays local. `web-ui` owns `source_link`, `view_tabs`, `adopt_document`, and `navigation.js`. The portfolio vendors the pinned implementation and keeps the lab report source identity separate from its shared presentation transform. Wikipedia/Pixiv typography and controls use that same modern theme. See [HTML Import contract](docs/html-import.md).

Pixiv source now supports a local heading dropdown through a consumer adapter.
See [source grammar, Python one-liners, and markdown.py integration](docs/pixiv-markup.md).

### Portfolio search, highlights and image evidence

- Project text search and topic filters work together in each view mode.
- The lab's Niconico tab attempts Snapshot Search API v2 from the browser. Live verification on 2026-10-21 JST found HTTP 200 JSON responses without `Access-Control-Allow-Origin`; the published browser could not read results. The panel explains this limitation and offers official Niconico search with the selected keyword/sort. GitHub Pages cannot fix an upstream CORS header. The portfolio owns `tools/niconico/` and reapplies this panel when importing a lab report. See [live verification](docs/evidence/niconico-live-20261021/README.md).
- AI & Tech Highlights displays public GitHub search results, or explicitly labelled curated examples when the API is unavailable. Curated examples do not claim current star counts.
- `python -S scripts/generate_apng.py frame1.png frame2.png -o demo.png` creates an animation without third-party dependencies. Frames must share dimensions, color format, palette and transparency.
- `python -S scripts/record_demo.py frame1.png frame2.png -o grid.png --mode montage` reconstructs PNG filters before stitching. Montage inputs must be matching non-interlaced 8-bit RGB/RGBA images.
- Browser capture is a development dependency: install `tests/requirements-browser.txt`, run `python -m playwright install --no-shell chromium`, serve the site, then run `python scripts/capture_portfolio_evidence.py --base-url http://localhost:8080 -o test-results/evidence`. It records all five portfolio modes and six tool routes, screenshots, hashes and a montage. Capture uses labelled curated highlights for repeatability.

Verification: `python -m pytest tests`, `npx playwright test`, and `node scripts/validate-ssot.mjs`. Python test dependencies stay in `tests/requirements.txt`; image regression tests decode exports with the vendored `pillow_min` module from Ironmate (`tools/vendor/ironmate/`, recorded in `vendor.lock.json`). Production image conversion uses only the standard library. The portal workflow preserves browser evidence as an Actions artifact.
