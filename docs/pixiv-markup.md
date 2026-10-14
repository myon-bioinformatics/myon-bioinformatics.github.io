# Pixiv source → Markdown → heading dropdown

The portfolio wraps the imported lab Pixiv URL and HTML helpers. It owns the
source-grammar adapter in `scripts/pixiv_markup.py` and `tools/pixiv/markup.js`.
Shared fixtures compare the Python and browser outputs. Generic controls belong
to pinned `web-ui`; Markdown rendering belongs to `markdown.py`.

The Pixiv tab accepts the original source or a copied `Title: … / Body: …`
extract. Choose a heading after Extract to switch the cached body locally.
A parent contains its child headings up to the next heading at the same or a
higher level. Repeated titles have separate ordinal values. Re-extracting resets
selection; errors clear stale options and output. The browser presents normalized
Markdown as text, as the Wiki tab does, without executing pasted HTML.

| Source | Canonical output |
| --- | --- |
| `*概要`, `**文明描写`, `*【概要】` | `# 概要`, `## 文明描写`, `# 【概要】` |
| `**強調**の文章` | Kept as emphasis, not a heading |
| `-**用語**`, `--[[下位]]` | Spaced Markdown list, indented child |
| `[[表示>対象]]` | `[表示](対象)`; existing Markdown links retained |
| `\|^項目\|値\|` | GFM table with a blank column header and bold row label; every data row retained |
| `[pixivimage:123]`, `![pixiv image 123](pixivimage:123)` | Ordinary artwork link |
| `[youtube:nlRxufviKuc]` | Ordinary YouTube watch link |

Code fences and backtick spans are preserved; unsupported syntax remains
literal. This is a conservative source adapter, not a complete Pixiv parser.
Only use it on known Pixiv source: unclosed star emphasis can be ambiguous.
Tables cannot preserve semantic row headers in GFM, so `^` becomes bold text.
Internal link targets are preserved, not rewritten to a guessed article URL.
Media URLs are not fetched or embedded. Saved HTML starting with a document or
block tag retains the imported HTML extraction path; it has no source-based
heading selector in this first increment.

## Python one-liners

From the portfolio root, using the pinned local UI copy:

```sh
PYTHONPATH=scripts:tools/vendor/web-ui python -S -c 'import sys; from pixiv_markup import extract_source; from web_ui import *; r=extract_source(sys.stdin.read()); print(render_document(title=r["title"],trusted_html=section_browser(tuple((s["label"],s["body"]) for s in r["sections"]),full_text=r["body"]),scripts=shared_scripts("tools/vendor/web-ui",names=("controls.js",))))' < source.txt > pixiv.html
```

Serve the repository root over HTTP and open `pixiv.html`. On Windows, place
`scripts`, `tools/vendor/web-ui` on `PYTHONPATH` using `;`, or copy the two Python
files into the working directory. No package installation or network is needed
for generation. The browser module must be served alongside the output.

For HTML rendering, make the separately pinned
[myon-bioinformatics/markdown.py](https://github.com/myon-bioinformatics/markdown/blob/aa5bccfcaf11f17473c7f1ff502509dfa1547660/markdown.py)
available on the Python import path, then compose the existing APIs:

```sh
python -S -c 'import sys; from pixiv_markup import pixiv_to_markdown; from markdown import markdown_to_html; from web_ui import render_document; print(render_document(trusted_html=markdown_to_html(pixiv_to_markdown(sys.stdin.read())))))' < source.txt > article.html
```

`markdown.py` is neither forked nor patched. Do not feed arbitrary HTML directly
to `trusted_html`; use the Markdown renderer's escaping and URL policy. The
interactive dropdown intentionally displays text; this command creates a
rendered article instead.

## Reimport and provenance

`scripts/lab_shared_ui.py` generates the select with `web_ui.select()`, suppresses
only the imported Pixiv auto-mount, and adds the consumer wrapper assets.
`import_lab_pages.py` reapplies this on future lab imports. `publication.json`
retains the original source hashes and records new published hashes. The lab
report snapshot is unchanged. No CI/deployment workflow is modified.
