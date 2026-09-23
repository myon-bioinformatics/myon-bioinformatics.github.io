# Stagehand v4 dual-SDK reference

This repository intentionally keeps both Stagehand v4 SDK paths as a reference for other myon-bioinformatics repositories.

- Node/TypeScript-friendly repositories can use `@browserbasehq/stagehand`.
- Python/pytest-friendly repositories can use `stagehand`.
- Existing deterministic Playwright tests remain the correctness/screenshot baseline.
- Stagehand is an optional agent/integration lane, not a replacement for Playwright.

The required CI contract is deliberately offline and credential-free: each SDK must install and expose its expected Stagehand v4 surface. Live browser/model operations are opt-in and must receive credentials through GitHub Actions secrets; secrets must not be committed or included in artifacts.

`scripts/tooling_meta.py` records SHA and observed tool/package versions as advisory evidence. Version drift alone is not a failure condition.

Other repositories should copy only the lane that matches their existing toolchain. This repository is intentionally the exception that demonstrates both.
