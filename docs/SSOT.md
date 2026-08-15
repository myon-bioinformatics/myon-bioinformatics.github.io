# Cross-project Single Sources of Truth

This repository owns canonical public data that is shared across the myon-bioinformatics projects.

## Canonical data

| Domain | Canonical source | Responsibility |
| --- | --- | --- |
| Person / skills / career | `profile.json` | Human profile facts and curated profile text |
| Repository facts | `api/repos.json` | Generated GitHub repository metadata; do not hand-edit |
| Portfolio curation | `projects.json` | Which repositories are featured and how they are presented |
| Public service endpoints | `services.json` | GitHub Pages, API/static data, MCP stub, repository and other public URLs |

## Ownership rules

1. Change a fact in its canonical source first.
2. Consumers should read or generate from the canonical source instead of copying the same fact by hand.
3. Generated outputs may be committed, but their generated regions must be clearly marked and reproducible.
4. `api/repos.json` is generated from GitHub and is the source of truth for repository facts such as repository URL, description, language, topics, stars, and update time.
5. `projects.json` is intentionally curated. `name` identifies the repository and `url` is a transitional compatibility field that must match `api/repos.json`; `desc`, `topics`, ordering, and future presentation-only fields may intentionally differ from repository metadata.
6. `services.json` owns public endpoints. README files and demos should consume service entries rather than inventing new canonical URLs.
7. `profile.json` may temporarily keep URL fields required by current renderers/generators, but CI must enforce that those compatibility values match the canonical entries in `services.json`.

## `services.json` schema

Services are grouped by responsibility rather than encoded into flat compound keys:

- `services.account`: account/external profile endpoints.
- `services.portfolio`: endpoints owned by the portfolio repository itself.
- `services.projects.<repository-name>`: repository-specific endpoints such as repository, Pages, or MCP stub URLs.

Allowed `kind` values:

- `external-profile`: an external public profile/account URL.
- `static-data`: a static JSON/data endpoint published by GitHub Pages.
- `repository`: the canonical GitHub repository URL; it must match `api/repos.json`.
- `pages`: a GitHub Pages site for the corresponding repository.
- `mcp-stub`: a browser-accessible MCP stub/demo endpoint under the corresponding project's Pages path.

Project `pages` and `mcp-stub` entries must map to a repository that exists in `api/repos.json`. The validator also enforces the expected GitHub Pages path prefix so repository renames/removals cannot silently drift.

## Shared repository policy and workflows

Cross-repository agent instructions and reusable GitHub Actions are maintained in the special profile repository:

- `myon-bioinformatics/myon-bioinformatics/templates/AGENTS.md`
- `myon-bioinformatics/myon-bioinformatics/templates/CLAUDE.md`
- `myon-bioinformatics/myon-bioinformatics/.github/workflows/reusable-actionlint.yml`
- `myon-bioinformatics/myon-bioinformatics/.github/workflows/reusable-pages-static.yml`

Individual repositories may keep local overrides when their requirements differ. Local files should document only the delta where practical.

## Intended dependency direction

```text
GitHub API ──> api/repos.json
                    │
projects.json ──────┼──> Portfolio / profile README / MCP / other consumers
profile.json ───────┤
services.json ──────┘

central templates / reusable workflows
                    └──> repository-local policy and CI callers
```

The goal is one authoritative owner for each fact, with many presentation layers.
