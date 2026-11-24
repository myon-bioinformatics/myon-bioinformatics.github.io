"""🌍 Worlds (scripts/world.py): the classroom, motion, real places, the shared board and the demo GIFs (browser behaviour: ``tests/world_browser.py``)."""

import copy
import importlib.util
import io
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import pytest

import pysaiyanweboo as ui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import world as W  # noqa: E402  (scripts/world.py: the engine, the specs and the demo recorder)


def _vendored(name):
    spec = importlib.util.spec_from_file_location(f"_vendored_{name}", ROOT / "vendor" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def node26():
    """An existing Node 26 or newer, else None (the fleet's one lookup: ``$NODE``, then PATH); nothing is installed."""
    return _vendored("fleet_check").node()


def node_js(source, *argv, timeout=60):
    """Run ``source`` (an ES module kept as a string here) in Node 26+, PySaiyanWeBoo's modules written beside it under ./js/."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="world-node-") as tmp:
        ui.write_js(tmp)
        script = Path(tmp) / "check.mjs"
        script.write_text('import {createRequire} from "node:module";const require=createRequire(import.meta.url);'
                          f"const REPO={json.dumps(str(ROOT))};\n" + source, encoding="utf-8")
        done = ui.run_node(script, *argv, timeout=timeout)
    if done.returncode != 0:
        raise AssertionError(f"node exited with {done.returncode}\n{done.stderr}")
    return done


def node_value(source, expression, data=None, *, timeout=60):
    """The JSON value of ``expression`` in Node after ``source``, with ``data`` bound to ``data``."""
    script = f"{source}\nconst data={json.dumps(data, ensure_ascii=False)};\nconsole.log(JSON.stringify({expression}));"
    return json.loads(node_js(script, timeout=timeout).stdout)


def world_js():
    """world.js without ``bindWorlds();``: its inner functions (gridRoute, motionSample, ...) for node_value and node_js."""
    return W.WORLD_JS.removesuffix("bindWorlds();\n")


def rgb_png(width, height, color, rectangles=()):
    """A PNG of ``color`` with filled ``rectangles`` (``((x0, y0, x1, y1), rgb)``), for the GIF encoder tests."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(image)
    for (x0, y0, x1, y1), fill in rectangles:
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=fill)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


# ═══ 🏫 classroom ═════════════════════════════════════════════════════════════════════════════════════════
# School world: the walking grid oracle, validation, the classroom generator, the emitted HTML, and Node parity.
#
# Browser behaviour (picker, keys, pad, taps, collisions) is in tests/integration/worlds_browser.py.


GRID = ["00000",
        "01110",
        "00010",
        "01000",
        "00000"]


def classroom(**kw):
    return W.world_validate({"schema": W.WORLD_SCHEMA, "id": "school", "floors": [W.classroom_floor(**kw)]})["floors"][0]


def test_path_is_shortest_and_avoids_solid_tiles():
    path = W.world_path(GRID, [0, 0], [4, 4])
    assert path[0] == [0, 0] and path[-1] == [4, 4] and len(path) == 9
    assert all(GRID[y][x] == "0" for x, y in path)
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(path, path[1:]))
    assert W.world_path(GRID, [3, 3], [3, 3]) == [[3, 3]]
    assert W.world_path(GRID, [0, 0], [0, 0]) == [[0, 0]]


def test_solid_or_cut_off_or_outside_goal_ends_at_the_nearest_reachable_tile():
    assert W.world_path(GRID, [0, 0], [2, 1])[-1] == [2, 0]                # solid goal: the first nearest tile in search order
    walled = ["0100", "0100", "0100"]
    assert W.world_path(walled, [0, 0], [3, 1])[-1] == [0, 1]              # the other side is cut off: nearest on this side
    assert W.world_path(GRID, [0, 0], [-9, 99])[-1] == [0, 4]              # outside clamps into the grid
    assert W.world_path(["1"], [0, 0], [0, 0]) == [[0, 0]]                 # the start always counts as free


def test_route_points_end_at_the_target_when_reachable_and_at_a_tile_centre_otherwise():
    blocked = ["00000", "01110", "00000"]
    points = W.world_route_points(blocked, 32, [16, 16], [144, 80])        # reachable: ends exactly at the tapped point
    assert points[0] == [16, 16] and points[-1] == [144, 80]
    assert points[1] in ([48, 16], [16, 48])                                # around the block, through tile centres
    assert all(blocked[int(y // 32)][int(x // 32)] == "0" for x, y in points)
    points = W.world_route_points(blocked, 32, [16, 16], [80, 48])         # a solid tile: ends at a free neighbour's centre
    assert points[-1] in ([80, 16], [80, 80]) and blocked[int(points[-1][1] // 32)][int(points[-1][0] // 32)] == "0"
    assert W.world_route_points(blocked, 32, [20, 20], [20, 20]) == [[20, 20], [20, 20]]


def test_route_is_constant_speed_and_stays_on_free_tiles():
    floor = classroom()
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    rng = random.Random(7)
    free = [(x, y) for y, row in enumerate(blocked) for x, v in enumerate(row) if v == "0"]
    for _ in range(60):
        (ax, ay), (bx, by) = rng.sample(free, 2)
        a = [ax * 32 + rng.uniform(1, 31), ay * 32 + rng.uniform(1, 31)]
        b = [bx * 32 + rng.uniform(1, 31), by * 32 + rng.uniform(1, 31)]
        points = W.world_route_points(blocked, 32, a, b)
        route = W.world_route(points, at=2, speed=96, width=floor["width"], height=floor["height"])
        length = sum(math.dist(p, q) for p, q in zip(points, points[1:]))
        end = route[-1]["at"] + route[-1]["duration"]
        assert end - 2 == pytest.approx(length / 96)
        assert W.world_route_sample(route, 2) == pytest.approx(a)
        assert W.world_route_sample(route, 1e9) == pytest.approx(b)
        for i in range(int((end - 2) / .05) + 1):
            x, y = W.world_route_sample(route, 2 + i * .05)
            assert blocked[int(y // 32)][int(x // 32)] == "0", (a, b, x, y)
        # retargeting samples the old route first, then starts a new one from there
        here = W.world_route_sample(route, 2 + (end - 2) / 2)
        assert W.world_route(W.world_route_points(blocked, 32, here, a), at=5, speed=96)[0]["from"] == pytest.approx(here)


def test_a_route_with_nowhere_to_go_is_one_still_segment():
    route = W.world_route([[10, 20]], at=3, speed=50)
    assert len(route) == 1 and route[0]["duration"] == 0
    assert W.world_route_sample(route, 0) == [10, 20] and W.world_route_sample(route, 9) == [10, 20]


@pytest.mark.parametrize("rows,groups,per_group,tile", [(1, 1, 1, 16), (4, 3, 2, 32), (8, 6, 4, 32), (3, 2, 3, 64), (5, 4, 1, 128)])
def test_classroom_generator_is_valid_aligned_and_fully_walkable(rows, groups, per_group, tile):
    floor = classroom(rows=rows, groups=groups, per_group=per_group, tile=tile)
    blocked = W.world_blocked(floor["width"], floor["height"], tile, floor["props"])
    assert floor["width"] % tile == 0 and floor["height"] % tile == 0 and tile % 8 == 0
    desks = [p for p in floor["props"] if p["kind"] == "desk"]
    chairs = [p for p in floor["props"] if p["kind"] == "chair"]
    assert len(chairs) == rows * groups * per_group and len(desks) == len(chairs) + 1   # one chair per student desk, plus the teacher's desk
    start = [floor["player"]["x"] // tile, floor["player"]["y"] // tile]
    seen = {tuple(start)}
    frontier = [tuple(start)]
    for x, y in frontier:                                                    # every free tile can be reached from the door
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if 0 <= n[0] < len(blocked[0]) and 0 <= n[1] < len(blocked) and blocked[n[1]][n[0]] == "0" and n not in seen:
                seen.add(n)
                frontier.append(n)
    free = {(x, y) for y, row in enumerate(blocked) for x, v in enumerate(row) if v == "0"}
    assert seen == free
    assert all((c["x"] // tile, c["y"] // tile) in free for c in chairs)


def test_default_classroom_sizes_are_multiples_of_eight():
    floor = classroom()
    numbers = [floor["width"], floor["height"], floor["tile"], floor["player"]["x"] - 16, floor["player"]["y"] - 16]
    for p in floor["props"]:
        numbers += [p["x"], p["y"], p["w"], p["h"]]
    assert all(n % 8 == 0 for n in numbers)


def test_the_old_world_is_unchanged_by_the_new_fields():
    value = W.world_validate(W.example_data("world"))
    assert "avatars" not in value and all("tile" not in f and "props" not in f for f in value["floors"])
    html = W.world_html(W.example_data("world"))
    for marker in ("ui-prop", "data-blocked", "data-grid", "ui-world-pick", "data-step", "data-me", "ui-world-grid-only"):
        assert marker not in html


def test_school_html_has_props_grid_pad_and_picker_and_escapes_text():
    school = W.example_data("school")
    school["floors"][0]["spots"][0]["label"] = "<b>黒板</b>"
    html = W.world_html(school)
    assert html.count('class="ui-prop"') == len(W.world_validate(school)["floors"][0]["props"])
    assert 'data-grid' in html and html.count('data-step="') == 4 and 'data-me' in html and 'data-pick-open' in html
    assert html.count('data-emoji="') == len(school["avatars"]) and 'name="emoji"' in html and 'maxlength="32"' in html
    assert "<b>黒板</b>" not in html and "&lt;b&gt;" in html
    rows = html.split('data-blocked="')[1].split('"')[0].split(",")
    floor = W.world_validate(school)["floors"][0]
    assert len(rows) == floor["height"] // floor["tile"] and all(len(r) == floor["width"] // floor["tile"] for r in rows)
    assert set("".join(rows)) <= {"0", "1"}
    assert 'hidden' in html.split('class="ui-world-pick"')[1].split(">")[0]       # opened by the script only
    assert "[data-kind=desk]" in W.world_css(school) and "[data-kind=desk]" not in W.world_css(school, base=False)


@pytest.mark.parametrize("change", [
    lambda f: f.update(tile=12),                                              # not a multiple of 8
    lambda f: f.update(tile=7),
    lambda f: f.update(tile=48),                                              # does not divide the floor
    lambda f: f.update(tile=True),
    lambda f: f["props"].append({"kind": "sofa", "x": 0, "y": 0, "w": 32, "h": 32}),
    lambda f: f["props"].append({"kind": "desk", "x": 8, "y": 0, "w": 32, "h": 32}),   # off the tiles
    lambda f: f["props"].append({"kind": "desk", "x": 352, "y": 0, "w": 64, "h": 32}),  # outside the floor
    lambda f: f["props"].append({"kind": "desk", "x": 0, "y": 0, "w": 0, "h": 32}),
    lambda f: f["props"].append({"kind": "desk", "x": 0, "y": 0, "w": 32}),
    lambda f: f["props"].append({"kind": ["desk"], "x": 0, "y": 0, "w": 32, "h": 32}),
    lambda f: f.update(props=f["props"] * 11),                                 # too many
    lambda f: f["player"].update(x=80, y=176),                                # starts on a desk
    lambda f: f.update(extra=1),
])
def test_floor_validation_refuses(change):
    floor = W.classroom_floor()
    change(floor)
    with pytest.raises(ValueError):
        W.world_validate({"schema": W.WORLD_SCHEMA, "floors": [floor]})


def test_props_need_a_tile_grid_and_avatars_are_bounded():
    floor = W.classroom_floor()
    del floor["tile"]
    with pytest.raises(ValueError):
        W.world_validate({"schema": W.WORLD_SCHEMA, "floors": [floor]})
    base = {"schema": W.WORLD_SCHEMA, "floors": [W.classroom_floor()]}
    for bad in (["🙂", "🙂"], ["a", "a"], [f"{chr(0x1f600 + i)}" for i in range(25)], "🙂", [1], [""], ["x" * 17], [" a"], ["a "], ["a\nb"],
                ["a\u202eb"], ["a\u2028b"], ["\u3000a"]):
        with pytest.raises(ValueError):
            W.world_validate({**base, "avatars": bad})
    mixed = ["🙂", "A", "先生", "🐱たろう", "a b", "👨‍👩‍👧‍👦", "x" * 16, "<b>"]       # emoji, text or both: any one label
    assert W.world_validate({**base, "avatars": mixed})["avatars"] == mixed
    html = W.world_html({**base, "avatars": mixed})
    assert 'data-emoji="先生"' in html and 'data-emoji="&lt;b&gt;"' in html and 'data-emoji="<b>"' not in html
    floor = W.classroom_floor()
    floor["player"] = {**floor["player"], "emoji": "ねこ"}
    assert W.world_validate({**base, "floors": [floor]})["floors"][0]["player"]["emoji"] == "ねこ"
    for bad in ({"rows": 0}, {"groups": 7}, {"per_group": 5}, {"tile": 12}, {"tile": 8}):
        with pytest.raises(ValueError):
            W.classroom_floor(**bad)


def test_validation_is_idempotent_for_the_school_example():
    once = W.world_validate(W.example_data("school"))
    assert W.world_validate(once) == once


def _node26():
    return node26() or pytest.skip('existing Node 26+ required; no installation')


def test_node26_grid_route_matches_python_oracle():
    _node26()
    floor = classroom()
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    rng = random.Random(11)
    routes = [[[rng.uniform(-40, 420), rng.uniform(-40, 560)], [rng.uniform(-40, 420), rng.uniform(-40, 560)]] for _ in range(150)]
    routes += [[[16, 16], [16, 16]], [[176, 496], [80, 176]], [[176, 496], [80, 272]], [[0, 0], [383.9, 511.9]]]
    cases = [[GRID, 32, [10, 10], [140, 140]], [GRID, 32, [10, 10], [80, 48]], [["1"], 32, [5, 5], [20, 20]]]
    cases += [[blocked, 32, a, b] for a, b in routes]
    glyphs = ["🐱", " 🦖x ", "先生", "A", "", "   ", "x" * 16, "x" * 17, "a\nb", "a\u202eb", "a\u2028b", "🐱たろう", "👨‍👩‍👧‍👦", "a b", "\u3000a\u3000"]
    result = node_value(world_js(), '{routes:data.cases.map(([r,t,a,b])=>gridRoute(r,t,a,b)),'
                        'samples:data.cases.map(([r,t,a,b])=>{const route=motionRoute(gridRoute(r,t,a,b),2,96,384,512);return [0,0.4,1,2.5,7,1e6].map(x=>routeSample(route,2+x))}),'
                        'glyphs:data.glyphs.map(cleanAvatar)}', {'cases': cases, 'glyphs': glyphs})
    for (rows, tile, a, b), actual, samples in zip(cases, result['routes'], result['samples']):
        expected = W.world_route_points(rows, tile, a, b)
        assert len(actual) == len(expected)
        for got, want in zip(actual, expected):
            assert got == pytest.approx(want, abs=1e-9)
        route = W.world_route(expected, at=2, speed=96, width=384, height=512)
        for t, point in zip([0, 0.4, 1, 2.5, 7, 1e6], samples):
            assert point == pytest.approx(W.world_route_sample(route, 2 + t), abs=1e-9)
    assert result['glyphs'] == ['🐱', '🦖x', '先生', 'A', None, None, 'x' * 16, None, None, None, None, '🐱たろう', '👨‍👩‍👧‍👦', 'a b', 'a']
    for text in glyphs:                                                  # the page and the oracle accept the same labels
        try:
            W._world_avatar(text.strip())
            ok = True
        except ValueError:
            ok = False
        assert ok == (result['glyphs'][glyphs.index(text)] is not None), text


def test_direction_is_the_arrow_from_the_first_point_to_the_second():
    here = [100, 100]
    assert [W.world_direction(here, p) for p in ([200, 100], [200, 200], [100, 200], [0, 200], [0, 100], [0, 0], [100, 0], [200, 0])] == \
        ["➡️", "↘️", "⬇️", "↙️", "⬅️", "↖️", "⬆️", "↗️"]                         # screen y grows downward: a target below is ⬇️
    assert W.world_direction(here, [104, 96]) == W.WORLD_HERE == "📍"       # both axes within eps (8)
    assert W.world_direction(here, [104, 96], eps=0) == "↗️" and W.world_direction(here, [100, 100], eps=0) == "📍"
    assert W.world_direction([0, 0], [240, 99]) == "➡️" and W.world_direction([0, 0], [240, 101]) == "↘️"      # the 5/12 slope edge
    assert W.world_direction([5, 5], [5, 5]) == "📍"
    for a, b in ((here, [180, 7]), (here, [3, 250]), ([9, 8], [90, 100])):    # swapping the points turns the arrow around
        turned = {"➡️": "⬅️", "↘️": "↖️", "⬇️": "⬆️", "↙️": "↗️", "⬅️": "➡️", "↖️": "↘️", "⬆️": "⬇️", "↗️": "↙️"}
        assert W.world_direction(b, a) == turned[W.world_direction(a, b)]


def test_points_come_from_the_centre_or_an_edge_of_each_object():
    desk = {"x": 64, "y": 32, "w": 96, "h": 32}
    assert W.world_point(desk) == (112, 48) and W.world_point(desk, "center") == (112, 48)
    assert [W.world_point(desk, at) for at in ("left", "right", "top", "bottom")] == [(64, 48), (160, 48), (112, 32), (112, 64)]
    assert [W.world_point((0, 0, 8, 8), at) for at in ("top-left", "top-right", "bottom-left", "bottom-right")] == [(0, 0), (8, 0), (0, 8), (8, 8)]
    assert W.world_point((50, 60, 0, 0)) == (50, 60)                          # a spot or a person: a rect with no size
    with pytest.raises(ValueError):
        W.world_point(desk, "middle")
    # a chair centred under the desk: its top edge meets the desk's bottom edge (here), and from the chair's centre the desk is straight up
    chair = (96, 64, 32, 32)
    assert W.world_direction(W.world_point(chair, "top"), W.world_point(desk, "bottom"), eps=0) == "📍"
    assert W.world_direction(W.world_point(chair), W.world_point(desk)) == "⬆️"


def test_arrow_names_an_anchor_in_any_form():
    assert [W.world_arrow_anchor(a) for a in ("↘️", "↘", "↘\ufe0e", "⬅", "⬅️", "←", "→", "➡️", "↑", "⬆️", "↓", "⬇", "↖", "↗️", "↙", "🎯", "📍")] == \
        ["bottom-right"] * 3 + ["left"] * 3 + ["right"] * 2 + ["top"] * 2 + ["bottom"] * 2 + ["top-left", "top-right", "bottom-left", "center", "center"]
    assert all(W.world_arrow_anchor(a) in W.WORLD_ANCHORS for a in "←→↑↓↖↗↙↘🎯")
    for bad in ("", "x", "➕", "↘️↘️"):
        with pytest.raises(ValueError):
            W.world_arrow_anchor(bad)


def test_node26_direction_matches_python_oracle():
    _node26()
    rng = random.Random(23)
    cases = [[[rng.randint(-300, 300), rng.randint(-300, 300)], [rng.randint(-300, 300), rng.randint(-300, 300)], rng.choice([0, 8, 16, 32])] for _ in range(400)]
    cases += [[[rng.uniform(-300, 300), rng.uniform(-300, 300)], [rng.uniform(-300, 300), rng.uniform(-300, 300)], rng.choice([0.5, 8, 24])] for _ in range(400)]
    cases += [[[0, 0], [240, 99], 8], [[0, 0], [240, 101], 8], [[0, 0], [99, 240], 8], [[0, 0], [101, 240], 8], [[3, 3], [3, 3], 0], [[0, 0], [8, 8], 8], [[0, 0], [9, 8], 8]]
    got = node_value(world_js(), 'data.map(([a,b,e])=>direction(a,b,e))', cases)
    assert got == [W.world_direction(a, b, e) for a, b, e in cases]
    assert {"➡️", "↘️", "⬇️", "↙️", "⬅️", "↖️", "⬆️", "↗️", "📍"} == set(got)


def _world(**extra):
    spec = W.example_data("school")
    spec.pop("tools", None)
    return {**spec, **extra}


def test_tools_map_an_emoji_to_one_feature_and_are_checked():
    world = W.world_validate(_world(tools={"🏫": {"label": "学校", "body": "ここは学校です。"}, "🛝": {"floor": "yard", "slot": "side"},
                                            "🗺️": {"label": "地図", "label_en": "Map", "spots": ["classroom-board", "flowers"]}}))
    assert list(world["tools"]) == ["🏫", "🛝", "🗺️"]
    assert world["tools"]["🛝"] == {"label": "🛝", "label_en": "🛝", "slot": "side", "floor": "yard"}       # the emoji is the default name
    assert world["tools"]["🗺️"]["spots"] == ["classroom-board", "flowers"] and world["tools"]["🏫"]["slot"] == "head"
    assert W.world_validate(world) == world                                                              # the expanded form is ordinary data
    assert "tools" not in W.world_validate(_world())
    bad = [{"🏠": {"body": "x"}}, {"⚙️": {"body": "x"}}, {"🌐": {"body": "x"}}, {"a": {"body": "x"}},                # the page's own icons; plain ASCII
           {"🏫": {}}, {"🏫": {"body": "x", "floor": "yard"}}, {"🏫": {"floor": "roof"}}, {"🏫": {"spots": []}}, {"🏫": {"spots": ["nope"]}},
           {"🏫": {"body": "x", "slot": "top"}}, {"🏫": {"body": "x", "icon": "y"}}, {"🏫": "x"}, {f"{chr(0x1F600 + i)}": {"body": "x"} for i in range(9)}]
    for tools in bad:
        with pytest.raises(ValueError):
            W.world_validate(_world(tools=tools))
    with pytest.raises(ValueError):
        W.world_validate({"schema": W.WORLD_SCHEMA, "shots": [{"id": "a", "label": "a", "title": "a"}], "tools": {"🏫": {"body": "x"}}})
    with pytest.raises(ValueError):
        W.world_validate(_world(shell="yes"))


def test_a_shell_world_is_icons_in_a_header_a_side_and_a_footer():
    html = W.world_html(_world(tools={"🗺️": {"label": "地図", "label_en": "Map", "spots": ["classroom-board", "flowers"]},
                                       "🏫": {"label": "学校", "body": "ここは学校です。"}, "🛝": {"label": "校庭", "floor": "yard", "slot": "side"}}))
    head = html[html.index('<header class="ui-world-head">'):html.index("</header>")]
    side = html[html.index('<div class="ui-world-side">'):html.index('<footer class="ui-world-foot">')]
    assert [m for m in ("🏠", "🗺️", "🏫", "⭐", "⚙️") if m in head] == ["🏠", "🗺️", "🏫", "⭐", "⚙️"] and head.index("🏠") < head.index("🗺️") < head.index("⭐") < head.index("⚙️")
    assert "☰" in side and "⋯" in side and "🛝" in side and 'for="school-floor-yard"' in side and "🚪" in html[html.index("<footer"):]
    assert 'aria-label="ホーム" title="ホーム" data-t="home"' in head and 'aria-label="地図" title="地図" data-labels="{&quot;ja&quot;:&quot;地図&quot;,&quot;en&quot;:&quot;Map&quot;}"' in head
    assert "<select data-lang" in head and head.count("<option ") == 11 + 3 and "<select data-names-pick" in head and "data-pick-open" in head and "data-pick-open" in head and 'class="ui-world-pause"' in head and " data-me " in side         # global in the header, local in the side
    assert 'class="ui-world-pause"' not in side and "data-pick-open" not in side
    assert '<a href="#school-spot-flowers" data-x="480" data-y="96" data-floor="yard">' in html                                  # a place on another floor shows 🚪, not an arrow
    assert html.count("ui-world-star") >= 5 and 'class="ui-world-rows ui-world-favs"' in head
    assert "✖️" in html   and ">Close<" not in html and "ほかの絵文字・文字 <input" not in html                                   # icons, with the words in aria-label
    assert 'data-grid data-shell' in html and ' data-shell' in html
    old = W.world_html({"schema": W.WORLD_SCHEMA, "floors": [{"id": "a", "label": "A", "width": 128, "height": 128, "spots": [{"id": "s", "x": 8, "y": 8, "label": "S"}]}]})
    assert "ui-world-head" not in old and "data-shell" not in old and ">Close<" in old                          # worlds without a grid keep their layout and markup


def test_any_world_may_ask_for_the_shell_and_a_catalogue_can_too():
    cat = W.catalogue_world([{"id": "a", "label": "A", "group": "g1", "emoji": "🌍"}, {"id": "b", "label": "B", "group": "g2"}], shell=True,
                             tools={"💡": {"label": "ヒント", "body": "押すと詳しく出ます。"}})
    html = W.world_html(cat)
    assert " data-shell" in html and "data-grid" not in html and "ui-world-dpad" not in html and " data-me " not in html and "💡" in html
    assert 'class="ui-world-goto"' in html and 'data-floor="f1"' in html and 'data-floor="f2"' in html
    plain = W.world_html(W.catalogue_world([{"id": "a", "label": "A", "group": "g1"}]))
    assert "data-shell" not in plain and "ui-world-head" not in plain
    css = W.world_css(cat)
    assert '.ui-world-spots[data-floor="f1"]{display:block}' in css and '.ui-world-spots[data-floor' not in W.world_css(W.catalogue_world([{"id": "a", "label": "A", "group": "g1"}]))


def test_a_floor_can_ask_for_a_classroom_in_plain_json():
    params = {"rows": 3, "groups": 2, "per_group": 3, "tile": 32}
    world = {"schema": W.WORLD_SCHEMA, "avatars": ["🙂"], "floors": [{"id": "room", "label": "教室A", "classroom": params}]}
    floor = W.world_validate(world)["floors"][0]
    built = W.world_validate({"schema": W.WORLD_SCHEMA, "floors": [W.classroom_floor(**params, id="room", label="教室A")]})["floors"][0]
    assert floor == built and "classroom" not in floor
    assert W.world_validate(W.world_validate(world)) == W.world_validate(world)            # the expanded form is ordinary data
    default = W.world_validate({"schema": W.WORLD_SCHEMA, "floors": [{"classroom": {}}]})["floors"][0]
    assert default["id"] == "classroom" and default["label"] == "教室" and default["tile"] == 32


def test_classroom_floor_keeps_what_is_given_beside_it_and_mixes_with_ordinary_floors():
    spot = {"id": "clock", "x": 192, "y": 64, "label": "時計", "body": "あと5分"}
    mixed = {"schema": W.WORLD_SCHEMA, "floors": [
        {"id": "room", "label": "教室", "classroom": {}, "spots": [spot], "player": {"emoji": "🐱", "x": 176, "y": 496, "speed": 64}},
        {"id": "yard", "label": "校庭", "width": 128, "height": 128, "spots": [{"id": "bar", "x": 64, "y": 64, "label": "鉄棒", "body": "-"}]}]}
    room, yard = W.world_validate(mixed)["floors"]
    assert [s["id"] for s in room["spots"]] == ["clock"] and room["player"]["emoji"] == "🐱" and room["player"]["speed"] == 64
    assert room["props"] and "tile" not in yard and "props" not in yard


@pytest.mark.parametrize("floor", [
    {"id": "r", "label": "x", "classroom": {"rows": 0}},
    {"id": "r", "label": "x", "classroom": {"tile": 12}},
    {"id": "r", "label": "x", "classroom": {"depth": 3}},
    {"id": "r", "label": "x", "classroom": "big"},
    {"id": "r", "label": "x", "classroom": [4, 3]},
    {"id": "r", "label": "x", "classroom": {}, "width": 640},                 # sizes come from the generator
    {"id": "r", "label": "x", "classroom": {}, "props": []},
    {"id": 7, "label": "x", "classroom": {}},
    {"id": "R!", "label": "x", "classroom": {}},
    {"id": "r", "label": ["x"], "classroom": {}},
    {"id": "r", "label": "x", "classroom": {"rows": True}},
])
def test_classroom_directive_refuses_bad_data(floor):
    with pytest.raises(ValueError):
        W.world_validate({"schema": W.WORLD_SCHEMA, "floors": [floor]})


ONE_LINER = {"schema": W.WORLD_SCHEMA, "avatars": ["🙂", "🐱"], "floors": [{"id": "room", "label": "教室", "classroom": {"rows": 5, "groups": 3}}]}


def _cli(*args, stdin):
    return subprocess.run([sys.executable, "scripts/world.py", *args], input=stdin.encode("utf-8"), capture_output=True, cwd=ROOT, timeout=60)


def test_world_page_from_stdin_equals_the_page_from_a_file(tmp_path):
    expected = W.world_document(ONE_LINER)
    result = _cli("page", "-", stdin=json.dumps(ONE_LINER, ensure_ascii=False))
    assert result.returncode == 0 and result.stdout.decode("utf-8") == expected
    (tmp_path / "w.json").write_text(json.dumps(ONE_LINER, ensure_ascii=False), encoding="utf-8")
    assert _cli("page", str(tmp_path / "w.json"), stdin="").stdout.decode("utf-8") == expected
    piped = _cli("page", "-", stdin=_cli("example", "school", stdin="").stdout.decode("utf-8"))   # the pipe in one line
    assert piped.returncode == 0 and piped.stdout.decode("utf-8") == W.world_document(W.example_data("school"))


@pytest.mark.parametrize("bad", ["not json", "", "[]", json.dumps({**ONE_LINER, "floors": [{"id": "r", "label": "x", "classroom": {"rows": 99}}]})])
def test_world_from_stdin_reports_bad_specs_without_a_traceback(bad):
    result = _cli("page", "-", stdin=bad)
    assert result.returncode == 2 and result.stdout == b"" and b"Traceback" not in result.stderr and b"error" in result.stderr


def test_world_from_stdin_is_bounded():
    result = _cli("page", "-", stdin=" " * (ui.PATTERN_MAX_INPUT + 10))
    assert result.returncode == 2 and b"larger than" in result.stderr


def _png(color, mark=None, size=(64, 48)):
    if isinstance(color, str):
        color = {"black": (0, 0, 0), "white": (255, 255, 255)}[color]
    rectangles = [((8, 8, 24, 24), mark)] if mark else []
    return rgb_png(*size, color, rectangles=rectangles)


def test_demo_gif_keeps_real_timing_and_decodes_to_the_same_pictures():
    pytest.importorskip("PIL")
    from PIL import Image, ImageChops
    shots = [(10.0, _png((13, 17, 23))), (10.003, _png((13, 17, 23), (255, 0, 0))), (10.5, _png((13, 17, 23), (0, 255, 0))), (11.0, _png((0, 0, 255)))]
    gif = W.encode(shots, tail_ms=700)
    image = Image.open(io.BytesIO(gif))
    assert gif[:6] == b"GIF89a" and image.n_frames == 4 and image.info["loop"] == 0
    delays = []
    for index in range(image.n_frames):
        image.seek(index)
        delays.append(image.info["duration"])
    assert delays == [20, 500, 500, 700]                       # 3 ms is lifted to 20 ms; real gaps round to 10 ms; the tail is the last frame
    for index, (_, png) in enumerate(shots):                   # delta frames still show exactly what was on screen
        image.seek(index)
        assert ImageChops.difference(image.convert("RGB"), Image.open(io.BytesIO(png)).convert("RGB")).getbbox() is None


def test_demo_gif_merges_still_frames_and_can_shrink():
    pytest.importorskip("PIL")
    from PIL import Image
    shots = [(0.0, _png("black")), (0.1, _png("black")), (0.2, _png("black")), (0.3, _png("white"))]
    image = Image.open(io.BytesIO(W.encode(shots, width=32)))
    assert image.size == (32, 24) and image.n_frames == 2


def test_demo_recorder_refuses_before_it_opens_a_browser(tmp_path, capsys):
    assert set(W.SCENES) >= {"pick", "avatar-text", "keys", "tap", "phone", "menu", "header", "floors", "oneliner", "lands", "real", "tokyo", "london", "paris"}
    assert {W.SCENES[n].world for n in ("tokyo", "london", "paris")} == {"cities"}
    assert W.SCENES["lands"].world == "overworld" and W.SCENES["real"].world == "overworld" and W.SCENES["keys"].world == "school"
    with pytest.raises(ValueError, match="unknown scene: nope"):
        W.record(tmp_path, ["nope"])
    (tmp_path / "school-pick.gif").write_bytes(b"GIF89a")
    with pytest.raises(FileExistsError, match="--force"):
        W.record(tmp_path, ["pick"])
    assert (tmp_path / "school-pick.gif").read_bytes() == b"GIF89a"
    with pytest.raises(SystemExit) as exit_info:
        W.main(["record", str(tmp_path), "--only", "pick"])
    assert exit_info.value.code == 1 and "refusing to overwrite" in capsys.readouterr().err


def test_demo_recorder_cli_checks_before_a_browser(tmp_path):
    """record: --only is a choice, and nothing touches a browser before the arguments are checked."""
    with pytest.raises(SystemExit) as exit_info:
        W.main(["record", str(tmp_path), "--only", "nope"])
    assert exit_info.value.code == 2
    seen = {}

    def fake_record(out, names, **kwargs):
        seen.update(out=out, names=names, **kwargs)
        return []

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(W, "record", fake_record)
    try:
        W.main(["record", str(tmp_path), "--only", "pick", "--git-commit", "--prefix", "ci-", "--suffix=-chrome", "--timestamp"])
    finally:
        monkeypatch.undo()
    assert seen == {"out": tmp_path, "names": ["pick"], "chrome": None, "width": None, "force": False, "prefix": "ci-", "suffix": "-chrome",
                    "run_details": ["git-commit", "timestamp"]}


def test_demo_zoom_goes_in_toward_the_anchor_and_stays_on_the_real_clock():
    pytest.importorskip("PIL")
    from PIL import Image

    class Page:                                                 # a screenshot of a red corner (bottom left) on blue
        def screenshot(self, type):
            return rgb_png(40, 40, (0, 0, 255), rectangles=[((0, 20, 20, 40), (255, 0, 0))])

    camera = W.Camera(Page())
    camera.zoom(anchor=(0, 1), factor=2, steps=4, hold_ms=300)
    assert len(camera.shots) == 4                               # three steps in, then the peak
    times = [t for t, _ in camera.shots]
    assert times == sorted(times) and round((times[-1] - times[-2]) * 1000) == 60 and round((times[1] - times[0]) * 1000) == 60
    frames = [Image.open(io.BytesIO(png)).convert("RGB") for _, png in camera.shots]
    assert frames[3].getpixel((20, 20)) == (255, 0, 0)          # at the peak the bottom-left corner fills the picture
    assert W.time.monotonic() >= times[-1] + 0.3      # the real clock was let catch up (the peak is held 300 ms)
    for anchor in ("↙️", "↙", "bottom-left", (0, 1)):          # an arrow emoji, an anchor name or a fraction: the same corner
        camera = W.Camera(Page())
        camera.zoom(anchor=anchor, factor=2, steps=2, hold_ms=20)
        assert Image.open(io.BytesIO(camera.shots[-1][1])).convert("RGB").getpixel((20, 20)) == (255, 0, 0), anchor
    with pytest.raises(ValueError):
        W.Camera(Page()).zoom(anchor="x")


def test_the_chrome_speaks_the_eleven_languages_of_flutter_navigation_basic():
    codes = [code for code, _ in W.WORLD_LANGS]
    assert codes == ["ja", "en", "fr", "es", "pt", "ar", "zh", "ru", "id", "de", "sw"]
    for key, words in W.WORLD_TEXT.items():                                   # every word in every language, none left as a stand-in
        assert len(words) == 11 and all(w.strip() for w in words), key
        assert len(set(words)) >= 6, key                                       # a few are the same word in several languages (Hotel-like), not all
    runtime = ("invalid", "camera", "photo", "clear", "unavailable")           # said by the script (a validity message, the ask() choices), not in the markup
    assert all(f'data-t="{k}"' in W.world_html(W.EXAMPLES["overworld"]) or k in runtime for k in W.WORLD_TEXT)
    assert all(f"'{k}'" in W.WORLD_JS for k in runtime[1:])
    assert W.WORLD_JS.startswith(W.WORLD_MOTION_JS + W.WORLD_SHARED_JS + W.WORLD_TEXT_JS)
    catalogue = json.loads(W.WORLD_TEXT_JS.split("WORLD_TEXT=")[1].rstrip(";\n"))
    assert catalogue == {k: list(v) for k, v in W.WORLD_TEXT.items()}
    assert 'lang="ar">العربية</option>' in W.world_html(_world())


def test_a_tool_can_name_itself_in_the_other_languages():
    world = W.world_validate(_world(tools={"🗺️": {"label": "地図", "label_en": "Map", "labels": {"fr": "Carte", "de": "Karte"}, "spots": ["flowers"]}}))
    assert world["tools"]["🗺️"]["labels"] == {"fr": "Carte", "de": "Karte"}
    html = W.world_html(world)
    assert "&quot;fr&quot;:&quot;Carte&quot;" in html and "&quot;de&quot;:&quot;Karte&quot;" in html
    assert "labels" not in W.world_validate(_world(tools={"🗺️": {"spots": ["flowers"]}}))["tools"]["🗺️"]
    for bad in ({"ja": "x"}, {"en": "x"}, {"xx": "x"}, {"fr": ""}, {"fr": "x" * 25}, ["fr"], "fr"):
        with pytest.raises(ValueError):
            W.world_validate(_world(tools={"🗺️": {"labels": bad, "spots": ["flowers"]}}))


# ---- lands: the same grid, other objects --------------------------------------------------------------------------------------------

def _reach(floor):
    """Tiles the player can walk to, and the walking grid they were found on."""
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    return set(W.world_reach(blocked, (floor["player"]["x"] // floor["tile"], floor["player"]["y"] // floor["tile"]))), blocked


@pytest.mark.parametrize("theme", sorted(W.LAND_THEMES))
@pytest.mark.parametrize("size", [(24, 16, 32), (12, 12, 32), (48, 32, 64), (30, 20, 16)])
def test_every_land_is_valid_and_its_town_and_landmark_can_be_walked_to(theme, size):
    cols, rows, tile = size
    for seed in (0, 1, 7, 12345):
        floor = W.land_floor(theme, cols, rows, seed=seed, tile=tile, id=theme)
        checked = W.world_validate({"schema": W.WORLD_SCHEMA, "id": "w", "floors": [floor]})["floors"][0]
        assert checked["props"] == floor["props"] and checked["player"] == floor["player"] and len(floor["props"]) <= 512 and floor["width"] == cols * tile and floor["height"] == rows * tile
        assert all(v % 8 == 0 for q in floor["props"] for v in (q["x"], q["y"], q["w"], q["h"]))
        reach, blocked = _reach(floor)
        for spot in floor["spots"]:
            cell = (spot["x"] // tile, spot["y"] // tile)
            assert cell in reach and blocked[cell[1]][cell[0]] == "0", (theme, seed, spot["id"])
        assert [s["id"] for s in floor["spots"]] == [f"{theme}-town", f"{theme}-landmark"]


def test_a_land_is_the_same_every_time_and_the_seed_makes_another():
    assert W.land_floor("forest", seed=4) == W.land_floor("forest", seed=4)
    assert W.land_floor("forest", seed=4) != W.land_floor("forest", seed=5)
    assert W.land_floor("meadow", seed=4)["props"] != W.land_floor("forest", seed=4)["props"]
    assert W.land_floor("meadow")["label"] == W.LAND_THEMES["meadow"]["label"] and W.land_floor("meadow", label="北")["label"] == "北"
    for bad in (dict(theme="moon"), dict(cols=11), dict(rows=11), dict(cols=49), dict(tile=20), dict(tile=128, cols=40), dict(seed=-1), dict(seed=2**31)):
        with pytest.raises(ValueError):
            W.land_floor(**bad)


def test_ground_opens_the_tiles_it_covers_and_the_other_kinds_only_block():
    props = [{"kind": "water", "x": 0, "y": 0, "w": 128, "h": 32}, {"kind": "bridge", "x": 32, "y": 0, "w": 32, "h": 32},
             {"kind": "tree", "x": 0, "y": 32, "w": 64, "h": 32}, {"kind": "road", "x": 0, "y": 32, "w": 32, "h": 32}]
    assert W.world_blocked(128, 64, 32, props) == ["1011", "0100"]                 # a bridge through water, a road through trees
    desk_then_rug = [{"kind": "desk", "x": 0, "y": 0, "w": 32, "h": 32}, {"kind": "rug", "x": 0, "y": 0, "w": 32, "h": 32}]
    assert W.world_blocked(32, 32, 32, desk_then_rug) == ["1"]                     # chairs and rugs never open anything: the classroom is as it was
    assert set(W.WORLD_GROUND) == {"grass", "sand", "road", "bridge"} and all(k in W.WORLD_PROPS for k in W.WORLD_LOOK)


def test_a_land_is_one_line_of_json_and_the_school_is_untouched():
    spec = {"schema": W.WORLD_SCHEMA, "id": "w", "floors": [{"id": "n", "label": "北", "land": {"theme": "coast", "seed": 3}}]}
    floor = W.world_validate(spec)["floors"][0]
    assert {k: v for k, v in floor.items() if k != "spots"} == {k: v for k, v in W.land_floor("coast", seed=3, id="n", label="北").items() if k != "spots"}
    assert [(s["id"], s["x"], s["y"]) for s in floor["spots"]] == [(s["id"], s["x"], s["y"]) for s in W.land_floor("coast", seed=3, id="n")["spots"]]
    own = W.world_validate({**spec, "floors": [{"id": "n", "land": {"theme": "desert"}, "spots": [{"id": "x", "x": 64, "y": 64, "label": "x"}]}]})["floors"][0]
    assert [s["id"] for s in own["spots"]] == ["x"] and own["props"] == W.land_floor("desert", id="n")["props"]
    for bad in ({"land": {"theme": "meadow", "color": "red"}}, {"land": "meadow"}, {"land": {}, "classroom": {}}, {"land": {}, "width": 64}):
        with pytest.raises(ValueError):
            W.world_validate({**spec, "floors": [{"id": "n", **bad}]})
    school = W.world_css(W.example_data("school"))
    assert "data-kind=water" not in school and "svg+xml" not in school                # no land rule leaks into a world without lands


def test_the_overworld_example_swaps_objects_and_ships_only_the_kinds_it_uses():
    spec = W.example_data("overworld")
    world = W.world_validate(spec)
    assert [f["id"] for f in world["floors"]] == ["meadow", "forest", "mountain", "desert", "coast", "castle", "real"] and W.world_validate(world) == world
    css = W.world_css(spec, base=False)                                             # only this world's rules, not the fixed ones
    for kind in ("grass", "sand", "road", "water", "tree", "cactus", "mountain", "house", "castle"):
        assert f".ui-prop[data-kind={kind}]" in css, kind
    assert ".ui-prop[data-kind=bridge]" not in css and ".ui-prop[data-kind=desk]" not in css
    assert "center/contain no-repeat" in css and css.count("0 0/var(--tile) var(--tile)") >= 5       # the castle once, the rest once per tile
    html = W.world_html(spec)
    assert html.count('class="ui-floor"') == 7 and 'data-real style="width:384px;height:384px' in html and world["floors"][-1]["real"] is True and "ui-world-goto" in html and "🧭" in html and 'data-t="home"' in html
    assert W.world_document(spec) == W.world_document(W.example_data("overworld"))
    assert W.example_data("overworld") == json.loads(json.dumps(W.EXAMPLES["overworld"]))


def test_a_real_floor_asks_for_a_photo_or_camera_and_other_worlds_do_not():
    floor = {"id": "r", "label": "R", "width": 128, "height": 128, "tile": 32, "real": True, "player": {"emoji": "🙂", "x": 48, "y": 48},
             "spots": [{"id": "a", "label": "A", "x": 64, "y": 64, "body": "b"}]}
    spec = {"schema": "web-ui-world/1", "id": "w", "floors": [floor]}
    world = W.world_validate(spec)
    assert world["floors"][0]["real"] is True and W.world_validate(world) == world
    assert "real" not in W.world_validate({**spec, "floors": [{k: v for k, v in floor.items() if k != "real"}]})["floors"][0]
    html = W.world_html(spec)
    assert 'data-real style="width:128px' in html and 'class="ui-world-real" data-real hidden' in html and 'data-t="backdrop"' in html
    plain = W.world_html({**spec, "floors": [{k: v for k, v in floor.items() if k != "real"}]})
    assert 'data-real style=' not in plain and 'class="ui-world-real"' not in plain                 # no button where no floor is real
    land = W.world_validate({"schema": "web-ui-world/1", "id": "l", "floors": [{"id": "x", "land": {"theme": "meadow"}, "real": True}]})
    assert land["floors"][0]["real"] is True and land["floors"][0]["props"]                          # a land can be real too: props over the picture
    for bad in ("yes", 1, None, []):
        with pytest.raises(ValueError):
            W.world_validate({**spec, "floors": [{**floor, "real": bad}]})


def test_node26_walks_a_land_like_python():
    _node26()
    floor = W.land_floor("forest", seed=9)
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    cases = [[blocked, floor["tile"], [floor["player"]["x"], floor["player"]["y"]], [s["x"], s["y"]]] for s in floor["spots"]]
    cases.append([blocked, floor["tile"], [floor["player"]["x"], floor["player"]["y"]], [48, 48]])
    for (rows, tile, a, b), actual in zip(cases, node_value(world_js(), "data.map(([r,t,a,b])=>gridRoute(r,t,a,b))", cases)):
        want = W.world_route_points(rows, tile, a, b)
        assert len(actual) == len(want) and all(g == pytest.approx(w, abs=1e-9) for g, w in zip(actual, want))


def test_floor_selection_updates_footer_before_animation_or_change_event():
    """The actual floor setter keeps the footer in sync, including favourite/hash jumps."""
    _node26()
    setter = W.WORLD_JS.split('setFloor=', 1)[1].split(';\nconst floor=', 1)[0]
    node_js('''const assert = require('node:assert/strict');
const select = {value: 'yard'};
const events = [];
const radios = Object.fromEntries(['classroom', 'yard'].map(value => [value, {
  value, checked: false,
  dispatchEvent(event) { events.push([value, select.value, event.type, event.bubbles]); }
}]));
const radio = (kind, value) => radios[value];
let hasFooter = true;
const el = {querySelector(selector) {
  assert.equal(selector, '.ui-world-goto');
  return hasFooter ? select : null;
}};
const setFloor = ''' + setter + ''';
setFloor('classroom');
assert.equal(radios.classroom.checked, true);
assert.equal(select.value, 'classroom');
assert.deepEqual(events, []);
setFloor('yard', true);
assert.equal(select.value, 'yard');
assert.deepEqual(events, [['yard', 'yard', 'change', true]]);
setFloor('missing', true);
assert.equal(select.value, 'yard');
assert.equal(events.length, 1);
hasFooter = false;
setFloor('classroom', true);
assert.equal(radios.classroom.checked, true);
assert.equal(events.length, 2);
''')


def test_the_name_layer_is_names_dots_or_off_and_switches_in_the_header():
    """Layers like a slide's z-order: ground < names < marks < player < sheet. data-names picks where plain spots sit."""
    spec = W.example_data("school")
    assert W.world_validate(spec)["names"] == "names"
    assert W.world_validate(W.example_data("cities"))["names"] == "dots"
    with pytest.raises(ValueError, match="names is names"):
        W.world_validate({**spec, "names": "pills"})
    html = W.world_html({**spec, "names": "dots"})
    assert 'data-names="dots"' in html
    assert '<option value="dots" selected>●</option>' in html
    css = W.world_css(spec)
    assert "--ui-layer-ground:0;--ui-layer-name:1;--ui-layer-mark:2;--ui-layer-player:3;--ui-layer-sheet:4" in css
    assert ".ui-world[data-names=dots] .ui-spot:not([data-sign]):not([data-near]):not(:hover):not(:focus-visible)" in css


def test_a_mark_is_an_emoji_in_place_of_the_dot_scaled_by_the_world():
    """A spot's mark (or its category's, through place_floor marks=) replaces the dot and leads the name; mark_scale sets every mark's width and height."""
    cities = W.world_validate(W.example_data("cities"))
    assert cities["mark_scale"] == [1.5, 1.5]
    assert {s["category"]: s.get("mark") for f in cities["floors"] for s in f["spots"]} == {"exit": "🚪", "station": "🚉", "terminus": "🚆", "sign": None}
    html = W.world_html(W.example_data("cities"))
    assert 'style="--mark-x:1.5;--mark-y:1.5"' in html
    assert "top:1232px;--mark:'🚪'\"" in html
    css = W.world_css(W.example_data("cities"))
    assert 'content:var(--mark,"●")' in css and "transform:scale(var(--mark-x,1),var(--mark-y,1))" in css
    spec = W.example_data("school")
    assert W.world_validate(spec)["mark_scale"] == [1, 1] and ' style="--mark-x' not in W.world_html(spec)
    with pytest.raises(ValueError, match="mark_scale is"):
        W.world_validate({**spec, "mark_scale": [1, 9]})
    floor = {**spec["floors"][0], "spots": [{**spec["floors"][0]["spots"][0], "mark": "🪑"}, {**spec["floors"][0]["spots"][1], "mark": "a b"}]}
    with pytest.raises(ValueError, match="a mark is"):
        W.world_validate({**spec, "floors": [floor]})
    with pytest.raises(ValueError, match="marks is"):
        W.place_floor([{"id": "a", "label": "A", "lat": 35.0, "lon": 139.0}], marks={"Bad Key": "x"})
    own = W.place_floor([{"id": "a", "label": "A", "lat": 35.0, "lon": 139.0, "category": "cafe", "mark": "☕"}, {"id": "b", "label": "B", "lat": 35.001, "lon": 139.0, "category": "cafe"}],
                         marks={"cafe": "🍰"})
    assert [s.get("mark") for s in own["spots"]] == ["☕", "🍰"]                                   # a point's own mark wins over its category's


# ═══ 🏃 motion ════════════════════════════════════════════════════════════════════════════════════════════
# Python oracle and emitted browser projection: no browser/Python runtime dependency.

def test_walk_constant_velocity_clamp_and_hold():
    s = W.world_walk([10, 20], [70, 100], speed=10, at=5)
    assert s['duration'] == 10
    assert W.world_motion_sample(s, 0) == [10, 20]
    assert W.world_motion_sample(s, 10) == [40, 60]
    assert W.world_motion_sample(s, 1e9) == [70, 100]
    assert W.world_walk([0, 0], [-20, 2000], width=64, height=128)['to'] == [0, 128]
    still = W.world_walk([3, 4], [3, 4])
    assert W.world_motion_sample(still, 0) == [3, 4]


def test_retarget_pause_resume_and_frame_rate_independence():
    original = W.world_walk([0, 0], [100, 0], speed=10)
    point = W.world_motion_sample(original, 3)
    retarget = W.world_walk(point, [30, 100], at=3, speed=10)
    assert W.world_motion_sample(retarget, 3) == point
    # A pause is a frozen simulation clock. Resume uses elapsed, not wall time.
    for _ in range(60):
        assert W.world_motion_sample(retarget, 3) == point
    assert W.world_motion_sample(retarget, 5) == [30, 20]
    for fps in (24, 60, 144):
        for i in range(fps * 5):
            W.world_motion_sample(retarget, i / fps)
        assert W.world_motion_sample(retarget, 8) == [30, 50]


def test_seeded_villagers_continuous_bounded_and_exact_speed():
    for seed in range(20):
        path = W.villager_path(seed, 128, 64, speed=17, stops=64)
        assert path == W.villager_path(seed, 128, 64, speed=17, stops=64)
        assert path['keys'][0][1:] == path['keys'][-1][1:]
        assert len(path['keys']) == 130
        for a, b in zip(path['keys'], path['keys'][1:]):
            assert 0 <= b[1] <= 128 and 0 <= b[2] <= 64
            distance = math.dist(a[1:], b[1:])
            if distance:
                duration = (b[0] - a[0]) / 100 * path['duration']
                assert distance / duration == pytest.approx(17, abs=1e-9)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), -float('inf'), 10**1000, True, '3', None])
def test_nonfinite_or_non_numeric_inputs(bad):
    for call in (lambda: W.world_walk([bad, 0], [1, 2]),
                 lambda: W.world_walk([0, 0], [1, 2], speed=bad),
                 lambda: W.world_motion_sample(W.world_walk([0, 0], [1, 2]), bad),
                 lambda: W.board_clock(bad, 0),
                 lambda: W.travel_seconds(0, 0, 10, 10, bad)):
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize('kwargs', [{'stops': 65}, {'seed': -1}, {'speed': 0}, {'width': 4097}, {'margin': 100}])
def test_plan_resource_bounds(kwargs):
    with pytest.raises(ValueError):
        W.villager_path(**{'seed': 1, 'width': 128, 'height': 64, **kwargs})


@pytest.mark.parametrize('now,at,expected', [(600,630,30),(600.1,630,30), (629.999,630,1), (630,630,0), (630.001,630,1440), (1439.5,0,1)])
def test_daily_countdown_seconds_ceil_exact_target_and_tomorrow(now, at, expected):
    assert W.minutes_until(now, at) == expected


@pytest.mark.parametrize('now,offset,clock,minutes', [(0,0,'00:00',0), (0,-60,'23:00',1380), (86399,540,'08:59',539+59/60)])
def test_clock_explicit_seconds_offset_and_day_rollover(now, offset, clock, minutes):
    result = W.board_clock(now, offset)
    assert result['clock'] == clock
    assert result['minutes'] == pytest.approx(minutes)


def test_html_safe_accessible_and_offset_opt_in():
    value = W.example_data('world')
    value['board']['offset_minutes'] = 540
    html = W.world_html(value)
    assert 'data-offset="540"' in html and 'aria-live="off"' in html
    assert 'aria-label="自分"' in html
    assert 'type="number"' in html and 'ここへ歩く' in html and 'aria-pressed="false"' in html
    assert W.world_validate(W.world_validate(value)) == W.world_validate(value)
    assert 'animation-play-state:paused' in W.world_css(value)


def test_node26_projection_matches_python_oracle():
    node26() or pytest.skip('existing Node 26+ required; no installation')
    segments = [W.world_walk([i, i*2], [100-i, 70-i], at=i/3, speed=10+i) for i in range(20)]
    segments += [W.world_walk([0, 0], [0, 0], at=2)]
    cases = [[s, t] for s in segments for t in (0, s['at'], s['at'] + s['duration']/2, s['at']+s['duration'], 1e9)]
    boards = [[0,-60], [86399.9,540], [1800000001,0]]
    countdowns = [[600,630], [629.999,630], [630,630], [630.001,630], [1439.5,0]]
    result = node_value(world_js(), '{samples:data.cases.map(([s,t])=>motionSample(s,t)),boards:data.boards.map(([n,o])=>boardClock(n,o)),'
                        'countdowns:data.countdowns.map(([n,a])=>minutesUntil(n,a)),walk:motionWalk([10,20],[70,100],5,10,1024,768)}',
                        {'cases': cases, 'boards': boards, 'countdowns': countdowns})
    for actual, (s, t) in zip(result['samples'], cases):
        assert actual == pytest.approx(W.world_motion_sample(s, t), abs=1e-10)
    for actual, (n,o) in zip(result['boards'], boards):
        expected = W.board_clock(n,o)
        assert actual['clock'] == expected['clock']
        assert actual['minutes'] == pytest.approx(expected['minutes'])
    assert result['countdowns'] == [W.minutes_until(n,a) for n,a in countdowns]
    assert result['walk'] == W.world_walk([10,20], [70,100], at=5, speed=10)


def test_node26_interaction_harness():
    # Appended to world.js (whose inner bindMap it drives): a fake DOM, clock and pointer, not a real-browser rendering test.
    motion_harness = r"""// Deterministic DOM/clock harness, NOT a real-browser rendering test.
import assert from 'node:assert/strict';
let now=0, frame, globalEvents={};
globalThis.performance={now:()=>now*1000};
let wall=1800000000000;
const RealDate=Date;globalThis.Date=class extends RealDate{constructor(...args){super(...(args.length?args:[wall+now*1000]))}getTimezoneOffset(){return 0}};
globalThis.setInterval=()=>0;globalThis.clearInterval=()=>{};
globalThis.requestAnimationFrame=f=>{frame=f};
globalThis.addEventListener=(name,f)=>{globalEvents[name]=f};
globalThis.location={hash:'',pathname:'/',search:''};
globalThis.history={replaceState(){}};
const reduced={matches:false,addEventListener(name,f){this.change=f}};
globalThis.matchMedia=()=>reduced;
function node(){return {dataset:{},style:{setProperty(k,v){this[k]=String(v)}},events:{},addEventListener(n,f){this.events[n]=f},setAttribute(n,v){this[n]=v},hasAttribute(n){return Object.hasOwn(this,n)},removeAttribute(n){delete this[n]},toggleAttribute(n,v){this[n]=v}}}
const actor=node(), avatar=node(), button=node(), board=node(), form=node();
form.elements={x:{value:'100'},y:{value:'32'}};form.reportValidity=()=>true;
const controls=node();controls.querySelector=s=>s==='form'?form:s==='output'?board:button;
avatar.dataset={x:'64',y:'32',speed:'10'};
const clock=node(), countdown=node();countdown.dataset.at='10:30';board.dataset.offset='0';
board.querySelector=s=>s==='[data-clock]'?clock:null;board.querySelectorAll=s=>s==='[data-at]'?[countdown]:[];   // the board also has gauges now: answer by selector
const f=node();f.dataset={w:'128',h:'64',floor:'one'};f.querySelector=()=>avatar;f.getBoundingClientRect=()=>({left:0,top:0,width:128,height:64});
const other=node();other.dataset={w:'128',h:'64',floor:'two'};other.querySelector=()=>null;other.getBoundingClientRect=f.getBoundingClientRect;
// Model the label nodes queried by near(), including attribute removal.
const startSpot=node(), nextSpot=node();startSpot.dataset={x:'64',y:'32'};nextSpot.dataset={x:'104',y:'32'};
f.querySelectorAll=s=>s==='.ui-spot[data-x]'?[startSpot,nextSpot]:s==='.ui-spot[data-near]'?[startSpot,nextSpot].filter(a=>a.hasAttribute('data-near')):[];
other.querySelectorAll=()=>[];
const radio={value:'one'}, view=node(),cam=node();view.clientWidth=128;view.clientHeight=64;view.contains=t=>t===view;view.closest=()=>null;view.hasPointerCapture=()=>false;view.setPointerCapture=()=>{};
const el=node();el.isConnected=true;el.dataset.zoomMax=4;
el.querySelector=s=>s==='.ui-world-pause'?button:s==='.ui-world-view'?view:s==='.ui-world-cam'?cam:s==='.ui-world-motion-controls'?controls:s==='.ui-board'?board:s.includes('input[name$="-floor"]')?radio:s.includes('data-floor="two"')?other:s==='.ui-floor'||s.includes('data-floor="one"')?f:null;
el.querySelectorAll=s=>s==='.ui-floor'?[f,other]:[];
bindMap(el);
const tick=t=>{now=t;const cb=frame;frame=null;cb()};
const pos=()=>[parseFloat(avatar.style['--px']),parseFloat(avatar.style['--py'])];
const event=(id,x,y,type='pointerup')=>({button:0,pointerId:id,clientX:x,clientY:y,target:view,type});
const tap=(x,y)=>{view.events.pointerdown(event(1,x,y,'pointerdown'));globalEvents.pointerup(event(1,x,y))};
tick(0);assert.deepEqual(pos(),[64,32]);assert.equal(startSpot.hasAttribute('data-near'),true);assert.equal(nextSpot.hasAttribute('data-near'),false);assert.equal(countdown.textContent.includes('あと'),true);
tap(104,32);tick(2);assert.deepEqual(pos(),[84,32]);
tap(84,52);tick(3);assert.deepEqual(pos(),[84,42]);
button.events.click();tick(8);assert.deepEqual(pos(),[84,42]);assert.equal(button['aria-pressed'],'true');
button.events.click();tick(9);assert.deepEqual(pos(),[84,52]);
// Drags, a motionless pinch, and cancellation must never create a destination.
view.events.pointerdown(event(1,10,10));view.events.pointermove(event(1,50,10));globalEvents.pointerup(event(1,50,10));tick(10);assert.deepEqual(pos(),[84,52]);
view.events.pointerdown(event(1,10,10));view.events.pointerdown(event(2,20,20));globalEvents.pointerup(event(2,20,20));globalEvents.pointerup(event(1,10,10));tick(11);assert.deepEqual(pos(),[84,52]);
view.events.pointerdown(event(1,10,10));globalEvents.pointercancel(event(1,10,10,'pointercancel'));tick(12);assert.deepEqual(pos(),[84,52]);
// Keyboard form uses exactly the same destination path.
form.elements.x.value='104';form.elements.y.value='52';form.events.submit({preventDefault(){}});tick(13);assert.deepEqual(pos(),[94,52]);assert.equal(startSpot.hasAttribute('data-near'),false);assert.equal(nextSpot.hasAttribute('data-near'),true);
reduced.matches=true;reduced.change();tick(20);assert.deepEqual(pos(),[94,52]);
form.elements.x.value='12';form.elements.y.value='10';form.events.submit({preventDefault(){}});assert.deepEqual(pos(),[12,10]);
reduced.matches=false;reduced.change();tick(21);assert.deepEqual(pos(),[12,10]);
// No board/form leakage into a floor without motion; return keeps avatar state.
radio.value='two';el.events.change({target:{name:'demo-floor'}});tick(22);assert.equal(form.hidden,true);tap(1,1);
radio.value='one';el.events.change({target:{name:'demo-floor'}});tick(23);assert.equal(form.hidden,false);assert.deepEqual(pos(),[12,10]);
// Wall clock can jump without changing monotonic motion.
wall=0;tick(23);assert.deepEqual(pos(),[12,10]);
el.isConnected=false;tick(24);assert.equal(frame,null);
console.log('motion interaction harness passed');"""
    node26() or pytest.skip('existing Node 26+ required; no installation')
    assert 'motion interaction harness passed' in node_js(world_js() + motion_harness).stdout


# ═══ 🗺️ places ═══════════════════════════════════════════════════════════════════════════════════════════
# Real places in miniature: the ``place`` floor turns latitude/longitude points into a tile grid (``W.place_floor``), and the ``cities`` example
# (Parallel Tokyo, Reverse London and Fake Paris) is built from it. The coordinates are approximate, so the checks are about relative positions and walking, not metres.

def pt(id, lat, lon, **over):
    return {"id": id, "label": id.upper(), "lat": lat, "lon": lon, **over}


# Two points 1 km apart on a meridian (about 0.00899 degrees of latitude), at 100 m per tile.
NORTH, SOUTH = pt("a", 35.0090, 139.0), pt("b", 35.0000, 139.0)


def cell(floor, spot_id):
    spot = next(s for s in floor["spots"] if s["id"] == f"{floor['id']}-{spot_id}")
    return spot["x"] // floor["tile"], spot["y"] // floor["tile"]


def walkable(floor):
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    start = (floor["player"]["x"] // floor["tile"], floor["player"]["y"] // floor["tile"])
    return W.world_reach(blocked, start)


def test_points_land_on_tiles_from_their_distance():
    floor = W.place_floor([NORTH, SOUTH], meters=100)
    (ax, ay), (bx, by) = cell(floor, "a"), cell(floor, "b")
    assert ax == bx
    assert by - ay == 10                                         # 1 km at 100 m per tile; north is up
    assert floor["width"] % floor["tile"] == 0 and floor["height"] % floor["tile"] == 0
    assert floor["spots"][0]["x"] == int((ax + .5) * floor["tile"])   # a spot stands in the middle of its tile


def test_east_is_right_and_longitude_shrinks_with_latitude():
    equator = W.place_floor([pt("w", 0.0, 10.0), pt("e", 0.0, 10.0090)], meters=100)
    north = W.place_floor([pt("w", 60.0, 10.0), pt("e", 60.0, 10.0090)], meters=100)
    assert cell(equator, "e")[0] - cell(equator, "w")[0] == 10   # 0.009 degrees of longitude is about 1 km at the equator ...
    assert cell(north, "e")[0] - cell(north, "w")[0] == 5        # ... and half of that at 60 degrees north


def test_same_arguments_give_the_same_floor_and_it_validates():
    one = W.place_floor([NORTH, SOUTH], meters=100, links=[["a", "b"]], id="p", label="P")
    assert one == W.place_floor([NORTH, SOUTH], meters=100, links=[["a", "b"]], id="p", label="P")
    W.world_validate({"schema": W.WORLD_SCHEMA, "id": "w", "floors": [one]})


def test_two_points_on_one_tile_take_two_tiles_and_the_earlier_one_keeps_its_own():
    a, b = pt("a", 35.0, 139.0), pt("b", 35.00001, 139.00001)                                  # a few metres apart: the same tile at 500 m
    far = pt("far", 35.1, 139.0)
    one, other = W.place_floor([a, b, far], meters=500), W.place_floor([b, a, far], meters=500)
    assert cell(one, "a") == cell(other, "b")                                                 # whoever comes first keeps the tile
    assert cell(one, "b") != cell(one, "a") and cell(other, "a") != cell(other, "b")
    assert max(abs(cell(one, "a")[i] - cell(one, "b")[i]) for i in (0, 1)) == 1                # and the other is one tile away
    assert len({cell(one, k) for k in ("a", "b", "far")}) == 3


def test_a_maps_url_is_a_point_like_any_other():
    a = W.place_floor([pt("a", 35.0090, 139.0), pt("b", 35.0, 139.0)], meters=100)
    b = W.place_floor([{"id": "a", "label": "A", "maps": "https://www.google.com/maps/@35.0090,139.0,17z"}, pt("b", 35.0, 139.0)], meters=100)
    assert a["spots"] == b["spots"]
    with pytest.raises(ValueError, match="no coordinates"):
        W.place_floor([{"id": "a", "label": "A", "maps": "https://example.test/"}], meters=100)


def test_an_area_is_the_box_tolerance_area_gives():
    centre = (35.0, 139.0)
    floor = W.place_floor([pt("c", *centre)], meters=100, area={"center": list(centre), "radius": 1000})
    box = ui.tolerance_area(*centre, 1000)
    height_m = (box["north"] - box["south"]) * math.pi / 180 * ui.EARTH_RADIUS_M
    assert floor["height"] // floor["tile"] == int(height_m // 100) + 1          # the map is the box, with no margin
    assert abs(cell(floor, "c")[1] - floor["height"] // floor["tile"] // 2) <= 1  # the centre is in the middle
    with pytest.raises(ValueError, match="outside the area"):
        W.place_floor([pt("far", 36.0, 139.0)], meters=100, area={"center": list(centre), "radius": 1000})
    with pytest.raises(ValueError, match="date line"):
        W.place_floor([pt("x", 0.0, 179.9999)], meters=100, area={"center": [0.0, 179.9999], "radius": 50000})


RIVER = {"line": [[35.0045, 138.99], [35.0045, 139.01]], "width": 2}         # between a (north) and b (south), all the way across


def test_a_river_cuts_the_place_until_a_link_makes_a_bridge():
    with pytest.raises(ValueError, match="cut off by water from a: b"):
        W.place_floor([NORTH, SOUTH], meters=100, rivers=[RIVER])
    floor = W.place_floor([NORTH, SOUTH], meters=100, rivers=[RIVER], links=[["a", "b"]])
    kinds = {p["kind"] for p in floor["props"]}
    assert {"water", "bridge", "road"} <= kinds
    assert cell(floor, "b") in walkable(floor)
    bridge = next(p for p in floor["props"] if p["kind"] == "bridge")
    tile = floor["tile"]
    assert all(floor["props"].index(bridge) > floor["props"].index(w) for w in floor["props"] if w["kind"] == "water")   # laid after the water
    assert bridge["w"] % tile == 0 and bridge["h"] % tile == 0


def test_no_spot_stands_in_the_water():
    floor = W.place_floor([pt("a", 35.0045, 139.0), pt("b", 35.0090, 139.0)], meters=100, rivers=[RIVER], links=[["a", "b"]])   # a is on the river
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    for spot in floor["spots"]:
        x, y = spot["x"] // floor["tile"], spot["y"] // floor["tile"]
        assert blocked[y][x] == "0"


def test_roads_are_few_props_not_one_per_tile():
    pts = [pt("a", 35.0090, 139.0), pt("b", 35.0, 139.0), pt("c", 35.0, 139.0090)]
    floor = W.place_floor(pts, meters=50, links=[["a", "b"], ["b", "c"]])
    assert len(floor["props"]) <= 4                              # grass, and the two roads (the corner is shared)


def test_mistakes_say_what_is_wrong():
    ok = [NORTH, SOUTH]
    for bad, message in [
        (dict(points=[]), "1..64 points"),
        (dict(points=[NORTH, NORTH]), "unique"),
        (dict(points=[pt("A", 1, 1)]), "unique lowercase token"),
        (dict(points=[pt("a", 91, 0)]), "between -90 and 90"),
        (dict(points=[{"id": "a", "label": "A", "lat": 1}]), "either lat and lon or maps"),
        (dict(points=[pt("a", 1, 1, color="red")]), "a point has"),
        (dict(points=[pt("a", 1, 1, flip="")]), "flip must"),
        (dict(points=[pt("a", 1, 1, sign="neon")]), "sign is one of led, wood"),
        (dict(points=[pt("a", 1, 1, sign="led")]), "needs a point that is not a sign"),
        (dict(points=[NORTH, pt("s", 35.0045, 139.0, sign="led")], start="s"), "start is the id"),
        (dict(points=[NORTH, pt("s", 35.0045, 139.0, sign="led")], links=[["a", "s"]]), "two different point ids"),
        (dict(points=ok, scatter={"kind": "tree", "every": 4, "seed": 1}), "scatter is"),
        (dict(points=ok, scatter={"kind": "road", "every": 4, "seed": 1}), "scatter is"),
        (dict(points=ok, scatter={"kind": "fire", "every": 1, "seed": 1}), "every must be an integer from 2 to 64"),
        (dict(points=ok, scatter={"kind": "fire", "every": 4}), "scatter is"),
        (dict(points=[pt("a", 1, 1, category="Big")]), "lowercase token"),
        (dict(points=ok, links=[["a", "zzz"]]), "two different point ids"),
        (dict(points=ok, links=[["a", "a"]]), "two different point ids"),
        (dict(points=ok, start="zzz"), "start is the id"),
        (dict(points=ok, rivers=[{"line": [[1, 1]], "width": 1}]), "a river is"),
        (dict(points=ok, rivers=[{"line": [[35, 139], [35.1, 139]], "width": 9}]), "width must be an integer from 1 to 8"),
        (dict(points=ok, meters=7), "meters must be an integer from 8 to 2000"),
        (dict(points=ok, meters=8), "4096 units"),
        (dict(points=ok, tile=20), "multiple of 8"),
    ]:
        with pytest.raises(ValueError, match=message):
            W.place_floor(**bad)


def test_scatter_puts_one_decoration_in_each_block_on_a_free_tile_and_is_repeatable():
    pts = [pt("a", 35.0090, 139.0), pt("b", 35.0, 139.0)]
    scatter = {"kind": "fire", "every": 4, "seed": 7}
    floor = W.place_floor(pts, meters=100, rivers=[RIVER], links=[["a", "b"]], scatter=scatter)
    assert floor == W.place_floor(pts, meters=100, rivers=[RIVER], links=[["a", "b"]], scatter=scatter)
    assert floor != W.place_floor(pts, meters=100, rivers=[RIVER], links=[["a", "b"]], scatter={**scatter, "seed": 8})
    tile = floor["tile"]
    fires = [(p["x"] // tile, p["y"] // tile) for p in floor["props"] if p["kind"] == "fire"]
    assert all(p["w"] == p["h"] == tile for p in floor["props"] if p["kind"] == "fire")
    cols, rows = floor["width"] // tile, floor["height"] // tile
    blocks = {(x // 4, y // 4) for x, y in fires}
    assert len(blocks) == len(fires)                                              # at most one in a block ...
    assert len(fires) >= (cols // 4) * (rows // 4) - 2                           # ... and nearly every block has one (a block may be all water)
    others = {(p["x"] // tile + i, p["y"] // tile + j) for p in floor["props"] if p["kind"] in ("water", "road", "bridge")
              for i in range(p["w"] // tile) for j in range(p["h"] // tile)}
    spots = {(s["x"] // tile, s["y"] // tile) for s in floor["spots"]}
    assert not set(fires) & (others | spots)                                      # never on a road, the river or a spot
    assert cell(floor, "b") in walkable(floor)                                    # and a fire is only a decoration


def test_a_flip_is_kept_through_validation_and_written_as_a_second_face():
    floor = W.place_floor([pt("a", 35.0, 139.0, flip="🐉"), pt("b", 35.1, 139.0)], meters=500, id="p")
    assert [s.get("flip") for s in floor["spots"]] == ["🐉", None]
    world = W.world_validate({"schema": W.WORLD_SCHEMA, "id": "w", "floors": [floor]})
    assert world["floors"][0]["spots"][0]["flip"] == "🐉" and "flip" not in world["floors"][0]["spots"][1]
    html = W.world_html({"schema": W.WORLD_SCHEMA, "id": "w", "floors": [floor]})
    assert 'data-flip="🐉"' in html and html.count("data-flip=") == 1


def test_a_sign_is_a_small_board_on_the_nearest_tile_corner_and_takes_no_tile():
    floor = W.place_floor([NORTH, SOUTH, pt("board", 35.0045, 139.0, category="sign", sign="led", label="◀ A | B ▶")], meters=100, id="p")
    tile = floor["tile"]
    board = next(s for s in floor["spots"] if s["id"] == "p-board")
    assert board["sign"] == "led" and board["x"] % tile == 0 and board["y"] % tile == 0
    (ax, ay), (bx, by) = cell(floor, "a"), cell(floor, "b")
    assert ay < board["y"] // tile <= by and abs(board["y"] // tile - (ay + by + 1) / 2) <= 1          # half way between the two stations
    assert [s["id"] for s in floor["spots"]] == ["p-a", "p-b", "p-board"]                                  # tile points first, then the corners
    taken = {(s["x"] // tile, s["y"] // tile) for s in floor["spots"] if "sign" not in s}
    assert len(taken) == 2                                                                                  # a sign does not use up a tile
    one = W.place_floor([NORTH, pt("s1", 35.0045, 139.0, sign="led"), pt("s2", 35.0045, 139.0, sign="wood")], meters=100)
    corners = {(s["x"], s["y"]) for s in one["spots"] if "sign" in s}
    assert len(corners) == 2                                                                                # two signs never share a corner


def test_a_sign_in_the_middle_of_a_river_moves_to_the_bank_and_is_walkable():
    wide = {"line": [[35.0045, 138.99], [35.0045, 139.01]], "width": 4}
    floor = W.place_floor([NORTH, SOUTH, pt("s", 35.0045, 139.0, sign="wood")], meters=100, rivers=[wide], links=[["a", "b"]])
    tile = floor["tile"]
    sign = next(s for s in floor["spots"] if "sign" in s)
    blocked = W.world_blocked(floor["width"], floor["height"], tile, floor["props"])
    around = [(sign["x"] // tile + dx, sign["y"] // tile + dy) for dx in (-1, 0) for dy in (-1, 0)]
    assert any(blocked[y][x] == "0" for x, y in around)                                                     # it touches dry land


def test_any_spot_may_be_a_sign_and_the_page_draws_it_as_a_board_on_a_dot():
    def world(sign):
        return {"schema": W.WORLD_SCHEMA, "id": "w", "floors": [{"id": "f", "label": "F", "width": 128, "height": 128,
                "spots": [{"id": "s", "x": 64, "y": 64, "label": "◀ 出口", "sign": sign}]}]}
    html = W.world_html(world("led"))
    assert 'data-sign="led"' in html and "ui-spot[data-sign=led]" in W.world_css(world("led")) + ui.bundled_css()
    assert 'data-sign="wood"' in W.world_html(world("wood"))
    with pytest.raises(ValueError, match="sign is one of led, wood"):
        W.world_validate(world("neon"))


def test_json_alone_asks_for_a_place_and_unknown_keys_are_refused():
    spec = {"schema": W.WORLD_SCHEMA, "id": "w", "floors": [{"id": "here", "label": "Here", "place": {"points": [NORTH, SOUTH], "meters": 100}}]}
    world = W.world_validate(spec)
    assert world["floors"][0]["spots"][0]["id"] == "here-a"
    bad = copy.deepcopy(spec)
    bad["floors"][0]["place"]["zoom"] = 3
    with pytest.raises(ValueError, match="a place floor has"):
        W.world_validate(bad)


# --- the two cities ---------------------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cities():
    world = W.world_validate(W.example_data("cities"))
    return {f["id"]: f for f in world["floors"]}


def by_id(floor):
    return {s["id"].split("-", 1)[1]: s for s in floor["spots"]}


def test_the_cities_are_three_floors_with_every_spot_walkable(cities):
    assert list(cities) == ["tokyo", "london", "paris"]
    for floor in cities.values():
        reach = walkable(floor)
        assert len(floor["props"]) <= 512 and len(floor["spots"]) <= 64
        tile = floor["tile"]
        for spot in floor["spots"]:
            if "sign" in spot:                                                                   # a sign sits on a corner: it touches four tiles
                assert spot["x"] % tile == 0 and spot["y"] % tile == 0, spot["id"]
                around = [(spot["x"] // tile + dx, spot["y"] // tile + dy) for dx in (-1, 0) for dy in (-1, 0)]
                assert any(c in reach for c in around), spot["id"]
            else:
                assert (spot["x"] // tile, spot["y"] // tile) in reach, spot["id"]
        assert len({(s["x"], s["y"]) for s in floor["spots"]}) == len(floor["spots"])          # no two spots on one tile or corner


def test_tokyo_station_has_six_exits_laid_out_like_the_building(cities):
    spots = by_id(cities["tokyo"])
    exits = {k: v for k, v in spots.items() if v["category"] == "exit"}
    assert sorted(exits) == ["marunouchi-c", "marunouchi-n", "marunouchi-s", "yaesu-c", "yaesu-n", "yaesu-s"]
    for side in ("marunouchi", "yaesu"):
        assert exits[f"{side}-n"]["y"] < exits[f"{side}-c"]["y"] < exits[f"{side}-s"]["y"]     # north above south
    for part in "ncs":
        assert exits[f"marunouchi-{part}"]["x"] < exits[f"yaesu-{part}"]["x"]                   # Marunouchi is the west side
    assert cities["tokyo"]["player"]["x"] // 32 == exits["marunouchi-c"]["x"] // 32


def test_tokyo_has_no_facility_names_and_the_stations_are_where_they_are(cities):
    spots = by_id(cities["tokyo"])
    assert {v["category"] for v in spots.values()} == {"exit", "station", "sign"}
    stations = {k: v for k, v in spots.items() if v["category"] == "station"}
    assert len(stations) == 13
    centre = spots["marunouchi-c"]
    tile = cities["tokyo"]["tile"]
    for key, spot in stations.items():                           # every one is within two kilometres of the station (the floor is 32 m a tile)
        metres = math.hypot(spot["x"] - centre["x"], spot["y"] - centre["y"]) / tile * 32
        assert metres < 2000, key
    assert stations["shimbashi"]["y"] > stations["yurakucho"]["y"] > stations["otemachi"]["y"]   # Shimbashi is south of Yurakucho, south of Otemachi
    assert stations["kanda"]["y"] < stations["otemachi"]["y"]                                      # Kanda is north of Otemachi
    assert stations["nihombashi"]["x"] > centre["x"] > stations["nijubashimae"]["x"]               # east of the station, and west of it


def test_london_is_its_main_termini_and_the_stations_beside_them(cities):
    floor = cities["london"]
    spots = by_id(floor)
    kinds = {}
    for key, spot in spots.items():
        kinds.setdefault(spot["category"], []).append(key)
    assert sorted(kinds) == ["sign", "station", "terminus"]                                          # transport only: no sights, no institutions
    assert len(kinds["terminus"]) == 13
    for key in ("kings-cross", "paddington", "waterloo", "victoria", "liverpool-street", "london-bridge", "euston", "charing-cross"):
        assert key in kinds["terminus"]
    assert spots["paddington"]["x"] < spots["kings-cross"]["x"] < spots["liverpool-street"]["x"]   # west to east
    assert spots["waterloo"]["y"] > spots["charing-cross"]["y"]                                    # south of the river
    assert spots["london-bridge"]["y"] > spots["cannon-street"]["y"]


def test_the_thames_is_between_waterloo_and_charing_cross_with_a_bridge(cities):
    floor = cities["london"]
    kinds = {p["kind"] for p in floor["props"]}
    assert {"water", "bridge"} <= kinds
    blocked = W.world_blocked(floor["width"], floor["height"], floor["tile"], floor["props"])
    spots = by_id(floor)
    tile = floor["tile"]
    (x0, x1), (y0, y1) = (sorted(spots[k]["x"] // tile for k in ("waterloo", "charing-cross")), sorted(spots[k]["y"] // tile for k in ("waterloo", "charing-cross")))
    assert any(blocked[y][x] == "1" for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)), "water lies between them"
    assert cell(floor, "charing-cross") in walkable(floor) and cell(floor, "waterloo") in walkable(floor)    # and a bridge joins them


def test_fake_paris_has_its_stations_a_seine_with_bridges_and_a_fire_in_each_block(cities):
    floor = cities["paris"]
    spots = by_id(floor)
    kinds = {}
    for key, spot in spots.items():
        kinds.setdefault(spot["category"], []).append(key)
    assert sorted(kinds) == ["sign", "station", "terminus"] and len(kinds["terminus"]) == 6                    # transport only
    assert spots["gare-du-nord"]["y"] < spots["gare-de-lyon"]["y"] < spots["montparnasse"]["y"] + 1              # north to south
    assert spots["saint-lazare"]["x"] < spots["gare-du-nord"]["x"] < spots["gare-de-lyon"]["x"]                  # west to east
    assert spots["montparnasse"]["x"] < spots["jussieu"]["x"] < spots["bastille"]["x"]                          # west to east, south of the river
    assert {"water", "bridge", "fire"} <= {p["kind"] for p in floor["props"]}
    fires = [p for p in floor["props"] if p["kind"] == "fire"]
    assert 20 <= len(fires) <= 40
    tile = floor["tile"]
    assert len({(p["x"] // tile // 8, p["y"] // tile // 8) for p in fires}) == len(fires)                         # one per block of eight tiles


def test_no_city_lists_a_religious_building(cities):
    words = ("大聖堂", "寺院", "教会", "聖堂", "神社", "寺", "モスク", "霊廟")
    assert not [s["id"] for floor in cities.values() for s in floor["spots"] if any(w in s["label"] + s["body"] for w in words)]


def test_the_nogard_sign_stands_by_a_station_and_turns_into_a_dragon(cities):
    floor = cities["london"]
    sign = by_id(floor)["nogard"]
    assert (sign["label"], sign["flip"], sign["category"], sign["sign"]) == ("nogard", "🐉", "sign", "wood")
    assert sign["label"][::-1] == "dragon"                                                                        # dragon, backwards
    stations = [s for s in floor["spots"] if s["category"] in ("terminus", "station")]            # the stations, not the other signs
    tile = floor["tile"]
    nearest = min(math.hypot(s["x"] - sign["x"], s["y"] - sign["y"]) for s in stations) / tile
    assert nearest <= 3                                                                                           # within three tiles (450 m)
    assert len([s for s in floor["spots"] if "flip" in s]) == 1
    assert sign["x"] % tile == 0 and sign["y"] % tile == 0                                                        # on a corner of the grid


def test_the_demo_page_and_the_cli_carry_the_cities():
    import project_pages
    page = project_pages.world_page("cities")                     # 🗼 tools/demos/cities.html
    for text in ("丸の内中央口", "リバースロンドン", "Fake Paris", "Parallel Tokyo", 'data-category="exit"', 'data-category="terminus"',
                 'data-flip="🐉"'):
        assert text in page
    spec = subprocess.run([sys.executable, str(ROOT / "scripts/world.py"), "example", "cities"], capture_output=True, text=True, check=True, encoding="utf-8").stdout
    assert json.loads(spec)["floors"][0]["place"]["points"][0]["id"] == "marunouchi-c"
    html = subprocess.run([sys.executable, str(ROOT / "scripts/world.py"), "page", "-"], input=spec, capture_output=True, text=True, check=True, encoding="utf-8").stdout
    assert "八重洲北口" in html and "ウォータールー" in html and "サン・ラザール駅" in html          # a spot of each city from the CLI
    assert "タワー・ブリッジ" not in html and "エッフェル塔" not in html                               # transport only


# ═══ 🤝 shared board ══════════════════════════════════════════════════════════════════════════════════════
# Opt-in shared board contract; no network calls or public writes.

def spec():
    value = W.example_data('world')
    value['board']['shared_issue'] = 'myon-bioinformatics/PySaiyanWeBoo/123'
    return value


def test_opt_in_and_local_form():
    value = spec()
    html = W.world_html(value)
    assert 'ui-board-post' in html and 'ui-board-shared' in html
    assert 'issues/123#new_comment_field' in html
    assert 'credentials' not in html  # secrets are never embedded in HTML
    assert 'target="_blank" rel="noopener noreferrer"' in html
    assert W.world_validate(W.world_validate(value)) == W.world_validate(value)
    del value['board']['shared_issue']
    assert 'data-shared-refresh' not in W.world_html(value)


@pytest.mark.parametrize('bad', ['', 'https://github.com/a/b/1', 'a/b/0', 'a/b/-1', 'a/b/1?token=x', 'a/b/1/extra', True, {}, 'a/../../1', 'a/../1', 'a/./1'])
def test_invalid_target(bad):
    value = spec()
    value['board']['shared_issue'] = bad
    with pytest.raises(ValueError):
        W.world_validate(value)


def test_shared_node():
    # Appended to world.js: sharedLines, sharedWait and bindSharedBoard with a fake fetch, clock and panel.
    shared_harness = r"""const assert = (await import('node:assert/strict')).default;
assert.equal(sharedLines([{body:'<img src=x onerror=alert(1)>',user:{login:'alice'},created_at:'today'}])[0].text,'<img src=x onerror=alert(1)>');
assert.throws(()=>sharedLines({}));
assert.deepEqual(sharedLines([{body:'  \n\t',user:{login:'a'}},{body:'\u0000',user:{login:'b'}}]),[]);
assert.equal(sharedLines([{body:'valid',user:{login:'a'}},{body:' ',user:{login:'b'}}])[0].text,'valid');
assert.equal(sharedLines(Array.from({length:110},(_,i)=>({body:String(i),user:{login:'a'}})))[0].text,'99');
assert.equal(sharedLines([{body:'x',user:null}]).length,0);
assert.equal(sharedWait({headers:new Headers({'retry-after':'300'})},1000),301000);
assert.equal(sharedWait({headers:new Headers({'x-ratelimit-remaining':'0','x-ratelimit-reset':'999'})},1000),999000);
let now=1000,calls=0,listener,fail=false;
Date.now=()=>now;
const status={},list={replaceChildren(...nodes){this.nodes=nodes}},button={addEventListener(type,cb){listener=cb}},panel={isConnected:true,dataset:{api:'https://api.github.com/repos/a/b/issues/1/comments?per_page=100'},querySelector(s){return s.includes('refresh')?button:s.includes('status')?status:list}};
globalThis.document={createElement(){return {}}};
globalThis.fetch=async(url,options)=>{calls++;assert.equal(options.credentials,'omit');assert.equal(options.method,'GET');if(fail)throw Error('offline');return {ok:true,headers:new Headers(),json:async()=>[{body:'hello',user:{login:'alice'},created_at:'today'}]}};
bindSharedBoard({querySelector(){return panel}});
assert.equal(calls,0);
await listener();assert.equal(calls,1);assert.match(list.nodes[0].textContent,/alice.*hello/);
await listener();assert.equal(calls,1);assert.match(status.textContent,/待機/);
now+=120001;fail=true;await listener();assert.equal(calls,2);assert.match(status.textContent,/前回/);assert.match(list.nodes[0].textContent,/hello/);
console.log('shared board harness passed');"""
    node26() or pytest.skip('Node 26+ required')
    assert 'shared board harness passed' in node_js(world_js() + shared_harness).stdout


def test_approved_example_destination():
    value = W.example_data('world')
    assert value['board']['shared_issue'] == 'myon-bioinformatics/PySaiyanWeBoo/110'
    html = W.world_document(value)
    assert 'https://github.com/myon-bioinformatics/PySaiyanWeBoo/issues/110#new_comment_field' in html
    assert 'issues/123#new_comment_field' not in html


def test_spot_item_validates_and_renders_bag_menu():
    spec = _world(shell=True)
    assert 'ui-world-bag' not in W.world_html(spec) and 'ui-world-take' not in W.world_html(spec)
    spec["floors"][0]["spots"][0]["item"] = {"emoji": "🍠", "label": "サツマイモ", "body": "ヒルガオ科のいも。"}
    checked = W.world_validate(spec)
    assert checked["floors"][0]["spots"][0]["item"] == {"emoji": "🍠", "label": "サツマイモ", "body": "ヒルガオ科のいも。"}
    html = W.world_html(checked)
    assert 'data-menu="bag"' in html and 'class="ui-world-rows ui-world-bag"' in html
    assert 'class="ui-world-take"' in html and 'data-item-emoji="🍠"' in html and 'data-item-label="サツマイモ"' in html
    for bad in ({"emoji": "🍠"}, {"label": "x"}, {"emoji": "x", "label": "y"}, {"emoji": "🍠", "label": "y", "extra": 1}, "🍠"):
        bad_spec = _world()
        bad_spec["floors"][0]["spots"][0]["item"] = bad
        with pytest.raises(ValueError):
            W.world_validate(bad_spec)


def test_overworld_meadow_has_hirugaoka_and_sweet_potato_item():
    world = W.world_validate(W.example_data("overworld"))
    meadow = next(f for f in world["floors"] if f["id"] == "meadow")
    hirugaoka = next(s for s in meadow["spots"] if s["id"] == "meadow-hirugaoka")
    assert "昼ヶ丘" in hirugaoka["label"] and hirugaoka["item"]["emoji"] == "🍠" and "サツマイモ" in hirugaoka["item"]["label"]
    reach, blocked = _reach(meadow)
    cell = (hirugaoka["x"] // meadow["tile"], hirugaoka["y"] // meadow["tile"])
    assert cell in reach and blocked[cell[1]][cell[0]] == "0"


def test_move_confirm_and_blended_spot_labels():
    spec = _world()
    assert W.world_validate(spec)["move"] == "direct"
    assert 'data-move=' not in W.world_html(spec) and 'class="ui-world-go"' not in W.world_html(spec)
    spec["move"] = "confirm"
    assert W.world_validate(spec)["move"] == "confirm"
    html = W.world_html(spec)
    assert 'data-move="confirm"' in html and 'class="ui-world-go"' in html
    bad = _world()
    bad["move"] = "teleport"
    with pytest.raises(ValueError):
        W.world_validate(bad)
    css = W.world_css(_world())
    assert "background:transparent" in css and "text-shadow:" in css and "[data-selected]" in css




def test_standalone_bulletin_markup():
    html = W.bulletin_html("https://example.test/community#post", title="<bulletin>", notice="<public>", post_label="External post")
    assert "https://example.test/community#post" in html and "data-api" not in html
    assert "&lt;bulletin&gt;" in html and "&lt;public&gt;" in html
    for invalid in ("javascript:alert(1)", "//example.test", "https://user:pass@example.test", "https://bad\\host", "https://bad\nhost"):
        with pytest.raises(ValueError):
            W.bulletin_html(invalid, title="", notice="", post_label="")
    project = "myon-bioinformatics/PySaiyanWeBoo/110"
    api, post = W.issue_bulletin_urls(project)
    assert api == "https://api.github.com/repos/myon-bioinformatics/PySaiyanWeBoo/issues/110/comments?per_page=100"
    assert post == "https://github.com/myon-bioinformatics/PySaiyanWeBoo/issues/110#new_comment_field"
    issue_html = W.issue_bulletin_html(project)
    assert api in issue_html and post in issue_html and "ページ内Post" not in issue_html


def test_standalone_bulletin_reader_and_issue_transport():
    node26() or pytest.skip("Node 26+ required")
    harness = r"""
      const assert=(await import('node:assert/strict')).default;
      let now=1000;Date.now=()=>now;
      globalThis.document={createElement(){return {}}};
      function makePanel(api){
       const refs={refresh:{addEventListener(type,cb){this.click=cb}},status:{},comments:{replaceChildren(...nodes){this.nodes=nodes}}};
       return {isConnected:true,dataset:{api},refs,querySelector(s){return refs[s.slice(13,-1)]}};
      }
      const generic=makePanel(),trustedRead=async(signal,observe)=>{
       assert.equal(signal.aborted,false);
       observe(new Headers());
       return {lines:[{author:'fixture',time:'today',text:'<b>plain text</b>'}],more:true};
      };
      bindBulletin(generic,trustedRead,{moreText:'external continuation'});
      assert.equal(generic.refs.comments.nodes,undefined);
      await generic.refs.refresh.click();
      assert.equal(generic.refs.comments.nodes[0].textContent,'fixture · today — <b>plain text</b>');
      assert.match(generic.refs.status.textContent,/external continuation/);
      for(const api of ['https://example.test/comments','https://api.github.com/repos/a/../issues/2/comments?per_page=100',
                        'https://api.github.com/repos/a/b/issues/2/comments?per_page=100&token=test','https://api.github.com/repos/a/b/issues/2/comments?per_page=100\n']){
       const rogue=makePanel(api);bindIssueBulletin(rogue);assert.equal(rogue.refs.refresh.click,undefined);
      }
      const api='https://api.github.com/repos/myon-bioinformatics/PySaiyanWeBoo/issues/110/comments?per_page=100';
      const issue=makePanel(api);let count=0,ok=true;
      globalThis.fetch=async(url,options)=>{
       count++;assert.equal(url,api);assert.equal(options.method,'GET');assert.equal(options.credentials,'omit');
       assert.equal(options.redirect,'error');assert.equal(options.referrerPolicy,'no-referrer');
       return {ok,status:ok?200:404,headers:new Headers(),
        json:async()=>[{body:'a comment on a closed issue',user:{login:'fixture'},created_at:'2030-01-01T00:00:00Z'}]};
      };
      bindIssueBulletin(issue);assert.equal(count,0);
      await issue.refs.refresh.click();assert.equal(count,1);
      assert.match(issue.refs.comments.nodes[0].textContent,/a comment on a closed issue/);
      now+=120001;ok=false;
      await issue.refs.refresh.click();assert.equal(count,2);
      assert.match(issue.refs.status.textContent,/前回/);
      assert.match(issue.refs.comments.nodes[0].textContent,/a comment on a closed issue/);
      console.log('standalone bulletin passed');
    """
    assert 'standalone bulletin passed' in node_js(W.ISSUE_BULLETIN_JS + harness).stdout
