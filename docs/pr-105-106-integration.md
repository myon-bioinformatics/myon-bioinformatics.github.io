# PR #105 / #106 integration review — 2026-11-12

## Inputs

- main: `8f62a16c2e4e7ad427a44bc9a759f094d48cfe25`
- #105: `54c89152695b0bdcdc7108b6f590143ab097a47b`
- #106: `da77a0b95470e5c11132c9a96fc324e03bc36f14`
- PySaiyanWeBoo pin retained from #105: `f624d9364017b7e2da7f797817dfba2a8d9adb14`

## Resolution

Nine #105/main conflict paths were reviewed: vendor-lock workflow, Dockerfile,
README, asset generator, lab adapter, deleted tests/requirements.txt, generated
asset tests, vendor-lock tests and parent-workflow tests.

Keep main's uv groups/lock, moved Playwright configs and vendor `recreate` step.
Add the pinned generator to the Docker/test groups; install git only in the Docker
builder stage. Keep tests/requirements.txt deleted. Retain #105's installed
generator and schema-2 hash verification; add #106's main(argv) behavior across
all eight entry points. Seven other #106 patches apply without conflicts.

Add pin consistency checks to normal generation and refresh. Reject invalid output
paths before refreshing. Add tests for explicit argv, CLI build/refresh, repeatable
hashes, mismatches, failed rendering and import-then-function invocation.

## Validation

| Check | Result |
| --- | --- |
| Python 3.12.14, `uv run --locked --group browser pytest tests -q` | 125 passed; 9 subtests passed |
| Two independent asset builds + recursive diff | Passed |
| HTML-import generation | Passed |
| SSOT, Node 26.13.1 | Passed |
| actionlint 1.7.7, changed workflows, shellcheck disabled | Passed |
| git diff --check | Passed |
| Generated-site Playwright, Node 26.13.1 | 90 failed at browser startup; 1 passed. System Chromium 156.0.8078.79 cannot create its singleton socket (`Operation not permitted`). No browser acceptance claim. |
| Playwright bundled Chromium download | Failed: returned archive could not be decoded |
| Local Jekyll / full Pages build | Not run: Ruby, Bundler, Jekyll and Docker unavailable |

Latest main's Pages and published-browser acceptance runs are successful; these
results describe main, not this proposed integration:

- https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/actions/runs/43101242921
- https://github.com/myon-bioinformatics/myon-bioinformatics.github.io/actions/runs/43101407596

## Proposed remote operations — require user approval

1. Re-fetch main and both PR heads; stop/reconcile if any reviewed input moved.
2. Push the reviewed integration, retaining both PR histories, to #105's existing
   `evidence/browser-gif-2026-11-07` branch (fast-forward, no force).
3. Update #105's description to this final scope and validation. Keep the existing
   main target; create no new PR. Wait for Python, browser, vendor and required
   checks on the pushed SHA; fix failures before merge.
4. Merge #105 into main with a merge commit, preserving #106's ancestry. Verify
   that #106 is recognized as indirectly merged; if it stays open despite its
   commits being reachable from main, close it as integrated with a clear note.
5. Verify the resulting main's CI, Pages build/deployment and published-browser
   acceptance. Report any deployment failure and its remediation.

Logical order: #106 → #105 integration branch → main. No remote push, PR update,
comment, close or merge has been performed during preparation.
