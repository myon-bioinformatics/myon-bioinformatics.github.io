"""Sub-site & Sub-page Evidence Capture Script.

Navigates through all portfolio sub-pages, view modes, and sub-tools
(html-import, mcp-toolcall-lab tabs: wiki, pixiv, niconico, diagnostics),
captures deterministic screenshots, writes metadata, and stitches a
multi-frame evidence montage image.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from record_demo import stitch_png_grid


TARGET_ROUTES = [
    {'name': 'portfolio_modern', 'url': 'http://localhost:8080/', 'mode': 'modern'},
    {'name': 'portfolio_github_like', 'url': 'http://localhost:8080/', 'mode': 'github-like'},
    {'name': 'portfolio_json', 'url': 'http://localhost:8080/', 'mode': 'json'},
    {'name': 'portfolio_markdown', 'url': 'http://localhost:8080/', 'mode': 'markdown'},
    {'name': 'tool_html_import', 'url': 'http://localhost:8080/tools/html-import/'},
    {'name': 'lab_home', 'url': 'http://localhost:8080/tools/mcp-toolcall-lab/#home'},
    {'name': 'lab_wiki', 'url': 'http://localhost:8080/tools/mcp-toolcall-lab/#wiki'},
    {'name': 'lab_pixiv', 'url': 'http://localhost:8080/tools/mcp-toolcall-lab/#pixiv'},
    {'name': 'lab_niconico', 'url': 'http://localhost:8080/tools/mcp-toolcall-lab/#niconico'},
    {'name': 'lab_diagnostics', 'url': 'http://localhost:8080/tools/mcp-toolcall-lab/repository-diagnostics.html'},
]


def capture_evidence(base_url: str = 'http://localhost:8080', output_dir: str | Path = 'test-results/evidence') -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    evidence_frames = []
    meta_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        for route in TARGET_ROUTES:
            target_url = route['url'].replace('http://localhost:8080', base_url.rstrip('/'))
            page.goto(target_url)
            page.wait_for_load_state('networkidle')

            if 'mode' in route:
                page.select_option('#view-mode-select', route['mode'])
                page.wait_for_timeout(300)

            frame_path = out_dir / f"{route['name']}.png"
            page.screenshot(path=frame_path)

            data = frame_path.read_bytes()
            sha256 = hashlib.sha256(data).hexdigest()

            evidence_frames.append(frame_path)
            meta_records.append({
                'name': route['name'],
                'url': target_url,
                'mode': route.get('mode', 'default'),
                'title': page.title(),
                'sha256': sha256,
                'file': frame_path.name,
            })

        context.close()
        browser.close()

    montage_path = out_dir / 'evidence_montage.png'
    stitch_png_grid(evidence_frames, montage_path, columns=3)

    summary_meta = {
        'schema': 'portfolio-evidence-summary/1',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'captured_count': len(meta_records),
        'records': meta_records,
        'montage_file': montage_path.name,
    }

    (out_dir / 'meta.json').write_text(json.dumps(summary_meta, indent=2) + '\n', encoding='utf-8')
    return out_dir


def main():
    parser = argparse.ArgumentParser(description='Capture screenshots and evidence montage for all sub-sites.')
    parser.add_argument('--base-url', default='http://localhost:8080', help='Base URL of running server')
    parser.add_argument('-o', '--output', default='test-results/evidence', help='Output evidence directory')

    args = parser.parse_args()
    out = capture_evidence(base_url=args.base_url, output_dir=args.output)
    print(f'Captured evidence for {len(TARGET_ROUTES)} sub-sites in {out}')


if __name__ == '__main__':
    main()
