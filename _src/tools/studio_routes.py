"""Portfolio publication routes for Studios; Ironmate supplies the generated content.

This is a build-time adapter, not a browser dependency or a copy of the editor.
"""
from collections.abc import Callable
import json
from pathlib import Path
import posixpath
import re
import shutil
from urllib.parse import urlsplit, urlunsplit

# 📽️ slide-studio/ is Ironmate's one slide editor (phone-first, the same page on a PC); slide-studio/phone/ (its address before)
# and slide-studio/pc/ (the PC studio it replaced) only send on to it.
PUBLIC_STUDIO_ENTRIES = ('image-studio/', 'browser-tools/', 'slide-studio/', 'slide-studio/pc/', 'slide-studio/phone/')
_IRONMATE_ENTRY_PAGES = ('index.html', 'tools/index.html', 'slides/index.html', 'slides/phone/index.html')

_IRONMATE_ROUTES = {'tools/': 'browser-tools/', 'slides/': 'slide-studio/'}


def _studio_path(path: str) -> str:
    for source, target in _IRONMATE_ROUTES.items():
        if path.startswith(source):
            return target + path[len(source):]
    return 'image-studio/' + path


_STUDIO_LINK = re.compile(r'(?P<attr>\b(?:href|src)=)(?P<quote>["\'])(?P<url>[^"\']+)(?P=quote)')


def _studio_href(source: str, url: str) -> str:
    parts = urlsplit(url)
    if not parts.path or parts.scheme or parts.netloc or parts.path.startswith('/'):
        return url
    directory = posixpath.dirname(source)
    old_target = posixpath.normpath(posixpath.join(directory, parts.path))
    if parts.path.endswith('/'):
        old_target = '' if old_target == '.' else old_target + '/'
    if old_target.startswith('../') or old_target == '..':
        return url
    target = _studio_path(old_target)
    new_path = posixpath.relpath(target, posixpath.dirname(_studio_path(source)))
    if parts.path.endswith('/'):
        new_path += '/'
    return urlunsplit(('', '', new_path, parts.query, parts.fragment))


def stage_ironmate_studios(built: Path, mapped: Path, add_navigation: Callable[[str, str], str]) -> None:
    """Relocate Ironmate's generated pages and keep their shared assets and cross-links working."""
    for page in _IRONMATE_ENTRY_PAGES:
        if not (built / page).is_file():
            raise FileNotFoundError(page)
    for path in built.rglob('*'):
        if not path.is_file() or path.name == '.nojekyll':
            continue
        source = path.relative_to(built).as_posix()
        if source == 'brand/index.html':   # 🚫 Ironmate's own forward to its tools/#brand; here they are browser-tools/ (the folder keeps the manifest and icons)
            continue
        target = mapped / _studio_path(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == '.html':
            page = _STUDIO_LINK.sub(lambda m: m['attr'] + m['quote'] + _studio_href(source, m['url']) + m['quote'],
                                    path.read_text(encoding='utf-8'))
            target.write_text(add_navigation(page, 'tools/' + _studio_path(source)), encoding='utf-8')
        elif source == 'brand/manifest.webmanifest':
            manifest = json.loads(path.read_text(encoding='utf-8'))
            # One shared app can open its two sibling tools under /tools/.
            manifest['scope'] = '../../'
            for shortcut in manifest.get('shortcuts', []):
                shortcut['url'] = _studio_href(source, shortcut['url'])
            target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        else:
            shutil.copyfile(path, target)
