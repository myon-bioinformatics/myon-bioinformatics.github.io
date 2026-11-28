#!/usr/bin/env python3
"""💬 The portfolio's cross-repo chat bot: one Markdown reply per message, made by the fleet's own single-file modules.

The same file runs in CPython (tests, ``python scripts/chat.py "/flow 入力 > 圧縮 > 出力"``) and in the chat page
(tools/chat/), where Pyodide loads it next to markdown.py (md-market), ascii_artist.py, cli_args.py,
ontautology.py (🧬 /onto, 🎯 /guess), olnm.py (🧷 /olnm) and Err-o-RoadRunner's triage.py + errlib (🧯 /triage) — the commits
pinned in pyproject.toml's pages group — and mcp-toolcall-lab's Wikipedia tools, PokéAPI reader and Jev router (🔌 /mcp, 🤖 /ask),
at the commit the index recorded. What it knows about the other repositories is ``media/chat/index.json``,
written at deploy time by ``project_pages.py --record`` (the chat card's ``record``): every JSON / JSONL file of every active repository at its
commit, and the tools mcp-toolcall-lab advertises. TalkCompress's shorthand compressor is fetched on first use.

``respond(text)`` → Markdown, ``reply_html(text)`` → HTML (markdown.py escapes raw HTML), ``configure(index, base)``
for the page. 🔌 ``mcp_rpc`` is an MCP server in the page (JSON-RPC 2.0: initialize, ping, tools/list, tools/call); /mcp and 🤖 /ask
are its clients. /ask: ``ask_messages`` (the context, and ⚖️ Jev's choice of the tools to offer), ``ask_tools`` (those tools, from
tools/list) and ``ask_call`` (one call: offered, then the server's check of its arguments — mcp-toolcall-lab's rule). Every
message and decision joins the 🧾 trace (``/mcp log``, JSONL). Every command is a cli_args subparser, so a typo gets "maybe you meant".
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import difflib
import io
import json
import os
import re
import sys
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlencode

import ascii_artist as aa
import cli_args
import markdown as md
import ontautology as otl

OWNER = 'myon-bioinformatics'
MODULES = ('markdown', 'ascii_artist', 'cli_args', 'ontautology', 'olnm', 'triage', 'errlib')   # 📦 the page writes these next to this file in Pyodide
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
    'mcp': ('🔌', '[TOOL {JSON} | log]', 'ページの中の MCP サーバーと話す（tools/list・tools/call。mcp-toolcall-lab の Wikipedia・PokéAPI と '
                                        'このチャットの find・show・onto）。log は JSON-RPC と ⚖️ Jev の判定の記録（JSONL）',
            ('/mcp', '/mcp fetch_pokemon {"name": "ditto"}', '/mcp fetch_wikipedia_article {"title": 3}', '/mcp fetch_wikipedia_artcle {}',
             '/mcp log')),
    'find': ('🔎', 'WORDS [--repo R] [--kind K]', 'リポジトリ横断で JSON / JSONL を探す（K: ' + ' '.join(KINDS) + '）',
             ('onto', '/find --kind onto', '/find --kind jsonl --repo Aoi', 'TaxOntOy')),
    'show': ('👀', 'REPO/PATH', 'JSON / JSONL の中身を表にまとめる（そのコミットの raw を読む）', ('/show TaxOntOy/otl-relations.json',)),
    'onto': ('🧬', '[WORD | 要素 + 要素]', 'オントロジー（OnTautoLogy）: 〇〇を〇〇たらしめる要素と、似たものとの違い。要素を + でつなぐと逆引き',
             ('/onto ギター', '/onto 撥弦 + フレット', '/onto')),
    'guess': ('🎯', '[y | n | ?]', '当てっこ。要素を質問し、最後に候補名を確認する。わからないときは ?',
              ('/guess',)),
    'olnm': ('🧷', '[ls | grep | like | show | calc | sections] …', '端末のワンライナー集 OLNM を動かす（探す・読む・もしかして・電卓）',
             ('/olnm like uvtets', '/olnm show gp', '/olnm calc 6 mul 7', '/olnm grep json')),
    'triage': ('🧯', 'LOG', '失敗のログを Err-o-RoadRunner の triage で調べる（✅ FOUND・❔ NOT FOUND・💡 HINT。ページの中で）。JUnit は 🧾 テスト結果で前回と比べられる',
               ('/triage Traceback (most recent call last):\n  File "app.py", line 3, in <module>\n    import numpy\n'
                "ModuleNotFoundError: No module named 'numpy'",)),
    'ask': ('🤖', 'TEXT', '小さな LLM に聞く（llama.cpp をページの中で。初回だけモデルを読む）。質問が名指すリポジトリの要約・台帳の概念と直前の 🧯 を添え、'
                          '⚖️ Jev が選んだ 🔌 MCP の道具をモデルが呼ぶ（渡した道具と型の合う引数だけ）', ('/ask オントロジーの台帳はどのリポジトリにある？',)),
}
# 🔧 This bot's read-only commands as tools of the page's MCP server (name → description, properties, required)
CHAT_TOOLS = {
    'find': ('リポジトリ横断で JSON / JSONL のファイルを探す（パスの語・リポジトリ・種類）',
             {'words': {'type': 'array', 'items': {'type': 'string'}, 'description': 'パスに含まれる語'},
              'repo': {'type': 'string', 'description': 'リポジトリ名'},
              'kind': {'type': 'string', 'enum': list(KINDS), 'description': '種類（onto はオントロジーの台帳）'}}, []),
    'show': ('記録にあるファイル（リポジトリ/パス）の中身を表にまとめる', {'target': {'type': 'string', 'description': 'REPO/PATH'}}, ['target']),
    'onto': ('オントロジーの台帳で概念を定義する（属と種差、似たもの）', {'word': {'type': 'string', 'description': '概念の名前'}}, ['word']),
}
ASK_CALLS, ASK_RESULT = 2, 600   # 🔧 calls per question, characters of a result the model reads (the context is 2048 tokens)
# 🔌 mcp-toolcall-lab's code the page's MCP server runs, in the repository's layout (record_chat copies it at the lab's commit into
# media/chat/lab/): its Wikipedia tools with their FastMCP catalog, its PokéAPI reader and Jev's keyword router.
LAB = tuple(f'src/mcp_toolcall_lab/{name}' for name in (
    '__init__.py', 'catalog.py', 'wikipedia_tool.py', 'pixiv_dictionary_tool.py', 'pixiv_markup_normalize.py', 'markdown_lib.py',
    'jev_router.py', 'jev_backend.py', 'jev_shim.py', 'jev_typesafe.py', 'fixture_selection.py', 'mock/__init__.py', 'mock/common.py',
    'adapters/__init__.py', 'adapters/pokeapi.py')) + ('fixtures/jev_router/keywords.json', 'deploy/wikipedia-mcp/catalog.generated.json')
MCP_PROTOCOL = '2025-06-18'
POKEAPI = 'https://pokeapi.co/api/v2/pokemon/{name}'
# ⚖️ Jev's tool families → the server's tools /ask offers ('none': no tool; another family or a low confidence: every tool)
FAMILIES = {'wikipedia': ('fetch_wikipedia_article', 'fetch_wikipedia_section'), 'pokeapi': ('fetch_pokemon',),
            'ironmate': ('find', 'show'), 'none': ()}
TYPOS = ('/flwo a > b', '/find --kidn onto', '/find --kind ont')    # ⌨️ what cli_args answers with "maybe you meant"
_STATE = {'index': None, 'base': '', 'fetch': None, 'talkcompress': None, 'concepts': None, 'guess': None, 'triage': None, 'calls': [],
          'lab': None, 'route': None, 'trace': [], 'mcp_id': 0, 'mcp_ready': False}


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


def _lab(fetch=None, base: str | None = None):
    """🔌 mcp-toolcall-lab's modules (``LAB``): importable (a checkout's src/ on sys.path, ``--lab``) or fetched from ``base``lab/ (all
    files first); False when neither works (not recorded, offline). Its Wikipedia tool reads MediaWiki through ``_STATE['get']``
    (in the page the browser's XMLHttpRequest, with ``origin=*`` for CORS, in place of urllib); the rest runs as the lab wrote it."""
    if _STATE['lab'] is None:
        try:
            try:
                import mcp_toolcall_lab.jev_router  # noqa: F401
            except ImportError:
                get, base = fetch or _STATE['fetch'] or _fetch, _STATE['base'] if base is None else base
                texts = {name: get(f'{base}lab/{name}') for name in LAB}
                root = Path(tempfile.gettempdir()) / 'mcp-toolcall-lab'
                for name, text in texts.items():
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_text(text, encoding='utf-8')
                sys.path.insert(0, str(root / 'src'))
            os.environ.setdefault('MARKDOWN_PY', md.__file__)       # 📝 its vendored markdown.py: the one this chat runs
            from mcp_toolcall_lab import catalog, wikipedia_tool
            from mcp_toolcall_lab.adapters import pokeapi
            from mcp_toolcall_lab.jev_backend import KeywordBackend
            from mcp_toolcall_lab.jev_router import decide_route
        except Exception:
            _STATE['lab'] = False
            return False

        def mediawiki(title: str, lang: str) -> dict:     # 🌐 the request wikipedia_tool makes, through the page
            query = urlencode({'action': 'query', 'format': 'json', 'prop': 'extracts', 'explaintext': 1, 'exsectionformat': 'wiki',
                               'redirects': 1, 'titles': title, 'origin': '*'})
            try:
                return json.loads(_STATE['get'](f'{wikipedia_tool.WIKIPEDIA_API.format(lang=lang)}?{query}'))
            except (OSError, ValueError) as exc:
                raise wikipedia_tool.WikipediaFetchError(f'could not fetch {title!r} from {lang}.wikipedia.org: {exc}') from exc
        wikipedia_tool._fetch_extract_payload = mediawiki
        tree = Path(wikipedia_tool.__file__).resolve().parents[2]
        _STATE['lab'] = {'catalog': catalog, 'pokeapi': pokeapi, 'router': KeywordBackend.from_path(), 'decide': decide_route,
                         'tools': json.loads((tree / 'deploy/wikipedia-mcp/catalog.generated.json').read_text(encoding='utf-8'))['tools']}
    return _STATE['lab']


def server_tools(fetch=None) -> dict:
    """🔌 What the page's MCP server lists (name → MCP tool: name, description, inputSchema): the lab's Wikipedia tools (its FastMCP
    catalog), its PokéAPI reader and this bot's find · show · onto (without the lab, only these)."""
    tools = {}
    lab = _lab(fetch)
    if lab:
        tools = {t['name']: {key: t[key] for key in ('name', 'description', 'inputSchema')} for t in lab['tools']}
        tools['fetch_pokemon'] = {'name': 'fetch_pokemon', 'description': 'PokéAPI の pokemon（タイプ・種族値・特性）。名前は英語の小文字（pikachu）か図鑑番号（25）',
                                  'inputSchema': {'type': 'object', 'properties': {'name': {'type': 'string'}}, 'required': ['name'],
                                                  'additionalProperties': False}}
    return {**tools, **{name: {'name': name, 'description': what, 'inputSchema': {
        'type': 'object', 'properties': props, 'required': required, 'additionalProperties': False}} for name, (what, props, required) in CHAT_TOOLS.items()}}


def _run_tool(name: str, args: dict, index: dict | None, fetch) -> str:
    """🔧 One listed tool, its arguments already checked: the text of its result."""
    if name == 'find':
        return find_reply(index, args.get('words', []), args.get('repo'), args.get('kind'))
    if name == 'show':
        return show_reply(index, args['target'], fetch)
    if name == 'onto':
        return onto_reply(args['word'], index, fetch)
    lab, _STATE['get'] = _lab(fetch), fetch or _STATE['fetch'] or _fetch
    if name == 'fetch_pokemon':                           # 🐾 the lab's reader of the JSON this page fetched
        url = POKEAPI.format(name=quote(args['name'].strip().lower(), safe=''))
        record = lab['pokeapi'].pokemon_source(_STATE['get'](url), url)
        return record.get('markdown') or json.dumps(record, ensure_ascii=False)
    return json.dumps(lab['catalog'].dispatch_tool(name, args), ensure_ascii=False)   # 📚 the lab's dispatch (Wikipedia)


TRACE_ROWS = 400   # 🧾 the trace keeps its last rows


def _trace(event: str, **row) -> None:
    _STATE['trace'].append({'event': event, **row})
    del _STATE['trace'][:-TRACE_ROWS]


def mcp_rpc(message, index: dict | None = None, fetch=None) -> dict | None:
    """🔌 The page's MCP server: one JSON-RPC 2.0 message (a dict or its JSON text) in, its response out (None for a notification) —
    initialize, ping, tools/list and tools/call, the messages the lab's Streamable HTTP /mcp answers, here without HTTP. tools/call
    runs a tool only when it is listed and its arguments pass its inputSchema (``_check``): an unknown tool or bad arguments are
    errors (-32602), a tool that fails is a result with ``isError``. Both directions join the 🧾 trace."""
    index = _STATE['index'] if index is None else index
    try:
        request = json.loads(message) if isinstance(message, str) else message
    except json.JSONDecodeError:
        request = None
    _trace('mcp/request', message=request if request is not None else str(message)[:200])
    rid = request.get('id') if isinstance(request, dict) else None

    def reply(result=None, code: int = 0, text: str = '', data=None) -> dict:
        error = {'code': code, 'message': text, **({'data': data} if data else {})}
        response = {'jsonrpc': '2.0', 'id': rid, **({'error': error} if code else {'result': result})}
        _trace('mcp/response', message=response)
        return response
    if not isinstance(request, dict) or request.get('jsonrpc') != '2.0' or not isinstance(request.get('method'), str):
        return reply(code=-32700 if request is None else -32600, text='Parse error' if request is None else 'Invalid Request')
    method, params = request['method'], request.get('params') or {}
    if 'id' not in request:                               # 📣 a notification (notifications/initialized): no response
        return None
    if method == 'initialize':
        return reply({'protocolVersion': MCP_PROTOCOL, 'capabilities': {'tools': {'listChanged': False}},
                      'serverInfo': {'name': 'myon-bioinformatics chat', 'version': ((index or {}).get('commits', {}).get('mcp-toolcall-lab') or '-')[:7]}})
    if method == 'ping':
        return reply({})
    tools = server_tools(fetch)
    if method == 'tools/list':
        return reply({'tools': list(tools.values())})
    if method != 'tools/call':
        return reply(code=-32601, text=f'Method not found: {method}')
    name, args = params.get('name'), params.get('arguments', {})
    if name not in tools:
        near = difflib.get_close_matches(str(name), tools, n=1)
        return reply(code=-32602, text=f'Unknown tool: {name}', data={'did_you_mean': near[0]} if near else None)
    problems = _check(tools[name]['inputSchema'], args)
    if problems:
        return reply(code=-32602, text='Invalid params', data={'problems': problems})
    try:
        text, failed = _run_tool(name, args, index, fetch), False
    except Exception as exc:                              # ⚠️ the tool ran and failed (404, CORS, offline): the model reads why
        text, failed = f'{type(exc).__name__}: {exc}', True
    return reply({'content': [{'type': 'text', 'text': text}], 'isError': failed})


def _rpc(method: str, params: dict | None = None, *, index: dict | None = None, fetch=None, notify: bool = False) -> dict | None:
    """🔌 The client's side: one message to the page's server; the session starts with initialize → notifications/initialized."""
    if not _STATE['mcp_ready'] and method != 'initialize':
        _STATE['mcp_ready'] = True
        _rpc('initialize', {'protocolVersion': MCP_PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'chat', 'version': '1'}},
             index=index, fetch=fetch)
        _rpc('notifications/initialized', index=index, fetch=fetch, notify=True)
    message = {'jsonrpc': '2.0', 'method': method, **({'params': params} if params is not None else {})}
    if not notify:
        _STATE['mcp_id'] += 1
        message['id'] = _STATE['mcp_id']
    return mcp_rpc(message, index, fetch)


def _call_text(response: dict) -> tuple[bool, str]:
    """✅ / ❌ and the text of a tools/call response (an error's message with its problems or did-you-mean)."""
    if 'error' in response:
        error, data = response['error'], response['error'].get('data', {})
        more = data.get('problems') or ([f'もしかして {data["did_you_mean"]}'] if data.get('did_you_mean') else [])
        return False, ' · '.join([f'{error["message"]} ({error["code"]})', *more])
    return not response['result']['isError'], response['result']['content'][0]['text']


def mcp_reply(text: str, index: dict | None, fetch=None) -> str:
    """🔌 /mcp: the page's server's tools/list, one tools/call, or (log) the 🧾 trace."""
    name, _, raw = text.strip().partition(' ')
    if name == 'log':
        return mcp_log()
    if not name:
        listed = _rpc('tools/list', index=index, fetch=fetch)['result']['tools']
        family = {tool: f for f, names in FAMILIES.items() for tool in names}
        rows = [[f'`{t["name"]}`', family.get(t['name'], '—'), ', '.join(t['inputSchema'].get('required', [])) or '—', _cell(t['description'])]
                for t in listed]
        return ('## 🔌 ページの中の MCP サーバー（tools/list）\n\n' + md.table(['道具', '⚖️ Jev', '必須', '説明'], rows).strip()
                + ('' if _lab(fetch) else '\n\n⏸ mcp-toolcall-lab を読めない（このビルドは記録していないか、オフライン）')
                + '\n\n`/mcp 道具 {"引数": "値"}` で tools/call、`/mcp log` で記録（JSONL）')
    try:
        arguments = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        return f'❌ 引数が JSON ではない（{exc.msg}, {exc.pos} 文字目）'
    response = _rpc('tools/call', {'name': name, 'arguments': arguments}, index=index, fetch=fetch)
    ok, result = _call_text(response)
    sent = next(row['message'] for row in reversed(_STATE['trace']) if row['event'] == 'mcp/request')
    head = ('✅ tools/call' if ok else '⚠️ isError' if 'result' in response else '❌ 断る（JSON-RPC のエラー）')
    body = result if len(result) <= 1500 else result[:1499] + '…'
    return '\n\n'.join([f'### 🔌 {head}', _code(json.dumps(sent, ensure_ascii=False), 'json'),
                          body if ok and name in ('find', 'show', 'onto', 'fetch_pokemon') else _code(body)])


def mcp_log(rows: int = 8) -> str:
    """🧾 The trace in numbers (requests by method, tools/call outcomes, ⚖️ Jev's decisions) and its last ``rows`` as JSONL."""
    trace = _STATE['trace']
    if not trace:
        return '🧾 まだ記録がない（/ask か /mcp で MCP を話すと、JSON-RPC と ⚖️ Jev の判定が JSONL で残る）'
    sent = {row['message'].get('id'): row['message'].get('method') for row in trace
            if row['event'] == 'mcp/request' and isinstance(row['message'], dict)}
    methods, outcomes, routes = {}, {'✅': 0, '⚠️': 0, '❌': 0}, {}
    for row in trace:
        if row['event'] == 'mcp/request' and isinstance(row['message'], dict):
            methods[row['message'].get('method')] = methods.get(row['message'].get('method'), 0) + 1
        elif row['event'] == 'mcp/response' and sent.get(row['message'].get('id')) == 'tools/call':
            outcomes['❌' if 'error' in row['message'] else '⚠️' if row['message']['result']['isError'] else '✅'] += 1
        elif row['event'] == 'jev/route_decision':
            key = row['tool_family'] if not row.get('fallback_reason') else f'⏸ {row["fallback_reason"]}'
            routes[key] = routes.get(key, 0) + 1
        elif row['event'] == 'ask/refused':
            outcomes['❌'] += 1
    clip = lambda line: line if len(line) <= 240 else line[:239] + '…'
    return '\n\n'.join(['### 🧾 MCP の記録', _kv([
        ('📨', ' · '.join(f'{m} {n}' for m, n in methods.items()) or '—'),
        ('🔧', ' · '.join(f'{k} {n}' for k, n in outcomes.items())),
        ('⚖️', ' · '.join(f'{k} {n}' for k, n in routes.items()) or '—'),
        ('🧾', f'{len(trace)} 行（下は最後の {min(rows, len(trace))} 行）')]),
        _code('\n'.join(clip(json.dumps(row, ensure_ascii=False)) for row in trace[-rows:]), 'jsonl')])


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


def _index_note(index: dict, repo: str | None = None) -> str:
    """Report scan coverage for the requested repository or the full search scope."""
    errors = index.get('scan_errors')
    if errors is None:
        return '⚠️ 索引の取得範囲は未記録です。'
    if repo:
        key = repo.lower()
        statuses = [status for name, status in errors.items() if name.lower() == key]
        if not statuses and not any(name.lower() == key for name in index['commits']):
            return 'ℹ️ このリポジトリは索引の対象外です。'
    else:
        statuses = list(errors.values())
    counts = [f'{label} {statuses.count(status)} 件' for status, label in
              [('truncated_tree', '部分取得'), ('unavailable', '取得不可')] if status in statuses]
    return f'⚠️ {"・".join(counts)}。未取得のファイルは検索範囲に含まれません。' if counts else ''


def find_reply(index: dict | None, words=(), repo=None, kind=None) -> str:
    if not index or 'files' not in index:
        return '⏸ このビルドはリポジトリ横断の索引を記録していない'
    hits = find(index, words, repo, kind)
    label = ' '.join([*words, *([f'📦 {repo}'] if repo else []), *([f'{KINDS[kind]} {kind}'] if kind else [])]) or 'すべて'
    note = _index_note(index, repo)
    if not hits:
        names = {name.lower(): name for name, _, _ in index['files']}
        near = [names[n] for n in names if any(w.lower() in n or n in w.lower() for w in words)][:5]
        return '\n\n'.join(part for part in (f'🔎 {label}: 0 件（索引内）', note,
                            f'📦 リポジトリ: {", ".join(near)} → `/find --repo {near[0]}`' if near else '') if part)
    repos = sorted({name for name, _, _ in hits}, key=str.lower)
    rows = [[f'📦 {name}', f'[{path}]({_blob(index, name, path)})', _size(size), ''.join(KINDS[k] for k in kinds_of(name, path))]
            for name, path, size in hits[:FIND_ROWS]]
    more = f'（上位 {FIND_ROWS} 件）' if len(hits) > FIND_ROWS else ''
    return '\n\n'.join(part for part in (f'🔎 {label}: {len(hits)} 件 · 📦 {len(repos)} リポジトリ{more}', note,
                        md.table(['リポジトリ', 'ファイル', '大きさ', '種類'], rows).strip(),
                        f'👀 `/show {hits[0][0]}/{hits[0][1]}` で中身') if part)


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
    if not index or 'files' not in index:
        return '⏸ このビルドはリポジトリ横断の索引を記録していない'
    target = re.sub(r'^https://github\.com/[^/]+/', '', target.strip()).replace('/blob/', '/', 1)
    name, _, path = target.partition('/')
    rows = {(n.lower(), p): (n, p, s) for n, p, s in index['files']}
    found = rows.get((name.lower(), path))
    if found is None and '/' in path:            # a pasted blob URL: REPO/COMMIT/PATH
        found = rows.get((name.lower(), path.split('/', 1)[1]))
    if found is None:
        near = find(index, [path.rsplit('/', 1)[-1]] if path else [name])
        return '\n\n'.join(part for part in (f'❓ 記録にない: `{target}`', _index_note(index, name),
                            f'🔎 近いもの: `/show {near[0][0]}/{near[0][1]}`' if near else '') if part)
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
    corpus = {'schema': otl.CONCEPT_SCHEMA, 'concepts': {}, 'similar': [], 'sources': [],
              'names': {}, 'name_basis': {}, 'maybe': {}, 'broader': {}}
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
        maybe = data.get('maybe') or {}
        for concept, body in data['concepts'].items():
            if concept not in corpus['concepts']:
                corpus['concepts'][concept] = body
                if isinstance(maybe, dict) and concept in maybe:
                    corpus['maybe'][concept] = maybe[concept]
        broader = data.get('broader')
        if isinstance(broader, dict):
            for element, parents in broader.items():
                corpus['broader'].setdefault(element, parents)
        corpus['similar'] += data.get('similar', [])
        for concept, called in (data.get('names') or {}).items():
            corpus['names'].setdefault(concept, []).extend(c for c in called if isinstance(c, str))
        for kind, order in (data.get('name_basis') or {}).items():       # 絵文字略称: [同じ, 代用, …] — the strongest first
            corpus['name_basis'].setdefault(kind, [b for b in order if isinstance(b, str)])
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


def aliases(corpus: dict) -> dict[str, list[tuple[str, str, int]]]:
    """🏷 What each concept is also called → (concept, basis, rank) for each concept called so, the strongest basis first: its
    name and the ledger's names whose kind is a name or a reading (略称:中日, 英名:Guitar, 別名:ヒト, 読み:しゃけ, 絵文字略称/同じ:🐯 —
    not 同音語 or 名前の由来). ``kind/basis`` ranks by the ledger's name_basis for that kind (🦅: 楽天 同じ before ソフトバンク 代用;
    an unlisted basis after them, none before them); the same rank keeps the ledger's order. A concept's name is only ever itself."""
    called = {_key(name): [(name, '', -1)] for name in corpus.get('concepts', {})}
    own = set(called)
    for concept, names in corpus.get('names', {}).items():
        for full, _, alias in (n.partition(':') for n in names):
            kind, _, basis = full.partition('/')
            key, order = _key(alias), corpus.get('name_basis', {}).get(kind, [])
            if concept in corpus['concepts'] and key and key not in own and (kind.endswith(('名', '称')) or kind == '読み') \
                    and concept not in [c for c, _, _ in called.get(key, [])]:
                rank = (order.index(basis) if basis in order else len(order)) if basis else -1
                called.setdefault(key, []).append((concept, basis, rank))
    return {key: sorted(claims, key=lambda claim: claim[2]) for key, claims in called.items()}


def _wins(claims: list, concept: str) -> bool:
    """``concept`` alone holds the strongest claim to a name (a tie wins for no one)."""
    return [c for c, _, rank in claims if rank == claims[0][2]] == [concept]


def icon(corpus: dict, concept: str) -> str:
    """The concept's face in replies (🐯 阪神タイガース) and a space: its strongest 絵文字略称 that no one else holds more strongly
    (ソフトバンク: 🦅 is 楽天's, so 🐶), else its strongest; '' without one."""
    table = aliases(corpus)
    marks = [(next(rank for c, _, rank in table[_key(alias)] if c == concept), _key(alias), alias.strip())
             for kind, _, alias in (n.partition(':') for n in corpus.get('names', {}).get(concept, []))
             if kind.partition('/')[0] == '絵文字略称' and concept in [c for c, _, _ in table.get(_key(alias), [])]]
    marks.sort(key=lambda mark: mark[0])
    face = next((alias for _, key, alias in marks if _wins(table[key], concept)), marks[0][2] if marks else '')
    return f'{face} ' if face else ''


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
    why = lambda basis: f'（{basis}）' if basis else ''
    if len(called) > 1 and not _wins(called, called[0][0]):           # a tie: which one is meant is the user's to say
        return '\n\n'.join([f'🏷 **{text}** は {len(called)} つ: ' + ' · '.join(f'`/onto {c}`{why(b)}' for c, b, _ in called), _ledger(corpus)])
    if called:
        said = f'🏷 {text} → **{called[0][0]}**{why(called[0][1])}' + (
            ' · ほかに ' + ' · '.join(f'`/onto {c}`{why(b)}' for c, b, _ in called[1:]) if called[1:] else '')
        text = called[0][0]
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
    """Render a turn of OnTautoLogy's guessing game in Markdown."""
    answer, session = text.strip().lower(), _STATE['guess']
    if answer in ('stop', 'やめる'):
        _STATE['guess'] = None
        return '🎯 おしまい（`/guess` でもう一度）'
    if session is None or answer in ('', 'new', 'again', 'もう一回'):
        _STATE['guess'] = None
        corpus = concepts(index, fetch)
        if not corpus.get('concepts'):
            return '⏸ 概念の台帳（OnTautoLogy の concepts-*.json）をこのビルドの索引から読めない'
        try:
            game = otl.GuessGame(corpus, binary=True, confirm_name=True, lies=1)
        except ValueError:
            return '⏸ 概念の台帳に不整合があるため、当てっこを始められない'
        if not game.candidates:
            return '⏸ 台帳に要素を観測した概念がない'
        _STATE['guess'] = game, corpus
        intro = f'🎯 台帳の {len(game.candidates)} 個から思い浮かべて（{_few(game.candidates, 6)}）。はい＝`y`・いいえ＝`n`・わからない＝`?`'
    else:
        game, corpus = session
        if answer in _YES | _NO | _SKIP:
            value = None if answer in _SKIP else answer in _YES
            _, question = game.question
            game.answer(value)
            mark = {True: '⭕', False: '❌', None: '❔'}[value]
            intro = f'{mark} {question}'
        else:
            intro = '🎯 `y`（はい）・`n`（いいえ）・`?`（わからない）で答えて（やめるなら `/guess stop`）'
    if game.question is not None:
        kind, question = game.question
        prompt = (f'候補は **{icon(corpus, question)}{question}**。思い浮かべたものと同じ？' if kind == 'name'
                  else f'『**{question}**』？（のこり {len(game.candidates)}）')
        return '\n\n'.join([intro, f'❓ Q{len(game.log) + 1}: {prompt}', '`y` / `n` / `?`'])

    _STATE['guess'] = None
    if game.guess is not None:
        name = game.guess
        return '\n\n'.join([intro, f'🎯 それは **{icon(corpus, name)}{name}**！ {len(game.log)} 問で',
                            f'🧬 `/onto {name}` で、何が {name} を {name} にしているか'])
    if game.log and game.log[-1].get('identity'):
        result = '🫥 台帳の候補を確認できなかった（`/guess` でもう一度）'
    elif len(game.candidates) > 1:
        result = f'🤷 見分けられない: {_few(game.candidates, 6)}'
    else:
        result = '🫥 当てられなかった（`/onto` で台帳の一覧）'
    return f'{intro}\n\n{result}'


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


def triage_reply(text: str) -> str:
    """🧯 Err-o-RoadRunner's triage on a pasted log: JUnit XML, a GitHub Actions log or stderr (a traceback, a Node stack, …).

    Its facts about the machine that runs it (Python, environment, node / gh, lock files) would describe this page, not the
    failure, so they are left out. The lines are kept for /ask, which may explain them — as a guess, beside the facts. A JUnit
    report also points to 🧾 テスト結果 (#test-report), which compares it with the previous run."""
    import triage
    text = text.strip('\n')
    if not text.strip():
        return '🧯 `/triage` の後に失敗のログ（traceback・Node のスタック・JUnit XML・Actions のログ）を貼る'
    junit, path = [], Path(tempfile.gettempdir()) / 'junit.xml'
    if text.lstrip().startswith(('<?xml', '<testsuite')):
        path.write_text(text.strip(), encoding='utf-8')
        junit = [str(path)]
    actions = text if re.search(r'^(\S+Z )?##\[(error|group)\]', text, re.M) else None
    runtime, triage.collect_runtime_facts = triage.collect_runtime_facts, lambda report, root: None
    try:
        report = triage.triage(exit_code=None, stderr_text=None if junit or actions else text, log_text=None,
                               actions_log_text=actions, junit_paths=junit, project_root=None)
    finally:
        triage.collect_runtime_facts = runtime
    tidy = lambda lines: [line.replace(f' ({path})', '') for line in lines if line.rpartition(': ')[2] != 'exit code']   # 📋 no exit code, no file
    _STATE['triage'] = [line for line in tidy(report.lines()) if not line.startswith('NOT FOUND')]   # 🤖 for /ask: facts and hints
    groups = [('✅ FOUND', tidy(report.found)), ('❔ NOT FOUND', tidy(report.not_found)), ('💡 HINT', tidy(report.hints))]
    out = ['### 🧯 Err-o-RoadRunner triage'] + [f'**{label}**\n\n' + md.bullet_list(lines).strip() for label, lines in groups if lines]
    if junit:
        out.append('🧾 前回の実行と比べる（新規・継続・解消）→ [🧾 テスト結果](#test-report)')
    return '\n\n'.join(out + ['🤖 `/ask この失敗は？` で 💡 を説明（推測）'])


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
        for concept, _, _ in called:                                  # one letter only when it is the name or a symbol (🐯, not 中)
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
    """🤖 The chat messages /ask sends to the model (JSON): who it is, the commands, what ``grounding`` finds for the question and
    the last 🧯 triage. A new question starts a new 🔧 trail (``ask_call``) and asks ⚖️ Jev which tools to offer (``ask_route``)."""
    question = re.sub(r'^/ask\s*', '', text.strip(), flags=re.I) or 'こんにちは'
    found = grounding(question, index, fetch)
    _STATE['calls'] = []
    offered = ask_route(question, fetch)['offered']
    lines = lambda title, rows: f'\n{title}:\n' + '\n'.join(f'- {row}' for row in rows) if rows else ''
    system = ('あなたは myon-bioinformatics のポートフォリオにある横断チャットの案内役。日本語で、短く、Markdown で答える。'
              '下の資料にあることを根拠にし、分からないことは分からないと言う。索引にない情報の有無は断定しない。道具はコマンドで: '
              + ' '.join(f'/{n}' for n in COMMANDS if n != 'ask') + '（概念は /onto 名前、ファイルは /show リポジトリ/パス）。'
              + ('\nリポジトリ: ' + ', '.join(found['names']) if found['names'] else '')
              + lines('関係しそうなリポジトリ（README の要約）', found['repos'])
              + lines('台帳の概念（OnTautoLogy）', found['concepts'])
              + ('\n記録にあるファイル: ' + ', '.join(found['files']) if found['files'] else '')
              + ('\n資料が足りなければ道具（' + '・'.join(offered) + '）を呼んでよい。道具の結果は事実として使う。' if offered else '')
              + ('\n直前の 🧯 triage（FOUND は事実、HINT は推測。説明は推測として書く）:\n' + '\n'.join(_STATE['triage'][:16])
                 if _STATE['triage'] else ''))
    return json.dumps([{'role': 'system', 'content': system}, {'role': 'user', 'content': question}], ensure_ascii=False)


def ask_route(question: str, fetch=None) -> dict:
    """⚖️ Jev (the lab's keyword router, ``decide_route``) on the question: which of the server's tools /ask offers — one family's
    when it is confident, none when it is confident no tool is needed, else every tool. The decision joins the 🧾 trace."""
    tools, lab = list(server_tools(fetch)), _lab(fetch)
    if not lab:
        row = {'needs_tool': None, 'tool_family': None, 'fallback_reason': 'no_lab', 'offered': tools}
    else:
        decision = dataclasses.asdict(lab['decide'](lab['router'], question))
        family = decision['tool_family'] if not decision['fallback_reason'] else None
        row = {**decision, 'offered': [t for t in tools if t in FAMILIES[family]] if family in FAMILIES else tools}
    _trace('jev/route_decision', question=question, **row)
    _STATE['route'] = row
    return row


def ask_tools(index: dict | None = None, fetch=None) -> str:
    """🔧 The tools /ask offers (``ask_route``) from the server's tools/list, as the OpenAI-style ``tools`` (JSON) wllama takes."""
    listed = _rpc('tools/list', index=index, fetch=fetch)['result']['tools']
    offered = (_STATE['route'] or {}).get('offered')
    return json.dumps([{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['inputSchema']}}
                       for t in listed if offered is None or t['name'] in offered], ensure_ascii=False)


def ask_call(name: str, arguments, index: dict | None = None, fetch=None) -> str:
    """🔧 One tool call of the model (``arguments``: the JSON text it wrote, or a dict), as JSON ``{ok, call, result}``. The client
    sends it as tools/call only when the tool was offered, the question has calls left (``ASK_CALLS``) and the arguments are
    JSON; the server then checks them against the tool's inputSchema. ``result`` says why not when it did not run (the model reads
    it either way); each call joins the 🔧 trail ``ask_html`` shows."""
    offered = (_STATE['route'] or {}).get('offered')
    problems, args = [], arguments
    if offered is not None and name not in offered:
        near = difflib.get_close_matches(str(name), offered, n=1)
        problems.append('渡していない道具' + (f'（もしかして {near[0]}）' if near else ''))
    elif len(_STATE['calls']) >= ASK_CALLS:
        problems.append(f'道具は 1 つの質問につき {ASK_CALLS} 回まで')
    else:
        try:
            args = json.loads(arguments or '{}') if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as exc:
            problems.append(f'引数が JSON ではない（{exc.msg}）')
    if problems:
        ok, result = False, '❌ ' + ' · '.join(problems)
        _trace('ask/refused', name=name, problems=problems)
    else:
        ok, result = _call_text(_rpc('tools/call', {'name': name, 'arguments': args}, index=index, fetch=fetch))
        result = result if ok else '❌ ' + result
    call = f'{name} ' + (json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(arguments)[:60])
    _STATE['calls'].append({'call': call, 'ok': ok})
    return json.dumps({'ok': ok, 'call': call, 'result': result if len(result) <= ASK_RESULT else result[:ASK_RESULT - 1] + '…'},
                      ensure_ascii=False)


def ask_html(output: str, tokens: int, seconds: float, *, threads: int = 1, webgpu: bool = False) -> str:
    """🤖 The model's answer as HTML: ⚖️ the tools Jev offered, the 🔧 calls the model made (✅ ran, ❌ refused), its reasoning (if
    it wrote any) quoted as 💭, the answer, what produced it and how fast."""
    parts = md.split_reasoning(output)
    thought = '\n'.join(parts['reasoning']).strip()
    route = _STATE['route'] or {}
    trail = (f'⚖️ Jev {route.get("tool_family") if not route.get("fallback_reason") else "⏸ " + route["fallback_reason"]} → '
             + (' · '.join(f'`{t}`' for t in route['offered']) or '道具なし') + '  \n' if route else '')
    trail += ''.join(f'🔧 {"✅" if c["ok"] else "❌"} `{c["call"]}`  \n' for c in _STATE['calls'])
    answer = (trail + '\n' if trail else '') + ('> 💭 ' + thought.replace('\n', '\n> ') + '\n\n' if thought else '') + (parts['answer'].strip() or '…')
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
        return mcp_reply(rest, index, fetch)
    if name == 'onto':
        return onto_reply(rest, index, fetch)
    if name == 'guess':
        return guess_reply(rest, index, fetch)
    if name == 'olnm':
        return olnm_reply(rest, index)
    if name == 'compress':
        return compress_reply(rest, fetch, commit=(index or {}).get('commits', {}).get('TalkCompress'))
    if name == 'triage':
        return triage_reply(text.strip()[len('/triage'):])
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
    cli.add_argument('--lab', type=Path, help='an mcp-toolcall-lab checkout (for /mcp and the tools of /ask)')
    cli.add_argument('--html', action='store_true', help='print the HTML the page shows')
    args = cli.parse_args(argv)
    if args.talkcompress:
        sys.path[:0] = [str(args.talkcompress), str(args.talkcompress / 'ShorthandSessionEdge')]
    if args.lab:
        sys.path.insert(0, str(args.lab / 'src'))
    index = json.loads(args.index.read_text(encoding='utf-8')) if args.index else None
    text = ' '.join(args.message)
    print(reply_html(text, index=index) if args.html else respond(text, index=index))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
