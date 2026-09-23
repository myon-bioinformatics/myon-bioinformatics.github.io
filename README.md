<h1 align="center">🧭 myon-bioinformatics.github.io</h1>
<p align="center">Personal site & portfolio — built and maintained by <a href="https://github.com/myon-bioinformatics">myon</a></p>

<p align="center">
  <img alt="Last commit" src="https://img.shields.io/github/last-commit/myon-bioinformatics/myon-bioinformatics.github.io">
  <img alt="License" src="https://img.shields.io/github/license/myon-bioinformatics/HelpYouBuildServer">
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

## 🔄 Automation: projects.json from pinned repos
- Manual run: **Actions → Update Projects JSON → Run workflow**
- Schedule: every Monday 03:17 UTC

Files:
- `.github/workflows/update-projects.yml`
- `scripts/generate_projects_from_pinned.py`

---

<details>
<summary>🇯🇵 日本語版 (クリックで展開)</summary>

このリポジトリは**GitHub Pagesサイト**です。`projects.json` を編集するだけでトップのプロジェクトカードが更新されます。  
ローカル確認は `python -m http.server` でOK。自動更新は Actions が `projects.json` をピン留めから生成します。
</details>
