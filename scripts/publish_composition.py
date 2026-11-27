"""Attach Portfolio's local Tone.js player to Ironmate's arrangement editor."""
import argparse
from pathlib import Path
import shutil


def publish(site):
    """🎵 Returns True when the player was attached. ⏸ Until Ironmate's default branch has the arrangement editor (a pull
    request preview stages it from its branch), there is nothing to attach: the deploy goes on without audio."""
    directory = site / "tools/browser-tools"
    page = directory / "index.html"
    html = page.read_text(encoding="utf-8") if page.is_file() else ""
    if 'id="song-audio"' not in html:
        print("⏸ 🎵 Ironmate's arrangement editor is not staged yet: no audition player")
        return False
    if not (directory / "async-task.js").is_file():
        raise ValueError("The staged Ironmate tools must include async-task.js")
    shutil.copyfile(Path(__file__).with_name("audition.mjs"), directory / "audition.mjs")
    tag = '<script type="module" src="./audition.mjs"></script>'
    page.write_text(html.replace("</body>", tag + "</body>", 1), encoding="utf-8")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="path to the staged site")
    publish(parser.parse_args().site)
