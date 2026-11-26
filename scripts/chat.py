#!/usr/bin/env python3
"""💬 The portfolio's cross-repo chat bot: one Markdown reply per message, made by the fleet's own single-file modules.

The same file runs in CPython (tests, ``python scripts/chat.py "/flow 入力 > 圧縮 > 出力"``) and in the chat page
(tools/demos/chat.html), where Pyodide loads it next to markdown.py (md-market), ascii_artist.py, cli_args.py,
ontautology.py (🧬 /onto, 🎯 /guess) and olnm.py (🧷 /olnm) — the commits pinned in pyproject.toml's pages group. What it knows about the other repositories is ``media/chat/index.json``,
written at deploy time by ``project_pages.py --record-chat``: every JSON / JSONL file of every active repository at its
commit, and the tools mcp-toolcall-lab advertises. TalkCompress's shorthand compressor is fetched on first use.

``respond(text)`` → Markdown, ``reply_html(text)`` → HTML (markdown.py escapes raw HTML), ``configure(index, base)``
for the page. Every command is a cli_args subparser, so a typo gets "maybe you meant".
"""
from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import json
import math
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote

import ascii_artist as aa
import cli_args
import markdown as md
import ontautology as otl

OWNER = 'myon-bioinformatics'
MODULES = ('markdown', 'ascii_artist', 'cli_args', 'ontautology', 'olnm')   # 📦 the page writes these next to this file in Pyodide
# 🐍 the page's Python (Pyodide, CPython 3.14, stdlib only), 🤖 llama.cpp in WebAssembly (wllama; WebGPU when the browser has it)
# and the GGUF /ask loads once (then the browser keeps it): GitHub Pages sends no COOP/COEP, so the CPU runs one thread
RUNTIME = {'pyodide': 'https://cdn.jsdelivr.net/npm/pyodide@314.0.8/',
           'wllama': 'https://cdn.jsdelivr.net/npm/@wllama/wllama@4.0.0/esm/',
           'model': 'https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/resolve/main/Qwen3.5-0.8B-Q4_0.gguf'}
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
    'onto': ('🧬', '[WORD | 要素 + 要素]', 'オントロジー（OnTautoLogy）: 〇〇を〇〇たらしめる要素と、似たものとの違い。要素を + でつなぐと逆引き',
             ('/onto ギター', '/onto 撥弦 + フレット', '/onto')),
    'guess': ('🎯', '[y | n | ?]', '当てっこ: 台帳から思い浮かべたものを、要素の質問（はい・いいえ）で当てる（OnTautoLogy の台帳）',
              ('/guess',)),
    'olnm': ('🧷', '[ls | grep | like | show | calc | sections] …', '端末のワンライナー集 OLNM を動かす（探す・読む・もしかして・電卓）',
             ('/olnm like uvtets', '/olnm show gp', '/olnm calc 6 mul 7', '/olnm grep json')),
    'ask': ('🤖', 'TEXT', '小さな LLM に聞く（llama.cpp をページの中で。初回だけモデルを読む）。質問が名指すリポジトリの要約・台帳の概念を添える', ('/ask オントロジーの台帳はどのリポジトリにある？',)),
}
TYPOS = ('/flwo a > b', '/find --kidn onto', '/find --kind ont')    # ⌨️ what cli_args answers with "maybe you meant"
_STATE = {'index': None, 'base': '', 'fetch': None, 'talkcompress': None, 'concepts': None, 'guess': None}


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


# ── 🧬 /onto and 🎯 /guess: OnTautoLogy's concept ledgers (ontautology-concepts/1, from any repository) ──────────────────

def concepts(index: dict | None = None, fetch=None) -> dict:
    """🧬 Every concept ledger the index records (``concepts-*.json`` with OnTautoLogy's schema, in any repository), merged
    into one corpus and read once at the recorded commits: {'concepts': {...}, 'similar': [...], 'sources': [...]}."""
    index = _STATE['index'] if index is None else index
    if not index or not index.get('files'):
        return {}
    key = (json.dumps(index.get('commits', {}), sort_keys=True), id(fetch))
    if _STATE['concepts'] and _STATE['concepts'][0] == key:
        return _STATE['concepts'][1]
    corpus = {'schema': otl.CONCEPT_SCHEMA, 'concepts': {}, 'similar': [], 'sources': [], 'names': {}}
    for name, path, size in index['files']:
        if not re.search(r'(^|/)concepts[-_][^/]*\.json$', path) or size > SHOW_MAX:
            continue
        commit = index['commits'].get(name, 'HEAD')
        try:
            data = json.loads((fetch or _STATE['fetch'] or _fetch)(
                f'https://raw.githubusercontent.com/{index.get("owner", OWNER)}/{name}/{commit}/{quote(path)}'))
        except Exception:
            continue
        if not isinstance(data, dict) or data.get('schema') != otl.CONCEPT_SCHEMA or not isinstance(data.get('concepts'), dict):
            continue
        for concept, body in data['concepts'].items():
            corpus['concepts'].setdefault(concept, body)
        corpus['similar'] += data.get('similar', [])
        for concept, called in (data.get('names') or {}).items():
            corpus['names'].setdefault(concept, []).extend(c for c in called if isinstance(c, str))
        corpus['sources'].append(f'{name}/{path}@{commit[:7]}')
    _STATE['concepts'] = (key, corpus)
    return corpus


def _elements(body) -> list:
    """A ledger entry's elements: the ledger writes {"id", "elements"} or the bare list; unobserved is []."""
    elements = body.get('elements') if isinstance(body, dict) else body
    return list(elements) if isinstance(elements, list) else []


def _key(word: str) -> str:
    """How a name is looked up: casefolded, without the emoji variation selector (❤️ is ❤)."""
    return word.replace('\ufe0f', '').strip().casefold()


def aliases(corpus: dict) -> dict[str, list[str]]:
    """🏷 What each concept is also called → the concepts called so (more than one when a name is shared: 🦅 is 楽天 and
    ソフトバンク): its name and the ledger's names whose kind is a name or a reading (略称:中日, 英名:Guitar, 別名:ヒト, 読み:しゃけ,
    絵文字略称:🐯 — not 同音語 or 名前の由来). A concept's own name is only ever itself."""
    called = {_key(name): [name] for name in corpus.get('concepts', {})}
    for concept, names in corpus.get('names', {}).items():
        for kind, _, alias in (n.partition(':') for n in names):
            key = _key(alias)
            if concept in corpus['concepts'] and key and (kind.endswith(('名', '称')) or kind == '読み') \
                    and key not in {_key(name) for name in corpus['concepts']} and concept not in called.setdefault(key, []):
                called[key].append(concept)
    return called


def icon(corpus: dict, concept: str) -> str:
    """The concept's first 絵文字略称 and a space (its face in replies: 🐯 阪神タイガース), or ''."""
    marks = [n.split(':', 1)[1].strip() for n in corpus.get('names', {}).get(concept, []) if n.startswith('絵文字略称:')]
    return f'{marks[0]} ' if marks else ''


def _ledger(corpus: dict) -> str:
    return f'📚 台帳: {" · ".join(corpus["sources"])}（OnTautoLogy の concepts-*.json）'


def _few(items, n: int = 4) -> str:
    items = list(items)
    return '・'.join(items[:n]) + (f' …ほか {len(items) - n}' if len(items) > n else '') if items else '—'


def _of(definition: dict, bold: str = '') -> str:
    """📐 "genus のうち、differentia のもの"; only "differentia のもの" when it shares nothing with all that is like it."""
    genus = f'{bold}{_few(definition["genus"], 6)}{bold} のうち、' if definition['genus'] else ''
    return f'{genus}{bold}{_few(definition["differentia"], 4)}{bold} のもの'


def _splitter(corpus: dict, names, asked=()) -> str | None:
    """The element that halves ``names`` best (a yes/no question worth the most), skipping ``asked``; None when none splits."""
    names = list(names)
    elements = sorted({e for n in names for e in _elements(corpus['concepts'][n])} - set(asked))
    has = {e: sum(e in _elements(corpus['concepts'][n]) for n in names) for e in elements}
    useful = [e for e in elements if 0 < has[e] < len(names)]
    return min(useful, key=lambda e: (abs(2 * has[e] - len(names)), e)) if useful else None


def onto_reply(text: str, index: dict | None = None, fetch=None) -> str:
    """🧬 A concept: what makes it itself (genus + differentia, OnTautoLogy's define_concepts) and how it differs from what is
    like it; elements joined with + : which concepts have them all (roundtrip_elements); nothing: the ledger."""
    corpus = concepts(index, fetch)
    if not corpus.get('concepts'):
        return '⏸ 概念の台帳（OnTautoLogy の concepts-*.json）をこのビルドの索引から読めない'
    names = list(corpus['concepts'])
    text, said = text.strip(), ''
    called = aliases(corpus).get(_key(text), []) if text not in corpus['concepts'] else []
    if len(called) > 1:
        return '\n\n'.join([f'🏷 **{text}** は {len(called)} つ: ' + ' · '.join(f'`/onto {c}`' for c in called), _ledger(corpus)])
    if called:
        said, text = f'🏷 {text} → **{called[0]}**', called[0]
    if not text:
        return '\n\n'.join([f'🧬 **{len(names)}** 概念 · 🤝 似ている組 **{len(corpus["similar"])}**', ' · '.join(names),
                            '例: `/onto ギター`（〇〇を〇〇たらしめるもの）· `/onto 撥弦 + フレット`（要素から逆引き）· `/guess`（当てっこ）',
                            _ledger(corpus)])
    if text not in corpus['concepts']:
        words = [w for w in re.split(r'\s*\+\s*|\s+', text) if w]
        known = {e for body in corpus['concepts'].values() for e in _elements(body)}
        if all(w in known for w in words):
            found = otl.roundtrip_elements(corpus, words)
            matched = found['matched']
            head = f'🔁 **{" + ".join(found["query"])}** を全部もつもの: '
            if found['verdict'] == 'unique':
                return head + f'✅ **{matched[0]}** だけ → `/onto {matched[0]}`'
            more = _splitter(corpus, matched, words) if matched else None
            return '\n\n'.join(part for part in [
                head + (f'⚠️ {len(matched)} つ（{_few(matched, 8)}）' if matched else '🫥 台帳にない'),
                f'➕ 見分けるなら: `/onto {" + ".join(words)} + {more}`' if more else ''] if part)
        near = difflib.get_close_matches(text, names, n=3, cutoff=0.3) + difflib.get_close_matches(text, sorted(known), n=3, cutoff=0.6)
        return '\n\n'.join(part for part in [f'❓ 台帳にない: **{text}**', f'⌨️ もしかして: {" · ".join(f"`/onto {n}`" for n in near)}' if near else '',
                                             '`/onto` で台帳の一覧（要素は + でつなぐと逆引き）'] if part)
    result = otl.define_concepts(corpus, [text])['concepts'][text]
    if not result['elements_observed']:
        return f'### 🧬 {icon(corpus, text)}{text}\n\n⏸ 要素はまだ観測されていない（似たもの: {_few(result["similar"])}）'
    definition, differ = result['definition'], result['differentia']
    verdict = definition['roundtrip']['verdict']
    rows = [[f'🤝 {other}', _few(result['genus']['by_similar'][other]['common']), _few(differ['vs_similar'][other]['only_target'], 3),
             _few(differ['vs_similar'][other]['only_similar'], 3)] for other in result['similar'] if other in differ['vs_similar']]
    keys = ' · '.join('＋'.join(k) for k in differ['minimal_keys'][:5])
    return '\n\n'.join(part for part in [
        f'### 🧬 {icon(corpus, text)}{text}', said,
        f'📐 {_of(definition, "**")}'
        f'（🔁 逆引き {"✅ これだけ" if verdict == "unique" else "⚠️ " + _few(definition["roundtrip"]["matched"])}）',
        md.table(['似たもの', '🤝 共通', f'🆚 {text}だけ', '🆚 相手だけ'], rows).strip() if rows else '🤝 似たものはまだない',
        f'🔑 決め手（それだけで {text}）: {keys}' if keys else '',
        f'🧩 要素 {len(result["elements"])}: ' + ' · '.join(result['elements']),
        _ledger(corpus)] if part)


_YES, _NO, _SKIP = {'y', 'yes', 'はい', 'うん', 'o', '⭕'}, {'n', 'no', 'いいえ', 'ううん', 'x', '❌'}, {'?', '？', 'わからない', 'skip', 'パス'}


def guess_reply(text: str = '', index: dict | None = None, fetch=None) -> str:
    """🎯 Think of one concept in the ledger; each question is the element that halves what is left (y / n / ?), until one
    is left — the count against ⌈log₂ N⌉, the questions a perfect split would need."""
    corpus = concepts(index, fetch)
    if not corpus.get('concepts'):
        return '⏸ 概念の台帳（OnTautoLogy の concepts-*.json）をこのビルドの索引から読めない'
    answer, game = text.strip().lower(), _STATE['guess']
    if answer in ('stop', 'やめる'):
        _STATE['guess'] = None
        return '🎯 おしまい（`/guess` でもう一度）'
    observed = [n for n, body in corpus['concepts'].items() if _elements(body)]
    if game is None or answer in ('', 'new', 'again', 'もう一回'):
        game = _STATE['guess'] = {'left': observed, 'asked': [], 'q': None, 'n': len(observed)}
        intro = f'🎯 台帳の {len(observed)} 個から 1 つ思い浮かべて（{_few(observed, 6)}）。はい＝`y`・いいえ＝`n`・わからない＝`?`'
    elif answer in _YES | _NO | _SKIP:
        element = game['q']
        game['asked'].append((element, '⭕' if answer in _YES else '❌' if answer in _NO else '❔'))
        if answer not in _SKIP:
            game['left'] = [n for n in game['left'] if (element in _elements(corpus['concepts'][n])) == (answer in _YES)]
        intro = f'{game["asked"][-1][1]} {element}'
    else:
        return f'🎯 `y`（はい）・`n`（いいえ）・`?`（わからない）で答えて（やめるなら `/guess stop`）\n\n❓ 『{game["q"]}』？'
    left, asked = game['left'], [e for e, _ in game['asked']]
    if len(left) == 1:
        _STATE['guess'] = None
        return '\n\n'.join([intro, f'🎯 それは **{icon(corpus, left[0])}{left[0]}**！ {len(asked)} 問で（目安 ⌈log₂ {game["n"]}⌉ = {math.ceil(math.log2(game["n"]))} 問）',
                            f'🧬 `/onto {left[0]}` で、何が {left[0]} を {left[0]} にしているか'])
    question = _splitter(corpus, left, asked) if left else None
    if question is None:
        _STATE['guess'] = None
        return '\n\n'.join([intro, f'🤷 見分けられない: {_few(left, 6)}' if left else '🫥 台帳にない…（`/onto` で一覧）'])
    game['q'] = question
    return '\n\n'.join([intro, f'❓ Q{len(asked) + 1}: 『**{question}**』？（のこり {len(left)}）', '`y` / `n` / `?`'])


# ── 🧷 /olnm: OneLaunchNumerousModules (olnm.py), the terminal's one-liners, run here as far as a browser can ─────────────

def _olnm_like(olnm, word: str) -> list[str]:
    """olnm's closest names (it prints them too; that print is not the reply)."""
    with _quiet(), contextlib.redirect_stdout(io.StringIO()):
        return olnm.like(word) if word else []


def olnm_reply(text: str, index: dict | None = None) -> str:
    """🧷 olnm.py itself: list, search, read and "maybe you meant" its one-liners, and its quote-free calculator. Running a
    one-liner needs a shell, so that stays in the terminal (the reply says how to get olnm there)."""
    import olnm
    index = _STATE['index'] if index is None else index
    argv = text.split()
    commit = ((index or {}).get('commits') or {}).get('OneLaunchNumerousModules', 'HEAD')
    install = _code(f'curl -fsSL https://raw.githubusercontent.com/{OWNER}/OneLaunchNumerousModules/{commit}/olnm.py -o ~/.olnm.py'
                    " && echo 'eval \"$(python3 ~/.olnm.py init)\"' >> ~/.bashrc", 'sh')
    if not argv or argv == ['ls']:
        counts = {}
        for entry in olnm.entries():
            counts[entry['section']] = counts.get(entry['section'], 0) + 1
        return '\n\n'.join([f'🧷 **OLNM**: 端末の bash/zsh で使うワンライナー **{sum(counts.values())}** 本（olnm.py 1 ファイル）',
                            ' · '.join(f'`{s}` {n}' for s, n in counts.items()),
                            '例: `/olnm ls git` · `/olnm grep json` · `/olnm like uvtets` · `/olnm show gp` · `/olnm calc 6 mul 7`',
                            '⬇️ 端末に入れる', install])
    sub, rest = argv[0], argv[1:]
    if sub == 'calc':
        words = getattr(olnm, '_CALC_WORDS', {})
        expression = ' '.join(words.get(w, w) for w in rest)
        try:
            return f'🧮 `{" ".join(rest)}` = **{olnm.calc(expression)}**'
        except (SyntaxError, ValueError, ZeroDivisionError, OverflowError) as exc:
            return f'🧮 ⚠️ {type(exc).__name__}: {exc}（数と + - * / ** % と mul div pow lpar rpar）'
    if sub not in ('ls', 'grep', 'like', 'show', 'sections', 'net'):
        named = [w for w in argv if w in olnm.names()]
        if named:                                       # a one-liner's own name (alone, or after run): read it
            sub, rest = 'show', named[:1]
        else:
            near = _olnm_like(olnm, sub)
            return '\n\n'.join(part for part in [f'▶️ `olnm {sub}` は端末で（ブラウザでは探す・読む・電卓まで）',
                                                 f'⌨️ もしかして: {" · ".join(f"`/olnm show {n}`" for n in near[:4])}' if near else '',
                                                 install] if part)
    if sub == 'show' and rest and rest[0] not in olnm.names():
        near = _olnm_like(olnm, rest[0])
        return f'❓ そのワンライナーはない: `{rest[0]}`' + (f'\n\n⌨️ もしかして: {" · ".join(f"`/olnm show {n}`" for n in near[:4])}' if near else '')
    with _quiet() as err, contextlib.redirect_stdout(io.StringIO()) as out:
        try:
            olnm.main([sub, *rest])
        except SystemExit:
            pass
    shown = out.getvalue().strip() or (err.getvalue().strip().splitlines() or ['（なし）'])[-1]
    tail = f'▶️ 端末で `{rest[0]}`（olnm を入れたシェル）' if sub == 'show' else ''
    return '\n\n'.join(part for part in [f'🧷 `olnm {" ".join([sub, *rest])}`', _code(shown, 'sh' if sub == 'show' else 'text'), tail] if part)


def abbr(name: str) -> str:
    """The capitals of a CamelCase name, as the fleet shortens them (OnTautoLogy → OTL, PySaiyanWeBoo → PSWB); '' below two."""
    caps = re.sub(r'[^A-Z]', '', name)
    return caps if len(caps) >= 2 else ''


def _said(word: str, text: str) -> bool:
    """``word`` in ``text``: as a whole word when it is ASCII (AI is not in MAIN), anywhere when it is not (中日 in 中日の本拠地)."""
    if re.fullmatch(r'[\x00-\x7f]+', word):
        return re.search(rf'(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])', text, re.I) is not None
    return word.casefold() in text.casefold()


def grounding(question: str, index: dict | None = None, fetch=None, *, repos: int = 3, ideas: int = 3) -> dict:
    """🤖 What /ask gives the model to stand on (the context is 2048 tokens, so a few lines): the repositories the question names
    (by name or capitals), whose summary has its words or whose recorded files it finds, with their README summary; the ledger's
    concepts it names (or their 🏷 aliases), each as genus + differentia; and those files."""
    index = (_STATE['index'] if index is None else index) or {}
    words = re.findall(r'[A-Za-z][A-Za-z0-9_.@-]{2,}', question)
    kind = 'onto' if re.search(r'onto|オントロジー|概念', question, re.I) else None
    hits = [(name, path) for word in (words if words else [''] if kind else [])
            for name, path, _ in find(index, [word] if word else [], None, kind)[:6]]
    hits = list(dict.fromkeys(hits))[:12]
    summaries = index.get('repos') or {}
    score = {name: 3 * (_said(name, question) or bool(abbr(name) and _said(abbr(name), question)))
             + sum(w.casefold() in summary.casefold() for w in words) + sum(n == name for n, _ in hits)
             for name, summary in summaries.items()}
    near = sorted((n for n in score if score[n]), key=lambda n: (-score[n], n))[:repos]
    corpus = concepts(index, fetch) if any(re.search(r'(^|/)concepts[-_]', p) for _, p, _ in index.get('files', [])) else {}
    named, asked = {}, question.replace('\ufe0f', '')            # concept → where the question first names it
    for alias, called in aliases(corpus).items():
        for concept in called:                                  # one letter only when it is the name or a symbol (🐯, not 中)
            if (len(alias) > 1 or alias == _key(concept) or unicodedata.category(alias)[0] == 'S') and _said(alias, asked):
                named[concept] = min(named.get(concept, len(asked)), asked.casefold().find(alias))
    defined = []
    for concept in sorted(named, key=named.get)[:ideas]:
        result = otl.define_concepts(corpus, [concept])['concepts'][concept]
        if result['elements_observed']:
            definition = result['definition']
            defined.append(f'{icon(corpus, concept)}{concept}: {_of(definition)}'
                           + (f'（似たもの: {_few(result["similar"], 3)}）' if result['similar'] else ''))
    return {'repos': [f'{n}{f"（{abbr(n)}）" if abbr(n) else ""}: {summaries[n]}' for n in near], 'concepts': defined,
            'files': [f'{n}/{p}' for n, p in hits], 'names': sorted(summaries or index.get('commits', {}), key=str.casefold)}


def ask_messages(text: str, index: dict | None = None, fetch=None) -> str:
    """🤖 The chat messages /ask sends to the model (JSON): who it is, the commands, and what ``grounding`` finds for the question."""
    question = re.sub(r'^/ask\s*', '', text.strip(), flags=re.I) or 'こんにちは'
    found = grounding(question, index, fetch)
    lines = lambda title, rows: f'\n{title}:\n' + '\n'.join(f'- {row}' for row in rows) if rows else ''
    system = ('あなたは myon-bioinformatics のポートフォリオにある横断チャットの案内役。日本語で、短く、Markdown で答える。'
              '下の資料にあることを根拠にし、分からないことは分からないと言う。道具はコマンドで: '
              + ' '.join(f'/{n}' for n in COMMANDS if n != 'ask') + '（概念は /onto 名前、ファイルは /show リポジトリ/パス）。'
              + ('\nリポジトリ: ' + ', '.join(found['names']) if found['names'] else '')
              + lines('関係しそうなリポジトリ（README の要約）', found['repos'])
              + lines('台帳の概念（OnTautoLogy）', found['concepts'])
              + ('\n記録にあるファイル: ' + ', '.join(found['files']) if found['files'] else ''))
    return json.dumps([{'role': 'system', 'content': system}, {'role': 'user', 'content': question}], ensure_ascii=False)


def ask_html(output: str, tokens: int, seconds: float, *, threads: int = 1, webgpu: bool = False) -> str:
    """🤖 The model's answer as HTML, with its reasoning (if it wrote any) quoted as 💭 above it, what produced it and how fast."""
    parts = md.split_reasoning(output)
    thought = '\n'.join(parts['reasoning']).strip()
    answer = ('> 💭 ' + thought.replace('\n', '\n> ') + '\n\n' if thought else '') + (parts['answer'].strip() or '…')
    speed = f'{tokens / seconds:.1f} tok/s' if seconds > 0 else ''
    where = '⚡ WebGPU' if webgpu else f'🧮 CPU 🧵{threads}'
    model = RUNTIME['model'].rsplit('/', 1)[-1]
    return md.markdown_to_html(answer + f'\n\n---\n\n🤖 {model} · {where} · {tokens} tokens · {speed}')


def respond(text: str, *, index: dict | None = None, fetch=None) -> str:
    """💬 One reply in Markdown for one message."""
    index = _STATE['index'] if index is None else index
    text = (text or '').strip()
    if not text.startswith('/'):
        if _STATE['guess'] and text.lower() in _YES | _NO | _SKIP | {'stop', 'やめる'}:   # 🎯 a game is on: y / n / ? answer it
            return guess_reply(text, index, fetch)
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
    if name == 'onto':
        return onto_reply(rest, index, fetch)
    if name == 'guess':
        return guess_reply(rest, index, fetch)
    if name == 'olnm':
        return olnm_reply(rest, index)
    if name == 'compress':
        return compress_reply(rest, fetch, commit=(index or {}).get('commits', {}).get('TalkCompress'))
    if name == 'ask':                                   # the page answers it with wllama; here there is no model
        return '🤖 `/ask` はチャットのページで、ブラウザの中の llama.cpp（wllama）が答える'
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
