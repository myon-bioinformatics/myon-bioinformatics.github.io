# Generated web-ui browser assets: staged migration

Stage 1 keeps the tracked `tools/vendor/web-ui/` snapshot, its root `vendor-lock/1`
entries, nested HTML-import lock, and Python wrapper unchanged. These historical
CSS/JS entries must **not** be refreshed to web-ui main: the source paths no longer
exist there. They are rollback/source-snapshot evidence, not the active build's
browser asset identity. No legacy file is deleted in this change.

The separately vendored `tools/vendor/web-ui-generator/web_ui.py` comes from
web-ui main commit `b3afe1cf5db6ab58e9b1dc77dce3fa62dd1d1a44`. The normal vendor
lock verifies its Git blob and SHA-256. `web-ui-assets.lock.json` repeats the
source identity and pins the SHA-256 of eight generated browser assets.
`scripts/build_web_ui_assets.py` checks both identities before importing the
Python generator, calls `css_source()` and `write_js()`, and verifies **all**
outputs before writing any of them. It uses only the Python standard library and
has no network/download step. `--site` is intentionally unnecessary: we need the
asset APIs, not upstream's example pages or brand images.

After Jekyll builds `_site`, generation replaces only these published URLs:

- `tools/vendor/web-ui/css/{tokens,base,components}.css`
- `tools/vendor/web-ui/css/themes/modern.css`
- `tools/vendor/web-ui/js/{navigation,ui,controls,collection}.js`

HTML links, classic/module script use, local imports, navigation bindings and CSP
are unchanged. The active source/output identity is published at
`tools/vendor/web-ui/generated.lock.json`. Existing `publication.json` describes
the historical imported report and wrapper, not this later asset build.
Deployment fails before upload if generation verification fails; it never silently
falls back to old assets. Browser CI stages the same overlay in `.generated-site`
and runs the existing browser suite against it. The tracked legacy lock tests
continue to run against the untouched source tree.

## Audit scope and order

Pages' `tools/html-import` and `tools/mcp-toolcall-lab` are direct users. The parent
registry also registers Aoi's Python wrapper and Ironmate's flow tools/CommonJS
files. Those consumers remain at their existing pins; this PR does not update
unrelated wrappers or assume that every removed upstream path has a generator.
The parent's companion PR adds the new generator enrollment without replacing
legacy topology. Parent PR validation supports pending pure additions.

Merge order requires explicit approval: Pages adoption first, then refresh the
parent's reviewed `child-heads.json` Pages baseline to the resulting main commit
and merge the companion registry change. Do not merge parent enrollment against
an old child baseline (push/schedule audit is strict). Keep both PRs unmerged
until the user reviews the results.

## Reproduce and rollback

```sh
python -m pytest tests/test_generated_web_ui_assets.py tests/test_myon_bioinformatics_github_io_vendor_lock.py tests/test_html_import.py tests/test_lab_publication.py
python -S scripts/build_web_ui_assets.py --output /tmp/generated-web-ui
```

Use the staging-copy step in `ci.yml` followed by
`npx playwright test --config playwright/generated.config.js` for browser checks.
To roll back, revert the deployment generation step and use the retained tracked
snapshot. A later, separately reviewed stage can retire old source-path entries
once generated distribution has been accepted. Updating the generator requires
reviewing its immutable source pin **and** all output hashes; do not recompute
expected hashes automatically in CI.
