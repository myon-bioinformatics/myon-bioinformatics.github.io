#!/usr/bin/env python3
"""Opt-in real HTTP probe. This does NOT prove browser CORS success.

Run manually: python -S scripts/probe_niconico_live.py --output reports/niconico-http.json
No mocks, no retries, no proxy service; at most two sequential API requests.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = 'https://snapshot.search.nicovideo.jp/api/v2/snapshot/video/contents/search'
ORIGIN = 'https://myon-bioinformatics.github.io'
FIELDS = 'contentId,title,description,viewCounter,likeCounter,lengthSeconds,thumbnailUrl,startTime'


def probe(query, sort):
    url = ENDPOINT + '?' + urlencode(dict(q=query, targets='title,description', fields=FIELDS,
                                        _sort=sort, _limit='10', _context='myon-portfolio-lab'))
    result = {'query': query, 'sort': sort, 'url': url, 'origin': ORIGIN}
    start = time.monotonic()
    try:
        with urlopen(Request(url, headers={'Origin': ORIGIN, 'User-Agent': 'myon-portfolio-lab/live-validation'}),
                     timeout=15) as response:
            result['http_status'] = response.status
            result['headers'] = {key: response.headers.get(key) for key in
                                 ('Content-Type', 'Access-Control-Allow-Origin', 'Vary', 'Date')}
            body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError('Response exceeds 2 MiB')
        result['body_sha256'] = hashlib.sha256(body).hexdigest()
        data = json.loads(body)
        rows = data['data']
        valid = (data['meta']['status'] == 200 and isinstance(rows, list) and len(rows) <= 10
                 and isinstance(data['meta']['totalCount'], int)
                 and all(isinstance(row.get('contentId'), str) and isinstance(row.get('title'), str)
                         and isinstance(row.get('viewCounter'), int)
                         and isinstance(row.get('startTime'), str) for row in rows))
        result['meta'] = data['meta']
        result['rows'] = [{key: row.get(key) for key in ('contentId', 'title', 'viewCounter', 'startTime')}
                          for row in rows]
        field = 'viewCounter' if sort == '-viewCounter' else 'startTime'
        values = [row[field] if field == 'viewCounter' else datetime.fromisoformat(row[field]) for row in rows]
        result['schema_ok'] = valid
        result['descending_ok'] = values == sorted(values, reverse=True)
        allow = result['headers']['Access-Control-Allow-Origin']
        result['cors_allows_origin'] = allow in ('*', ORIGIN)
    except HTTPError as error:
        result.update(http_status=error.code, error=str(error))
    except (URLError, TimeoutError, ValueError, KeyError, TypeError) as error:
        result['error'] = str(error)
    result['elapsed_seconds'] = round(time.monotonic() - start, 3)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', default='初音ミク')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records = []
    for sort in ('-viewCounter', '-startTime'):
        record = probe(args.query, sort)
        records.append(record)
        if 'error' in record:
            break  # In particular, never immediately retry HTTP 503.
        if sort == '-viewCounter':
            # Official guide requests an idle interval >= previous response time.
            time.sleep(record['elapsed_seconds'] + 0.1)
    report = {'kind': 'live-http-not-browser', 'mocked': False,
              'observed_at': datetime.now(timezone.utc).isoformat(), 'records': records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(args.output)
    # API/schema/order success is distinct from cross-origin readability.
    return 0 if len(records) == 2 and all(r.get('schema_ok') and r.get('descending_ok') for r in records) else 1


if __name__ == '__main__':
    raise SystemExit(main())
