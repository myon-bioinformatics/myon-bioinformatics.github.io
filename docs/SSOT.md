# Cross-project Single Sources of Truth

This repository owns canonical public data that is shared across the myon-bioinformatics projects.

## Canonical data

| Domain | Canonical source | Responsibility |
| --- | --- | --- |
| Person / skills / career | `profile.json` | Human profile facts and curated profile text |
| Repository facts | `api/repos.json` | Generated GitHub repository metadata; do not hand-edit |
| Portfolio curation | `projects.json` | Which repositories are featured and how they are presented |
| Public service endpoints | `services.json` | GitHub Pages, API, MCP stub, and other public URLs |

## Ownership rules

1. Change a fact in its canonical source first.
2. Consumers should read or generate from the canonical source instead of copying the same fact by hand.
3. Generated outputs may be committed, but their generated regions must be clearly marked and reproducible.
4. `api/repos.json` is generated from GitHub and is the source of truth for repository facts such as repository URL, description, language, topics, stars, and update time.
5. `projects.json` is intentionally curated. It may contain presentation-specific summaries or ordering, but should not become a second database of GitHub repository facts.
6. `services.json` owns public endpoints. README files and demos should link to service keys rather than inventing new canonical URLs.

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
