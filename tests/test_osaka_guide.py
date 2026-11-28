import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from osaka_guide import build, markdown
from world import example_data


def city():
    return copy.deepcopy(example_data("cities"))


def test_generated_files_match_the_game():
    graph = build(city())
    assert not graph["diagnostics"]
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert all(e["source"] in nodes and e["target"] in nodes for e in graph["edges"])
    assert {n["type"] for n in nodes.values()} == {
        "Guide", "Actor", "Task", "State", "Resource", "Goal", "Condition", "Claim", "Evidence"}
    assert sum(n.get("section") == "現場一覧" for n in nodes.values()) == 35
    assert json.loads((ROOT/"docs/osaka-guide.json").read_text(encoding="utf-8")) == graph
    assert (ROOT/"docs/osaka-guide.md").read_text(encoding="utf-8") == markdown(graph)


@pytest.mark.parametrize("observed,expected", [({}, None), ({"clue": 2}, False), ({"clue": 3}, True)])
def test_hat_unlock_evidence(observed, expected):
    graph = build(city(), observed)
    cid, = [e["target"] for e in graph["edges"] if e["source"] == "task/chest-hat" and e["kind"] == "guarded_by"]
    claim = next(n for n in graph["nodes"] if n["id"] == "claim/"+cid)
    assert claim["value"] is expected
    assert any(e["source"] == claim["id"] and e["kind"] == "supported_by" for e in graph["edges"]) == bool(observed)


def test_unreachable_and_unknown_are_distinct():
    spec = city()
    badge = spec["detective"]["badges"][0]
    badge.update(kind="quiz", count=99)
    assert "到達不能" in build(spec)["diagnostics"][0]
    badge["kind"] = "rumor"
    graph = build(spec, {"rumor": 99})
    assert "不明" in graph["diagnostics"][0]
    assert next(n["value"] for n in graph["nodes"] if n["id"] == "claim/condition/rumor/99") is None
    with pytest.raises(ValueError, match="impossible observation"):
        build(city(), {"clue": 36})
    hat = next(n for n in spec["detective"]["nodes"] if n["id"] == "chest-hat")
    hat["requires_clues"] = 36
    with pytest.raises(ValueError, match="unreachable clue lock"):
        build(spec)


def test_all_world_guide_covers_every_registered_floor_and_route():
    from world_guide import build as build_worlds, render
    from world_shell import SPACES
    from world import world_validate
    graph = build_worlds()
    assert json.loads((ROOT / "docs/world-guide.json").read_text(encoding="utf-8")) == graph
    assert (ROOT / "docs/world-guide.md").read_text(encoding="utf-8") == render(graph)
    scenes = {scene for scene, _ in SPACES.values()}
    expected = {f'{scene}/{f["id"]}' for scene in scenes
                for f in world_validate(example_data(scene))["floors"]}
    floors = [e for e in graph["edges"] if e["kind"] == "contains"]
    assert {e["target"] for e in floors} == expected
    assert {e["source"] for e in floors} == {"#"+route for route in SPACES}
    spec = copy.deepcopy(example_data("overworld"))
    spec["rpg"]["loot"]["meadow-chest-charm"]["requires_enemy"] = "meadow-town"
    with pytest.raises(ValueError, match="identify an enemy"):
        world_validate(spec)
