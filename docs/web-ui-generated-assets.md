# Generated browser assets

The generator is the installed `pysaiyanweboo` dependency (the `pages` group). Its full git commit is
pinned once, in `[tool.uv.sources]` in `pyproject.toml`.
`uv.lock` records the same source. The front page (`index.html`, from `scripts/front_page.py`: shell, 🧰 Tools
cards, the profile and projects rendered in every display mode, stylesheet and script in one file; outside the
lock because it follows the refreshed `api/repos.json`), the generated CSS/JS and the pages are not kept in git
(`.gitignore`); only the license under `tools/vendor/web-ui/` is. `--output DIR` writes the
generated files, `--stage DIR` writes the whole site (public static files plus generated files).

`web-ui-assets.lock.json` (`web-ui-generated/2`) records the commit and SHA-256
of all eight public assets. Normal generation checks the installed git provenance,
dependency pin, lock schema, public paths and every output hash before writing.
A mismatch fails the build before upload; there is no fallback to stale assets.
`tools/vendor/web-ui/generated.lock.json` publishes this provenance beside the assets.
The lab's `publication.json` separately identifies the imported report source.

🧰 The same generator also builds `tools/demos/` (`DEMOS` in `scripts/project_pages.py`): PySaiyanWeBoo's MCP / API
stubs, its in-page MCP server and its JUnit reader, plus their catalog `index.html`. Each gets the portfolio back link, 🧰 the tools' chrome
(the board with the clock, 🏠 ⭐ ⚙️ ☰ ⋯: `tools_chrome()` and `scripts/world.py` `add_chrome()`),
shortcut label and icons (`add_back_nav()` / `add_home_label()` in `scripts/project_pages.py`). Their SHA-256 values are under `pages` in the same lock, so
`presentation_identity()` (the shared assets, `outputs`) is unchanged. `--refresh-lock` rewrites their hashes with the assets'.

📄 `tools/html-import/index.html` (the HTML import tool page) is built by `render_html_import()` in the same file and locked
under `pages` as well; it is no longer kept in git.

## Reproduce

```sh
uv sync --locked --only-group browser
uv run --locked python scripts/project_pages.py --output /tmp/generated-web-ui
uv run --locked python -c "from scripts.project_pages import main; main(['--output', '/tmp/generated-web-ui'])"
uv run --locked pytest tests
uv run --locked --group browser python -m pytest tests/test_front_page.py
uv run --locked python scripts/project_pages.py --stage .generated-site
npx playwright test --config playwright/html-import.config.js
```

The front page tests stage the site themselves. Stage `.generated-site` before running the Node specs for HTML import and MCP lab.
Use a fresh output directory to reproduce a deployment.

`--copy-source` copies the files in `PUBLIC_SOURCE_FILES` from `scripts/project_pages.py`. Add a path there when a new
file needs to be served verbatim. The list covers public JSON endpoints and browser settings, icons and the web app
manifest, the HTML import guide, demo GIFs and their browser receipt, Niconico's browser script, and licenses.
The weekly view is rendered into `index.html`, and the chat's Python and dependencies are embedded in its HTML for
Pyodide. The generation and recording steps write those pages, the chat index, and other built assets directly to the
output directory. Build scripts, development docs, tests, and caches stay in the checkout.

## Move the generator pin

1. Review the upstream commit; set its full SHA in both dependency definitions.
2. Run `uv lock` and `uv sync --locked --only-group browser`.
3. Run `uv run --locked python scripts/project_pages.py --refresh-lock`.
4. Review the changed hashes, then run Python and browser checks.

`--refresh-lock --output DIR` supports refreshing and building together.
Refresh rejects an installed commit that differs from the dependency pin. All
rendering and provenance checks finish before the lock is touched.
Invalid output paths are rejected before refreshing. Filesystem write errors may
still leave partial writes; restore the reviewed snapshot from git and retry.
CI verifies hashes and never refreshes expected hashes automatically.

Rollback requires reverting the dependency pin, lock and generated assets together.
Other repositories and the parent child-head baseline require their own reviewed
updates; this change does not move those pins.
