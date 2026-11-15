# Generated browser assets

The generator is the installed `pysaiyanweboo` dependency. Its full git commit is
pinned in `requirements-pages.txt` and `[tool.uv.sources]` in `pyproject.toml`.
`uv.lock` records the same source. The front page (`index.html`, from `scripts/front_page.py`: shell, Tools & Demos
cards, stylesheet and script in one file), the generated CSS/JS and the pages are not kept in git
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
shortcut label and icons (`scripts/portfolio_nav.py`). Their SHA-256 values are under `pages` in the same lock, so
`presentation_identity()` (the shared assets, `outputs`) is unchanged. `--refresh-lock` rewrites their hashes with the assets'.

📚 `tools/projects/` is built the same way from the `showcase` of each `projects.json` entry: icon and media as
`raw.githubusercontent.com` URLs at the recorded commit, and one recorded run (command, exit code, output). Rerun a
command after moving its commit, then refresh:

```sh
uv run --locked python scripts/project_pages.py --record Err-o-RoadRunner=../err-o-roadrunner --refresh-lock
```

`--record` refuses a checkout that is not at the showcase commit, and runs with only `PATH`, a temporary `HOME` and
`LANG`, so no other variable of the recording machine reaches the page.
A command that needs packages (DRAgoWing needs Python-Markdown) uses the latest release, as its own build installs it:
add them with `uv run --locked --with markdown python scripts/project_pages.py --record DRAgoWing=../Aoi`.

## Reproduce

```sh
uv sync --locked --only-group browser
uv run --locked python scripts/project_pages.py --output /tmp/generated-web-ui
uv run --locked python -c "from scripts.project_pages import main; main(['--output', '/tmp/generated-web-ui'])"
uv run --locked pytest tests
uv run --locked python scripts/project_pages.py --stage .generated-site
npx playwright test
```

The browser suite serves `.generated-site`, so stage it first (CI does the same). Pages overlays the same verified
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
