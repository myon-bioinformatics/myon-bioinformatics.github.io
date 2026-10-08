"""Import an explicitly supplied trusted lab public export, never raw test logs."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

FILES = ('index.html', 'terminal.css', 'pages-hash.js', 'pages-wiki.js',
         'pages-pixiv.js', 'summary.json', 'build_meta.json')
OPTIONAL = ('repository-diagnostics.html', 'repository-diagnostics.json', 'repository-diagnostics.jsonl')
DESTINATION = Path(__file__).resolve().parents[1] / 'tools' / 'mcp-toolcall-lab'


def import_export(source: Path, destination: Path = DESTINATION) -> dict:
    # All reads/validation precede writes. The source must be a trusted public
    # export from the lab; this is not an arbitrary HTML/JS sanitizer.
    payload = {name: (source / name).read_bytes() for name in FILES}
    payload.update({name: (source / name).read_bytes() for name in OPTIONAL if (source / name).is_file()})
    meta = json.loads(payload['build_meta.json'])
    json.loads(payload['summary.json'])
    if not re.fullmatch(r'[0-9a-f]{40}', meta.get('sha', '')):
        raise ValueError('public export requires a full source commit SHA')
    page = payload['index.html'].decode('utf-8')
    if any(name in page and name not in payload for name in OPTIONAL):
        raise ValueError('referenced diagnostics must be included in public export')
    banner = ('<aside aria-label="Publication ownership"><p>Portfolio-hosted lab tools. '
              'The report below is an imported Actions snapshot, not a live run or a claim '
              'of the latest result. See <a href="publication.json">import identity</a> and '
              '<a href="https://github.com/myon-bioinformatics/mcp-toolcall-lab/actions/workflows/stub-pages.yml">lab Actions</a>. '
              '<a href="../../#tools">Back to portfolio</a>.</p></aside>')
    if '</header>' not in page:
        raise ValueError('public export has no page header')
    payload['index.html'] = page.replace('</header>', '</header>' + banner, 1).encode('utf-8')
    manifest = {'schema': 'portfolio-lab-publication/1', 'source_repository': 'myon-bioinformatics/mcp-toolcall-lab',
                'source_sha': meta['sha'], 'source_dirty': meta.get('dirty'),
                'imported_at': datetime.now(timezone.utc).isoformat(),
                'report_status': 'imported_snapshot',
                'source_sha256': {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in payload},
                'published_sha256': {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}}
    destination.mkdir(parents=True, exist_ok=True)
    for name in OPTIONAL:
        if name not in payload:
            (destination / name).unlink(missing_ok=True)
    for name, data in payload.items():
        (destination / name).write_bytes(data)
    (destination / 'publication.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='trusted extracted lab _site public export')
    args = parser.parse_args()
    import_export(args.source)
