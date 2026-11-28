"""Attach Portfolio's local Tone.js player to Ironmate's arrangement editor (the one screen's framed #browser-tools)."""
import argparse
from html import escape, unescape
from pathlib import Path
import re
import shutil

_FRAME = re.compile(r'(<section id="browser-tools"[^>]*><template><iframe[^>]*\bsrcdoc=")([^"]*)(")')


def publish(site):
    """🎵 Returns True when the player was attached. ⏸ Until Ironmate's default branch has the arrangement editor (a pull
    request preview stages it from its branch), there is nothing to attach: the deploy goes on without audio. The editor is
    Browser Tools, framed in tools/index.html; the player loads from its folder (``/tools/browser-tools/audition.mjs``)."""
    directory, shell = site / "tools/browser-tools", site / "tools/index.html"
    html = shell.read_text(encoding="utf-8") if shell.is_file() else ""
    frame = _FRAME.search(html)
    page = unescape(frame[2]) if frame else ""
    if 'id="song-audio"' not in page:
        print("⏸ 🎵 Ironmate's arrangement editor is not staged yet: no audition player")
        return False
    if not (directory / "async-task.js").is_file():
        raise ValueError("The staged Ironmate tools must include async-task.js")
    shutil.copyfile(Path(__file__).with_name("audition.mjs"), directory / "audition.mjs")
    page = page.replace("</body>", '<script type="module" src="/tools/browser-tools/audition.mjs"></script></body>', 1)
    shell.write_text(html[:frame.start(2)] + escape(page) + html[frame.end(2):], encoding="utf-8")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path, help="path to the staged site")
    publish(parser.parse_args().site)
