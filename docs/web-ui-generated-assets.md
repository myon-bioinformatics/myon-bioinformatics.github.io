# Generated browser assets

The generator is the installed `pysaiyanweboo` dependency. Its full git commit is
pinned in `requirements-pages.txt` and `[tool.uv.sources]` in `pyproject.toml`.
`uv.lock` records the same source. The front page (`index.html`, from `scripts/front_page.py`: shell, Tools & Demos
cards, the profile and projects rendered in every display mode, stylesheet and script in one file; outside the
lock because it follows the refreshed `api/repos.json`), the generated CSS/JS and the pages are not kept in git
(`.gitignore`); only the license under `tools/vendor/web-ui/` is. `--output DIR` writes the
generated files, `--stage DIR` writes the whole site (source tree plus generated files).

`web-ui-assets.lock.json` (`web-ui-generated/2`) records the commit and SHA-256
of all eight public assets. Normal generation checks the installed git provenance,
dependency pin, lock schema, public paths and every output hash before writing.
A mismatch fails the build before upload; there is no fallback to stale assets.
`tools/vendor/web-ui/generated.lock.json` publishes this provenance beside the assets.
The lab's `publication.json` separately identifies the imported report source.

🧰 The same generator also builds `tools/demos/` (`DEMOS` in `scripts/project_pages.py`): PySaiyanWeBoo's MCP / API
stubs, its in-page MCP server and its JUnit reader, plus their catalog `index.html`. Each gets the portfolio back link,
shortcut label and icons (`add_back_nav()` / `add_home_label()` in `scripts/project_pages.py`). Their SHA-256 values are under `pages` in the same lock, so
`presentation_identity()` (the shared assets, `outputs`) is unchanged. `--refresh-lock` rewrites their hashes with the assets'.

📄 `tools/html-import/index.html` (the HTML import tool page) is built by `render_html_import()` in the same file and locked
under `pages` as well; it is no longer kept in git.

📚 `tools/projects/` is built the same way from the `showcase` of each `projects.json` entry: icon and media as
`raw.githubusercontent.com` URLs at the recorded commit, and one recorded run (command, exit code, output). Rerun a
command after moving its commit, then refresh:

```sh
uv run --locked python scripts/project_pages.py --record Err-o-RoadRunner=../err-o-roadrunner --refresh-lock
```

`--record` refuses a checkout that is not at the showcase commit, and runs with only `PATH`, a temporary `HOME` and
`LANG`, so no other variable of the recording machine reaches the page.
🧰 A showcase with `"scripts": {"match": ["tools/*.py", …]}` also gets a table of the scripts those globs match at the
same commit, recorded by the same `--record` into `scripts.items`: each file's own description (module docstring, or a
JS module's leading `//` comment past the shebang and imports) and the usage line of its `--help` (`python3 -S` or
`node`, same minimal environment; empty when a script has no `--help`, answers with something that does not start
with `usage`, or needs more than that). The list follows the
code, so the project's README links here instead of listing scripts by hand; ❔ marks a script without a description.

⏩ `--advance`, run daily by `repos-api.yml` (06:00 JST, before Pages publishes), moves every showcase to the newest
commit of its repository's default branch and records it there. It keeps the old pin (⏸, with the reason in the log)
when that commit no longer has the icon or media the page shows, or when the run that used to exit 0 now fails, so the
page always shows a working example; a repository it cannot fetch is skipped the same way.
A command that needs packages (DRAgoWing needs Python-Markdown) uses the latest release, as its own build installs it:
add them with `uv run --locked --with markdown python scripts/project_pages.py --record DRAgoWing=../Aoi`.

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

The front page tests stage the site themselves; the Node specs (HTML import, MCP lab) serve `.generated-site`, so stage it first. Pages overlays the same verified
assets after the Jekyll build. The public CSS/JS URLs remain unchanged.

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
