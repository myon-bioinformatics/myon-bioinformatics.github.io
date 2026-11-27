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
            check = """import {knowledgeStep,parseGraph,seededIndex} from './knowledge.mjs';
import assert from 'node:assert/strict';
const graph=parseGraph('@prefix ex: <urn:example:> .\\nex:A ex:r ex:B .\\nex:B ex:r ex:C .');
assert.equal(graph.nodes.length,3);
assert.deepEqual(graph.edges,[[0,1],[1,2]]);
let a=[1,0,0];
assert.deepEqual(knowledgeStep(a,0,graph.edges),a);
assert.deepEqual(knowledgeStep(a,1,graph.edges),[.5,.5,0]);
for(let i=0;i<100;i++){a=knowledgeStep(a,1,graph.edges);assert.ok(a.every(x=>x>=0));assert.ok(Math.abs(a.reduce((s,x)=>s+x,0)-1)<1e-12);}
assert.throws(()=>knowledgeStep(a,2,graph.edges),RangeError);
assert.throws(()=>parseGraph('ex:A ex:r ex:B .'));
assert.equal(seededIndex(123,3),seededIndex(123,3));
assert.equal(parseGraph('<urn:a> <urn:r> <urn:a> .').nodes.length,1);
"""
            (Path(tmp)/"check.mjs").write_text(check, encoding="utf-8")
            subprocess.run(["node", "check.mjs"], cwd=tmp, check=True)
