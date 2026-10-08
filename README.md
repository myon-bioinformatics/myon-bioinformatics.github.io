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

Current destinations include Ironmate, mcp-toolcall-lab,
flutter_navigation_basic, and web-ui.

## 🚀 Projects (JSON-driven cards)
This site renders “Projects” cards from a simple `projects.json`.  
Edit `projects.json` to reorder/update your cards.

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
