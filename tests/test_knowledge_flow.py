"""Exercise the published knowledge-flow module with Node."""
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest
import ast

class KnowledgeFlowTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node required")
    def test_diffusion(self):
        source = Path(__file__).resolve().parents[1] / "scripts/project_pages.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        value = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "KNOWLEDGE_FLOW_SOURCE" for t in n.targets))
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "knowledge.mjs"
            p.write_text(value, encoding="utf-8")
            check = """import {knowledgeStep} from './knowledge.mjs';
import assert from 'node:assert/strict';
let a=[1,0,0,0,0,0];
assert.deepEqual(knowledgeStep(a,0),a);
assert.deepEqual(knowledgeStep(a,1),[.5,.25,.25,0,0,0]);
for(let i=0;i<100;i++){a=knowledgeStep(a,1);assert.ok(a.every(x=>x>=0));assert.ok(Math.abs(a.reduce((s,x)=>s+x,0)-1)<1e-12);}
assert.throws(()=>knowledgeStep(a,2),RangeError);
"""
            (Path(tmp)/"check.mjs").write_text(check, encoding="utf-8")
            subprocess.run(["node", "check.mjs"], cwd=tmp, check=True)
