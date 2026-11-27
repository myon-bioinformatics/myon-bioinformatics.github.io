"""Publish PSWB's Composition Studio inside Portfolio's existing Browser Tools page."""
from pathlib import Path
import sys

import pysaiyanweboo as ui


def publish(site):
    tools = site / "tools"
    directory = tools / "browser-tools"
    page = directory / "index.html"
    html = page.read_text(encoding="utf-8")
    if 'id="digest"' not in html:
        raise ValueError("Browser Tools was not staged")
    source = "https://myon-bioinformatics.github.io/PySaiyanWeBoo/examples/composition-studio.html"
    panel = ui.studio_html()
    if 'id="composition"' in html:
        heading = "<h2>🎵 Composition Studio</h2>"
        if html.count(heading) != 1:
            raise ValueError("unexpected songwriting section")
        html = html.replace(heading, heading + panel)
        html = html.replace(f'<a href="{source}" target="_blank" rel="noopener">🎵 作曲スタジオを開く ↗</a>', "")
    else:
        html = html.replace("</main>", '<section id="composition">' + panel + "</section></main>", 1)
    assets = ("composition.js", "studio-audio.js")
    for name in assets:
        (directory / name).write_text(ui.js_source(name), encoding="utf-8")
    (directory / "composition.css").write_text(ui.css_source("studio.css"), encoding="utf-8")
    html = html.replace("</head>", '<link rel="stylesheet" href="./composition.css"></head>', 1)
    scripts = "".join(f'<script type="module" src="./{name}"></script>' for name in assets)
    page.write_text(html.replace("</body>", scripts + "</body>", 1), encoding="utf-8")
    for folder in ("image-studio", "slide-studio"):
        for entry in (tools / folder).rglob("index.html"):
            text = entry.read_text(encoding="utf-8")
            if source in text:
                entry.write_text(text.replace(source, "/tools/browser-tools/#composition"), encoding="utf-8")


if __name__ == "__main__":
    publish(Path(sys.argv[1]))
