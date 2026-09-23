# Stagehand v4 dual-SDK reference

This repository intentionally keeps both Stagehand v4 SDK paths as a reference for other myon-bioinformatics repositories.

Here, **reference implementation** means three things only:

1. a concrete SDK install/import pattern,
2. a credential-free CI pattern for validating the supported surface,
3. a documented boundary between deterministic Playwright checks and optional agent tests.

It does **not** mean that every downstream repository must copy both SDKs or the same CI layout.

- Node/TypeScript-friendly repositories can use `@browserbasehq/stagehand`.
- Python/pytest-friendly repositories can use `stagehand`.
- Existing deterministic Playwright tests remain the correctness/screenshot baseline.
- Stagehand is an optional agent/integration lane, not a replacement for Playwright.

## Shared contract vs SDK-specific contract

The common required contract is deliberately small and credential-free:

- dependency installation succeeds,
- SDK import succeeds,
- the expected Stagehand v4 entry point is exposed.

The concrete export shape is SDK-specific. Node checks the public `Stagehand` export. Python accepts `Stagehand` or `AsyncStagehand`, matching the Python package surface. The probes are intentionally similar in purpose rather than byte-for-byte symmetric.

Session creation, browser launch, navigation, extraction, `act`, `observe`, model calls, and remote Browserbase sessions are **optional integration checks**, not part of the required CI contract today.

Live browser/model operations must receive credentials through GitHub Actions secrets or environment variables; secrets must not be committed or included in metadata/artifacts.

## Advisory metadata

`scripts/tooling_meta.py` records repository SHA and observed tool/package versions as **advisory evidence only**.

- version drift alone is never a failure condition,
- an older installed version is not automatically an error,
- metadata exists for reproducibility and diagnosis, not freshness enforcement,
- `sha: null` means the Git SHA probe could not be observed in that environment; it is diagnostic information, not proof that the repository state is invalid.

Command probes default to a 10 second timeout. Slow environments can override it with `STAGEHAND_TOOL_TIMEOUT`.

If Node and Python compatibility requirements diverge later, document that explicitly as a compatibility matrix here rather than assuming they must remain identical.

## Downstream use

Other repositories should copy only the lane that matches their existing toolchain. This repository is intentionally the exception that demonstrates both.

- Node/Playwright-heavy repository → prefer the Node Stagehand lane.
- Python/pytest-heavy repository → prefer the Python Stagehand lane.
- lightweight library → metadata only unless browser automation is actually useful.


## Screenshot evidence

In addition to the dual-SDK Stagehand surface checks, this repository captures
deterministic browser screenshots with Playwright/Chromium.

Current baseline viewports:

- `desktop-1440x900`
- `mobile-390x844`

Artifacts are uploaded as `github-io-screenshots` and retained for 14 days.

This visual evidence is intentionally separate from Stagehand's optional
agent-oriented integration lane. Playwright provides the stable screenshot
baseline; Stagehand remains the optional browser-agent reference.
