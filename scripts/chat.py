#!/usr/bin/env python3
"""💬 The portfolio's cross-repo chat bot: one Markdown reply per message, made by the fleet's own single-file modules.

The same file runs in CPython (tests, ``python scripts/chat.py "/flow 入力 > 圧縮 > 出力"``) and in the chat page
(tools/demos/chat.html), where Pyodide loads it next to markdown.py (md-market), ascii_artist.py and cli_args.py — the
commits pinned in pyproject.toml's pages group. What it knows about the other repositories is ``media/chat/index.json``,
written at deploy time by ``project_pages.py --record-chat``: every JSON / JSONL file of every active repository at its
commit, and the tools mcp-toolcall-lab advertises. TalkCompress's shorthand compressor is fetched on first use.

``respond(text)`` → Markdown, ``reply_html(text)`` → HTML (markdown.py escapes raw HTML), ``configure(index, base)``
for the page. Every command is a cli_args subparser, so a typo gets "maybe you meant".
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

import ascii_artist as aa
import cli_args
import markdown as md

OWNER = 'myon-bioinformatics'
MODULES = ('markdown', 'ascii_artist', 'cli_args')            # 📦 the page writes these next to this file in Pyodide
PYODIDE = 'https://cdn.jsdelivr.net/npm/pyodide@314.0.8/'     # 🐍 the page's Python (CPython 3.14, stdlib only)
SHOW_MAX = 2 * 1024 ** 2   # 👀 bytes /show reads
FIND_ROWS = 20
# 🗂 TalkCompress's shorthand compressor (layer 3) and the files it imports or reads, in the repository's layout
TALKCOMPRESS = ('shared/__init__.py', 'shared/ledger.py', 'shared/lex_policy.py', 'shared/romance_gate.py',
                'shared/unicode_boundary.py', 'ShorthandSessionEdge/shorthand_session_edge.py',
                'ShorthandSessionEdge/ledger/conventions.json')
KINDS = {'onto': '🧬', 'jsonl': '🧾', 'lock': '🔒', 'config': '⚙️', 'test': '🧪', 'data': '📊'}
_ONTO = {'ontology', 'taxonomy', 'kgraph', 'graph', 'graphs', 'knowledge', 'triples', 'owl', 'rdf', 'skos', 'otl', 'relations'}
_CONFIG = {'package.json', 'tsconfig.json', 'renovate.json', 'deno.json', 'jsconfig.json', 'biome.json', '.eslintrc.json',
           'manifest.json', 'devcontainer.json', 'settings.json', 'launch.json', 'extensions.json', 'tasks.json'}

# name: (icon, arguments, what it does, examples) — the help table, the parser, the page's chips and its 📇 index come from here
COMMANDS = {
    'help': ('❓', '', 'コマンドの一覧', ('/help',)),
    'md': ('📝', 'TEXT', 'Markdown を表示し、見出し・リンク・コードを数える（markdown.py）', ('/md # 見出し\n\n- [x] **太字** と `code`',)),
    'table': ('📊', 'CSV', 'CSV を Markdown の表と罫線の表に（markdown.py・ascii_artist）', ('/table 道具,行数;markdown,7284;cli_args,1288',)),
    'ascii': ('🎨', 'TEXT', '大きな文字（ascii_artist の banner）', ('/ascii HELLO',)),
    'box': ('📦', 'TEXT', '文字を枠で囲む（ascii_artist）', ('/box cross-repo chat',)),
    'flow': ('🔀', 'A > B > C', '流れ図を ASCII と Mermaid に（A, B > C で合流）', ('/flow 入力, 履歴 > 圧縮 > 出力',)),
    'compress': ('🗂', 'TEXT', '会話を短く（TalkCompress の略語・合意台帳）と、LLM 出力の整理（markdown.py）',
                 ('/compress As soon as possible, please send me the report. Thank you very much!',)),
    'mcp': ('🔌', '[TOOL {JSON}]', 'MCP の道具呼び出しを確かめる（mcp-toolcall-lab が広告する道具と引数の型）',
            ('/mcp', '/mcp find_municipalities {"query": "Exampleville"}', '/mcp find_municipalities {"query": 3}',
             '/mcp query_unadvertised_tool {}')),
    'find': ('🔎', 'WORDS [--repo R] [--kind K]', 'リポジトリ横断で JSON / JSONL を探す（K: ' + ' '.join(KINDS) + '）',
             ('onto', '/find --kind onto', '/find --kind jsonl --repo Aoi', 'TaxOntOy')),
    'show': ('👀', 'REPO/PATH', 'JSON / JSONL の中身を表にまとめる（そのコミットの raw を読む）', ('/show TaxOntOy/otl-relations.json',)),
}
TYPOS = ('/flwo a > b', '/find --kidn onto', '/find --kind ont')    # ⌨️ what cli_args answers with "maybe you meant"
_STATE = {'index': None, 'base': '', 'fetch': None, 'talkcompress': None}


def configure(index=None, base: str = '', fetch=None) -> None:
    """For the page: the recorded index (dict or JSON text), the URL of media/chat/ and an optional fetch(url) -> text."""
    _STATE.update(index=json.loads(index) if isinstance(index, str) else index, base=base, fetch=fetch)


def _fetch(url: str) -> str:
    """Text at ``url``; an HTTP error raises OSError. In the page a synchronous XMLHttpRequest (Pyodide), else urllib."""
    if 'pyodide' in sys.modules:
        from js import XMLHttpRequest
        request = XMLHttpRequest.new()
        request.open('GET', url, False)
        request.send(None)
        if request.status != 200:
            raise OSError(f'HTTP {request.status}: {url}')
        return request.responseText
    import urllib.request
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode('utf-8')


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
        yield err


def parser() -> argparse.ArgumentParser:
    """The commands as cli_args subparsers: typos of a command, an option or a --kind get "maybe you meant"."""
    top = cli_args.make_parser(prog='💬', exit_on_error=False, add_help=False)
    sub = top.add_subparsers(dest='command', required=True)
    for name, (_, _, what, _) in COMMANDS.items():
        command = sub.add_parser(name, help=what, add_help=False, exit_on_error=False)
        if name == 'find':
            command.add_argument('words', nargs='*')
            command.add_argument('--repo')
            command.add_argument('--kind', choices=list(KINDS))
    return top


def _parse(argv: list[str], top: argparse.ArgumentParser | None = None) -> tuple[argparse.Namespace | None, str]:
    """Parsed args, or the parser's message (with its "maybe you meant") when the argv does not parse."""
    with _quiet() as err:
        try:
            return (top or parser()).parse_args(argv), ''
        except argparse.ArgumentError as exc:
            return None, str(exc)
        except SystemExit:
            lines = [line for line in err.getvalue().splitlines() if line.strip()]
            return None, lines[-1].split('error: ', 1)[-1] if lines else 'usage'


def _code(text: str, lang: str = 'text') -> str:
    return md.code_block(text.rstrip('\n'), lang=lang).rstrip('\n')


def _cell(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = text.replace('\n', ' ')
    return text if len(text) <= 60 else text[:59] + '…'


def _kv(rows) -> str:
    return ' · '.join(f'{key} **{value}**' for key, value in rows)


def help_reply() -> str:
    rows = [[icon, f'`/{name}{" " + args if args else ""}`', what] for name, (icon, args, what, _) in COMMANDS.items()]
    return '\n\n'.join(['## 💬 コマンド', md.table([' ', 'コマンド', 'すること'], rows),
                        '🔎 `/` なしの文は横断検索（例: `onto`、`Aoi jsonl`、`TaxOntOy relations`）· ⌨️ 打ち間違いは cli_args が「もしかして」']).strip()


def md_reply(text: str) -> str:
    counts = [('🧭 見出し', len(md.extract_sections(text))), ('🔗 リンク', len(md.extract_links(text))),
              ('💻 コード', len(md.extract_code_blocks(text)))]
    return text.strip() + '\n\n---\n\n' + ' · '.join(f'{k} {v}' for k, v in counts)


def table_reply(text: str) -> str:
    csv_text = text.replace(';', '\n').strip()
    rows = [line.split(',') for line in csv_text.splitlines() if line.strip()]
    if len(rows) < 2:
        return '📊 `/table 見出し1,見出し2` の次の行（または `;` の後）に値を'
    return md.csv_to_markdown_table(csv_text, align=True).strip() + '\n\n' + _code(
        aa.render_table(rows[1:], headers=rows[0], style='rounded'))


def ascii_reply(text: str) -> str:
    return _code(aa.banner(text.strip() or 'HI', fallback='?'))


def box_reply(text: str) -> str:
    return _code(aa.generate_box(text.strip() or '💬', style='rounded'))


def flow_reply(text: str) -> str:
    parts = [part.strip() for part in re.split(r'\s*(?:>|→|->)\s*', text) if part.strip()]
    if len(parts) < 2:
        return '🔀 `/flow A > B > C`（2つ以上を `>` でつなぐ）'
    sources = [s.strip() for s in parts[0].split(',') if s.strip()]
    spec = {'title': text.strip()[:120], 'sources_label': '📥', 'sources': [{'title': s} for s in sources[:8]],
            'steps': [{'title': s} for s in parts[1:9]]}
    return _code(aa.flow([' + '.join(sources), *parts[1:]])) + '\n\n' + aa.flow_mermaid(spec).strip()


def _talkcompress(fetch, base: str):
    """TalkCompress's shorthand_session_edge: importable (a checkout on sys.path) or fetched from ``base``talkcompress/
    (all files first, so a failed fetch leaves nothing half written on the path)."""
    if _STATE['talkcompress'] is None:
        try:
            import shorthand_session_edge
        except ImportError:
            texts = {name: fetch(f'{base}talkcompress/{name}') for name in TALKCOMPRESS}
            root = Path('/tmp/talkcompress')
            for name, text in texts.items():
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding='utf-8')
            sys.path[:0] = [p for p in (str(root), str(root / 'ShorthandSessionEdge')) if p not in sys.path]
            import shorthand_session_edge
        _STATE['talkcompress'] = shorthand_session_edge
    return _STATE['talkcompress']


def compress_reply(text: str, fetch=None, base: str | None = None, commit: str | None = None) -> str:
    text = text.strip()
    if not text:
        return '🗂 `/compress 文`'
    out = []
    try:
        short = _talkcompress(fetch or _STATE['fetch'] or _fetch, _STATE['base'] if base is None else base).compress(text)
        at = f' @ {commit[:7]}' if commit else ''
        out += [f'### 🗂 TalkCompress（ShorthandSessionEdge{at}）', _code(short),
                _kv([('📏', f'{len(text)} → {len(short)} 文字'), ('📉', f'{len(short) / len(text):.0%}')])]
    except Exception as exc:      # ⏸ not recorded in this build, or offline
        out.append(f'⏸ TalkCompress を読めない（{type(exc).__name__}）')
    compact = md.compact_llm_output(text)
    if compact.strip() != text:
        out += ['### 🧹 markdown.py compact_llm_output', _code(compact)]
    return '\n\n'.join(out)


def _check(schema: dict, value, path: str = 'arguments') -> list[str]:
    """The JSON Schema subset the lab's tools use: type, required, properties, additionalProperties, enum, items."""
    kinds = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'object': dict, 'array': list, 'null': type(None)}
    want = schema.get('type')
    if want in kinds and (not isinstance(value, kinds[want]) or (want in ('integer', 'number') and isinstance(value, bool))):
        return [f'{path}: {want} ではない（{type(value).__name__}）']
    problems = []
    if 'enum' in schema and value not in schema['enum']:
        problems.append(f'{path}: {schema["enum"]} のどれでもない')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        problems += [f'{path}.{key}: 必須' for key in schema.get('required', []) if key not in value]
        if schema.get('additionalProperties') is False:
            problems += [f'{path}.{key}: 広告にない引数' for key in value if key not in props]
        for key, item in value.items():
            if key in props:
                problems += _check(props[key], item, f'{path}.{key}')
    if isinstance(value, list) and isinstance(schema.get('items'), dict):
        for i, item in enumerate(value):
            problems += _check(schema['items'], item, f'{path}[{i}]')
    return problems


def mcp_reply(text: str, index: dict | None) -> str:
    tools = {tool['name']: tool for tool in (index or {}).get('tools', [])}
    if not tools:
        return '⏸ このビルドは mcp-toolcall-lab の道具を記録していない'
    name, _, raw = text.strip().partition(' ')
    if not name:
        rows = [[f'`{t["name"]}`', ', '.join(t.get('parameters', {}).get('required', [])) or '—', _cell(t.get('description', ''))]
                for t in tools.values()]
        return '## 🔌 広告されている道具\n\n' + md.table(['道具', '必須', '説明'], rows).strip() + \
            '\n\n`/mcp 道具 {"引数": "値"}` で、その呼び出しを出してよいかを確かめる'
    if name not in tools:
        top = cli_args.make_parser(prog='🔌', exit_on_error=False, add_help=False)
        top.add_argument('tool', choices=list(tools))
        _, hint = _parse([name], top)
        maybe = re.search(r"maybe you meant '([^']+)'", hint)
        return '\n\n'.join(['❌ 広告されていない道具 → `tool_calls` を出さずに断る（lab の fictional_tool_reject と同じ）',
                            f'❓ もしかして `{maybe.group(1)}`' if maybe else '', '`/mcp` で一覧']).replace('\n\n\n\n', '\n\n')
    try:
        arguments = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        return f'❌ 引数が JSON ではない（{exc.msg}, {exc.pos} 文字目）'
    problems = _check(tools[name].get('parameters', {'type': 'object'}), arguments)
    if problems:
        return '❌ 引数が広告と合わない\n\n' + md.bullet_list(problems).strip()
    call = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': name, 'arguments': arguments}}
    return '✅ 広告どおり → この呼び出しを送ってよい\n\n' + _code(json.dumps(call, ensure_ascii=False, indent=2), 'json')


def kinds_of(repo: str, path: str) -> list[str]:
    """🏷 The kinds of one recorded file (``KINDS``): onto, jsonl, lock, config, test, else data."""
    name = path.rsplit('/', 1)[-1].lower()
    found = []
    words = re.split(r'[^a-z0-9]+', path.lower())
    if 'onto' in repo.lower() or any(w.startswith('onto') or w in _ONTO for w in words):
        found.append('onto')
    if name.endswith(('.jsonl', '.ndjson')):
        found.append('jsonl')
    if 'lock' in name:
        found.append('lock')
    if name in _CONFIG or path.startswith('.') or '/.' in path:
        found.append('config')
    if re.search(r'(^|/)(tests?|fixtures?|__snapshots__)/', path):
        found.append('test')
    return found or ['data']


def find(index: dict, words=(), repo: str | None = None, kind: str | None = None) -> list[tuple[str, str, int]]:
    """Recorded files whose ``repo/path`` holds every word (case ignored), best first: file name hits, data, short paths."""
    words = [w.lower() for w in words if w]
    hits = []
    for name, path, size in index.get('files', []):
        where = f'{name}/{path}'.lower()
        if repo and name.lower() != repo.lower():
            continue
        if any(w not in where for w in words) or (kind and kind not in kinds_of(name, path)):
            continue
        base = path.rsplit('/', 1)[-1].lower()
        score = (-sum(w in base for w in words), kinds_of(name, path) == ['config'], path.count('/'), where)
        hits.append((score, (name, path, size)))
    return [hit for _, hit in sorted(hits)]


def _size(size: int) -> str:
    return f'{size} B' if size < 1024 else f'{size / 1024:.1f} KB' if size < 1024 ** 2 else f'{size / 1024 ** 2:.1f} MB'


def _blob(index: dict, name: str, path: str) -> str:
    return f'https://github.com/{index.get("owner", OWNER)}/{name}/blob/{index["commits"].get(name, "HEAD")}/{quote(path)}'


def find_reply(index: dict | None, words=(), repo=None, kind=None) -> str:
    if not index or not index.get('files'):
        return '⏸ このビルドはリポジトリ横断の索引を記録していない'
    hits = find(index, words, repo, kind)
    label = ' '.join([*words, *([f'📦 {repo}'] if repo else []), *([f'{KINDS[kind]} {kind}'] if kind else [])]) or 'すべて'
    if not hits:
        names = {name.lower(): name for name, _, _ in index['files']}
        near = [names[n] for n in names if any(w.lower() in n or n in w.lower() for w in words)][:5]
        return f'🔎 {label}: 0 件' + (f'\n\n📦 リポジトリ: {", ".join(near)} → `/find --repo {near[0]}`' if near else '')
    repos = sorted({name for name, _, _ in hits}, key=str.lower)
    rows = [[f'📦 {name}', f'[{path}]({_blob(index, name, path)})', _size(size), ''.join(KINDS[k] for k in kinds_of(name, path))]
            for name, path, size in hits[:FIND_ROWS]]
    more = f'（上位 {FIND_ROWS} 件）' if len(hits) > FIND_ROWS else ''
    return '\n\n'.join([f'🔎 {label}: {len(hits)} 件 · 📦 {len(repos)} リポジトリ{more}',
                        md.table(['リポジトリ', 'ファイル', '大きさ', '種類'], rows).strip(),
                        f'👀 `/show {hits[0][0]}/{hits[0][1]}` で中身'])


def summarize(path: str, text: str) -> str:
    """👀 JSON / JSONL as tables: top-level keys, the first records, and the size of a graph (nodes, edges, @graph)."""
    if path.lower().endswith(('.jsonl', '.ndjson')):
        records, bad = [], 0
        for line in text.splitlines():
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    bad += 1
        head = _kv([('🧾 行', len(records)), *([('⚠️ 読めない行', bad)] if bad else [])])
        return head + '\n\n' + _records(records)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return f'⚠️ JSON として読めない（{exc.msg}, {exc.lineno} 行目）'
    if isinstance(data, list):
        return _kv([('📚 配列', f'{len(data)} 件')]) + '\n\n' + _records(data)
    if not isinstance(data, dict):
        return _kv([('🔹 値', _cell(data))])
    rows = [[f'`{key}`', type(value).__name__, _cell(len(value) if isinstance(value, (list, dict)) else value)]
            for key, value in list(data.items())[:30]]
    graph = [(k, len(data[k])) for k in ('nodes', 'edges', 'links', '@graph', 'triples', 'classes', 'terms')
             if isinstance(data.get(k), (list, dict))]
    out = [_kv([('🔑 キー', len(data)), *[(f'🧬 {k}', n) for k, n in graph]]),
           md.table(['キー', '型', '中身・数'], rows).strip()]
    if len(data) > 30:
        out.append(f'…ほか {len(data) - 30} キー')
    return '\n\n'.join(out)


def _records(records: list) -> str:
    objects = [r for r in records[:5] if isinstance(r, dict)]
    if not objects:
        return _code('\n'.join(_cell(r) for r in records[:5])) if records else ''
    keys = list(dict.fromkeys(k for r in objects for k in r))[:8]
    return md.table(keys, [[_cell(r.get(k, '')) for k in keys] for r in objects]).strip()


def show_reply(index: dict | None, target: str, fetch=None) -> str:
    if not index or not index.get('files'):
        return '⏸ このビルドはリポジトリ横断の索引を記録していない'
    target = re.sub(r'^https://github\.com/[^/]+/', '', target.strip()).replace('/blob/', '/', 1)
    name, _, path = target.partition('/')
    rows = {(n.lower(), p): (n, p, s) for n, p, s in index['files']}
    found = rows.get((name.lower(), path))
    if found is None and '/' in path:            # a pasted blob URL: REPO/COMMIT/PATH
        found = rows.get((name.lower(), path.split('/', 1)[1]))
    if found is None:
        near = find(index, [path.rsplit('/', 1)[-1]] if path else [name])
        return f'❓ 記録にない: `{target}`' + (f'\n\n🔎 近いもの: `/show {near[0][0]}/{near[0][1]}`' if near else '')
    name, path, size = found
    if size > SHOW_MAX:
        return f'🐘 {_size(size)} は大きすぎる（{_size(SHOW_MAX)} まで）→ [GitHub で開く]({_blob(index, name, path)})'
    commit = index['commits'].get(name, 'HEAD')
    url = f'https://raw.githubusercontent.com/{index.get("owner", OWNER)}/{name}/{commit}/{quote(path)}'
    try:
        text = (fetch or _STATE['fetch'] or _fetch)(url)
    except Exception as exc:
        return f'⏸ 読めない（{type(exc).__name__}）→ [GitHub で開く]({_blob(index, name, path)})'
    return '\n\n'.join([f'### 👀 [{name}/{path}]({_blob(index, name, path)})',
                        f'📦 {name} @ {commit[:7]} · {_size(size)} · ' + ''.join(KINDS[k] for k in kinds_of(name, path)),
                        summarize(path, text)])


def chat_reply(text: str, index: dict | None) -> str:
    """Text without a command searches: a kind's name (onto, jsonl, …; オントロジー) filters by kind, the other words must all
    appear in ``repo/path``; a greeting gets the help."""
    words = re.findall(r'[A-Za-z0-9_.@-]{2,}|[ぁ-んァ-ヶー一-龠々]{2,}', text)
    if not words or re.fullmatch(r'\s*(hi|hello|help|こんにちは|ヘルプ|使い方)\W*', text, re.I):
        return help_reply()
    aliases = {**{k: k for k in KINDS}, 'オントロジー': 'onto', 'ontology': 'onto', 'ndjson': 'jsonl', 'テスト': 'test', '設定': 'config'}
    kind = next((aliases[w.lower()] for w in words if w.lower() in aliases), None)
    rest = [w for w in words if w.lower() not in aliases and w.lower() != 'json']
    reply = find_reply(index, rest, None, kind)
    if ': 0 件' in reply and len(rest) > 1:             # every word did not fit: the words that find something on their own
        loose = [w for w in rest if find(index or {}, [w], None, kind)]
        if loose:
            reply = find_reply(index, loose, None, kind)
    return reply


def respond(text: str, *, index: dict | None = None, fetch=None) -> str:
    """💬 One reply in Markdown for one message."""
    index = _STATE['index'] if index is None else index
    text = (text or '').strip()
    if not text.startswith('/'):
        return chat_reply(text, index)
    head, rest = (re.split(r'\s', text[1:], maxsplit=1) + [''])[:2]
    name = head.lower()
    args, problem = _parse([name, *(rest.split() if name == 'find' else [])])
    if args is None:
        return '\n\n'.join(part for part in [f'❓ `/{head}`: {problem}', _maybe(problem), '`/help` で一覧'] if part)
    if name == 'help':
        return help_reply()
    if name == 'find':
        return find_reply(index, args.words, args.repo, args.kind)
    if name == 'show':
        return show_reply(index, rest, fetch)
    if name == 'mcp':
        return mcp_reply(rest, index)
    if name == 'compress':
        return compress_reply(rest, fetch, commit=(index or {}).get('commits', {}).get('TalkCompress'))
    return {'md': md_reply, 'table': table_reply, 'ascii': ascii_reply, 'box': box_reply, 'flow': flow_reply}[name](rest)


def _maybe(problem: str) -> str:
    """⌨️ The parser's suggestion as what to type: a command, an option, or an option with the choice it meant."""
    found = re.search(r"(?:maybe you meant|did you mean) '([^']+)'", problem)
    if not found:
        return ''
    option = re.match(r'argument (--[a-z-]+):', problem)
    hint = found.group(1)
    typed = hint if hint.startswith('-') else f'{option.group(1)} {hint}' if option else f'/{hint}'
    return f'⌨️ もしかして `{typed}`'


def reply_html(text: str, **kwargs) -> str:
    """💬 One reply as HTML (markdown.py's renderer, raw HTML escaped)."""
    return md.markdown_to_html(respond(text, **kwargs))


def main(argv=None) -> int:
    cli = cli_args.make_parser(description='💬 one reply (Markdown) per message, as in the chat page')
    cli.add_argument('message', nargs='+', help='the message, e.g. "/flow a > b"')
    cli.add_argument('--index', type=Path, help='a recorded media/chat/index.json (for /find, /show, /mcp)')
    cli.add_argument('--talkcompress', type=Path, help='a TalkCompress checkout (for /compress)')
    cli.add_argument('--html', action='store_true', help='print the HTML the page shows')
    args = cli.parse_args(argv)
    if args.talkcompress:
        sys.path[:0] = [str(args.talkcompress), str(args.talkcompress / 'ShorthandSessionEdge')]
    index = json.loads(args.index.read_text(encoding='utf-8')) if args.index else None
    text = ' '.join(args.message)
    print(reply_html(text, index=index) if args.html else respond(text, index=index))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
