from pathlib import Path
import hashlib
import importlib.util
import json
import socket
import pytest
ROOT = Path(__file__).resolve().parents[1]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
extractor=module('html_snapshot','tools/vendor/lab/html_snapshot.py')
CASES=json.loads((ROOT/'tests/fixtures/html-import/cases.json').read_text())
@pytest.mark.parametrize('case',CASES,ids=lambda c:c['name'])
def test_shared_contract(case,monkeypatch):
    def deny(*args,**kwargs):raise AssertionError('fixture extraction must be offline')
    monkeypatch.setattr(socket.socket,'connect',deny)
    if 'error' in case:
        with pytest.raises(ValueError) as caught:extractor.extract(case['html'],case['url'],case['profile'],case['selector'])
        assert str(caught.value)==case['error']
    else:
        result=extractor.extract(case['html'],case['url'],case['profile'],case['selector'])
        result.pop('tag_counts')
        assert result==case['expected']
def test_exact_vendor_bytes():
    lock=json.loads((ROOT/'tools/html-import/vendor.lock.json').read_text())
    for item in lock['sources']:
        assert len(item['commit'])==40
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()==item['sha256']
def test_generated_page_is_current():
    builder=module('build_html_import','tools/build_html_import.py')
    assert (ROOT/'tools/html-import/index.html').read_text()==builder.generate()
def test_fixture_oracles_are_explicit():
    # Independent checks of the contract: not just regeneration from Python.
    by_name={c['name']:c for c in CASES}
    assert by_name['article']['expected']['text']=='A Hello world ! Link'
    assert by_name['multiple']['expected']['text']=='A nested B'
    assert by_name['multiple']['expected']['scope_count']==2
    assert by_name['main']['expected']['text']=='Main a b 日'
    assert by_name['links']['expected']['links']==[
        {'text':'R','url':'https://example.test/r'},
        {'text':'X','url':'https://example.test/dir/page#x'},
        {'text':'A','url':'https://other.test/a'},
        {'text':'B','url':'https://other.test/b'}]
    assert by_name['whitespace']['expected']['text']=='A B C'
