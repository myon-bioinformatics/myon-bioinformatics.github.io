"""Conservative Pixiv-source wrapper. Stdlib only; Markdown rendering stays external.

Use only for known Pixiv source, not for autodetecting arbitrary Markdown.
The browser mirror is tools/pixiv/markup.js; shared fixtures enforce parity.
"""
from __future__ import annotations
import re

MAX_SOURCE_LENGTH = 200000


def _inline(text: str) -> str:
    def link(match):
        label = match[1].strip()
        target = (match[2] or label).strip().replace('(', '%28').replace(')', '%29').replace(' ', '%20')
        return f'[{label}]({target})'
    def prose(part):
        part = re.sub(r'NEXT▶︎(?=\[\[)', 'NEXT ▶︎ ', part)
        part = re.sub(r'\[\[([^\[\]>]+)(?:>([^\[\]]+))?\]\]', link, part)
        part = re.sub(r'!\[pixiv image (\d+)\]\(pixivimage:\1(?: "[A-Za-z0-9]+")?\)',
                      r'[pixiv image \1](https://www.pixiv.net/artworks/\1)', part)
        part = re.sub(r'\[pixivimage:(\d+)(?::[A-Za-z0-9]+)?\]',
                      r'[pixiv image \1](https://www.pixiv.net/artworks/\1)', part)
        return re.sub(r'\[youtube:([A-Za-z0-9_-]{11})\]', r'[YouTube](https://www.youtube.com/watch?v=\1)', part)
    # Preserve matched backtick code spans, including runs longer than one tick.
    parts = re.split(r'(`+)(.*?)\1', text)
    if len(parts) == 1:
        return prose(text)
    out = prose(parts[0])
    for index in range(1, len(parts), 3):
        out += parts[index] + parts[index + 1] + parts[index] + prose(parts[index + 2])
    return out


def pixiv_to_markdown(source: str) -> str:
    """Normalize star headings, wiki links/lists, row-header tables and media links.

    Already-normalized Markdown is kept. Unsupported syntax remains literal.
    GFM cannot express row headers: ^ cells become bold data cells, under an
    empty column header. No external media is downloaded or embedded.
    """
    if len(source) > MAX_SOURCE_LENGTH:
        raise ValueError('Pixiv source exceeds 200000 characters')
    source = source.replace('\r\n', '\n').replace('\r', '\n').replace('\u2028', '\n').replace('\u2029', '\n').replace('\x00', '\ufffd')
    lines = source.split('\n')
    out: list[str] = []
    fence = None
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            out.append(line)
            if match and match[1][0] == fence[0] and len(match[1]) >= len(fence) and not match[2].strip():
                fence = None
            i += 1
            continue
        if match and not (match[1][0] == '`' and '`' in match[2]):
            fence = match[1]
            out.append(line)
            i += 1
            continue
        # Only contiguous pipe rows containing an explicit Pixiv ^ cell marker.
        if line.startswith('|') and line.endswith('|'):
            j = i
            rows = []
            while j < len(lines) and lines[j].startswith('|') and lines[j].endswith('|'):
                rows.append(re.split(r'(?<!\\)\|', lines[j][1:-1]))
                j += 1
            if any(cell.lstrip().startswith('^') for row in rows for cell in row):
                width = max(map(len, rows))
                if out and out[-1].strip():
                    out.append('')
                out.extend(['|' + '|'.join([' '] * width) + '|', '|' + '|'.join([' --- '] * width) + '|'])
                for row in rows:
                    cells = []
                    for cell in row:
                        cell = cell.strip()
                        cells.append('**' + _inline(cell[1:]) + '**' if cell.startswith('^') else _inline(cell))
                    out.append('| ' + ' | '.join(cells + [''] * (width - len(cells))) + ' |')
                out.append('')
                i = j
                continue
        heading = re.match(r'^(\*{1,6})([^*\s].*?)\s*$', line)
        if heading and heading[1] not in heading[2]:
            if out and out[-1].strip():
                out.append('')
            out.extend(['#' * len(heading[1]) + ' ' + _inline(heading[2]), ''])
        else:
            line = re.sub(r'^(-{1,6})(?=[^\s-])', lambda m: '  ' * (len(m[1]) - 1) + '- ', line)
            out.append(_inline(line))
        i += 1
    return '\n'.join(out)


def extract_source(source: str, title: str = '') -> dict:
    """Accept raw source or the panel's Title/Body copy format; retain structure."""
    if len(source) > MAX_SOURCE_LENGTH:
        raise ValueError('Pixiv source exceeds 200000 characters')
    source = source.replace('\r\n', '\n').replace('\r', '\n').replace('\u2028', '\n').replace('\u2029', '\n')
    envelope = re.match(r'^Title: ([^\n]+)\n[\s\S]*?\nBody:\n', source)
    if envelope:
        title = title.strip() or envelope[1].strip()
        source = source[envelope.end():]
    body = pixiv_to_markdown(source)
    found = []
    fence = None
    lines = body.split('\n')
    for index, line in enumerate(lines):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker and not (marker[1][0] == '`' and '`' in marker[2]):
            fence = marker[1]
            continue
        heading = re.match(r'^(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$', line)
        if heading:
            found.append({'line': index, 'level': len(heading[1]), 'heading': heading[2]})
    ends = [len(lines)] * len(found)
    stack = []
    for index, item in enumerate(found):
        while stack and found[stack[-1]]['level'] >= item['level']:
            ends[stack.pop()] = item['line']
        stack.append(index)
    sections = []
    for index, item in enumerate(found):
        end = ends[index]
        sections.append({'value': str(index), 'label': '#' * item['level'] + ' ' + item['heading'],
                         'body': '\n'.join(lines[item['line'] + 1:end]).strip()})
    fallback = found[0]['heading'] if found else next((line.strip() for line in lines if line.strip()), '')
    return {'title': title.strip() or fallback, 'body': body, 'headings': [{'level': n['level'], 'heading': n['heading']} for n in found], 'sections': sections}
