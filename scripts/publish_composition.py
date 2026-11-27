"""Attach the pinned PSWB audio modules to Ironmate's arrangement editor."""
from pathlib import Path
import shutil
import sys

import pysaiyanweboo as ui


def publish(site):
    directory = site / "tools/browser-tools"
    page = directory / "index.html"
    html = page.read_text(encoding="utf-8")
    if 'id="song-audio"' not in html:
        raise ValueError("Stage the Ironmate arrangement editor before publishing audio")
    for name in ("composition.js", "studio-audio.js"):
        (directory / name).write_text(ui.js_source(name), encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("audition.mjs"), directory / "audition.mjs")
    tag = '<script type="module" src="./audition.mjs"></script>'
    page.write_text(html.replace("</body>", tag + "</body>", 1), encoding="utf-8")


if __name__ == "__main__":
    publish(Path(sys.argv[1]))
