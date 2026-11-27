"""Attach Portfolio's local Tone.js player to Ironmate's arrangement editor."""
from pathlib import Path
import shutil
import sys


def publish(site):
    directory = site / "tools/browser-tools"
    page = directory / "index.html"
    html = page.read_text(encoding="utf-8")
    if 'id="song-audio"' not in html:
        raise ValueError("Stage the Ironmate arrangement editor before publishing audio")
    if not (directory / "async-task.js").is_file():
        raise ValueError("The staged Ironmate tools must include async-task.js")
    shutil.copyfile(Path(__file__).with_name("audition.mjs"), directory / "audition.mjs")
    tag = '<script type="module" src="./audition.mjs"></script>'
    page.write_text(html.replace("</body>", tag + "</body>", 1), encoding="utf-8")


if __name__ == "__main__":
    publish(Path(sys.argv[1]))
