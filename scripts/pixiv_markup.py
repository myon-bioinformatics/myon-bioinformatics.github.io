"""Conservative Pixiv-source wrapper: the 🔌 MCP 実験室 panel's copy format and its heading sections. Stdlib only.

The conversion itself is markdown.py's ``pixiv_to_markdown`` (md-market, pinned in pyproject.toml); this adds the panel's
``Title:`` / ``Body:`` envelope and the sections it offers. Use only for known Pixiv source, not for autodetecting arbitrary
Markdown. The browser mirror is _src/tools/mcp/pixiv-markup.js (published with the lab); shared fixtures enforce parity.
"""
from __future__ import annotations
import re

from markdown import pixiv_to_markdown   # ✍️ md-market

__all__ = ['extract_source', 'pixiv_to_markdown']


def extract_source(source: str, title: str = '') -> dict:
    """Accept raw source or the panel's Title/Body copy format; retain structure."""
    if len(source) > 200000:
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
