"""🌍 World · 🗼 Parallel cities · 🏫 School: one page, a camera, no page changes (moved from PySaiyanWeBoo).

``world_validate(spec)`` / ``world_html(spec)`` / ``world_css(spec)`` / ``WORLD_JS`` / ``world_document(spec)`` draw a
``web-ui-world/1`` spec: scrolling shots, a pan/zoom map, a tile grid to walk (``classroom_floor``, ``land_floor``,
``place_floor`` from latitude/longitude). ``EXAMPLES`` / ``example_data(name)`` hold the world, the school, the overworld
and the three cities. The CSS, the themes, the dial and the coordinates come from PySaiyanWeBoo (the pinned web UI).

"""
from __future__ import annotations

import argparse
import bisect
import contextlib
import functools
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import zlib
from html import escape
from pathlib import Path
from typing import Any, Callable, NamedTuple
from urllib.parse import quote, urlsplit

from pysaiyanweboo import (CHROME_LANGS, COUNTER_ATTACK_ORBS, COUNTER_HEAL_ORBS, COUNTER_MAX_ORBS, DIAL_CSS, DIAL_JS, EARTH_RADIUS_M, bundled_css,
                           chrome_word, counter_effect, counter_label, dial_html, js_source, module_script, parse_coordinate, play_random,
                           render_document, shell_js, tolerance_area, try_parse_maps_url)

# --- World: one page, a camera, no page changes (scrolling "shots" and a pan/zoom map) -----------------
# Everything is built here in memory: Python validates the data, does the arithmetic, and emits the HTML,
# the CSS and a thin JavaScript module. JS only applies state (data-lit, camera variables); CSS does the rest.

WORLD_SCHEMA = "web-ui-world/1"
_WORLD_ID = re.compile(r"[a-z][a-z0-9-]{0,31}")  # the world itself: it prefixes element ids, so it starts with a letter
_WORLD_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")  # floors, shots, spots, categories (1f is fine)
_WORLD_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def _luminance(color: str) -> float:
    channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    """WCAG contrast ratio of two #rrggbb colors."""
    light, dark = sorted((_luminance(foreground), _luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def ink_for(background: str) -> str:
    """Black or white text, whichever reads better on ``background``."""
    return "#0b0b0c" if contrast_ratio("#0b0b0c", background) >= contrast_ratio("#ffffff", background) else "#ffffff"


def fit_zoom(width: float, height: float, view_w: float, view_h: float) -> float:
    """Zoom at which a width x height map just fits a view_w x view_h view."""
    return min(view_w / width, view_h / height)


def clamp_focus(fx: float, fy: float, zoom: float, width: float, height: float,
                view_w: float, view_h: float) -> tuple[float, float]:
    """Keep the camera's focal point (map units) so the view never leaves the map; a map smaller than the view is centered."""
    half_w, half_h = view_w / (2 * zoom), view_h / (2 * zoom)
    return (min(max(fx, half_w), width - half_w) if width > 2 * half_w else width / 2,
            min(max(fy, half_h), height - half_h) if height > 2 * half_h else height / 2)


# Motion uses elapsed monotonic seconds; boards use Unix UTC seconds. All inputs
# are bounded so static documents cannot request unbounded plans or DOM nodes.
def _motion_number(value: Any, label: str, low: float, high: float) -> float:
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{label} must be finite and from {low} to {high}")
    return float(value)


def world_walk(start: list[float], target: list[float], *, at: float = 0,
               speed: float = 40, width: float = 1024, height: float = 768) -> dict[str, Any]:
    """One constant-velocity segment. Targets clamp at map edges; no overshoot.

    For retarget/pause/resume first sample the old segment at the event's time,
    then start a new segment from that point. Never integrate per frame.
    """
    width = _motion_number(width, "width", 64, 4096)
    height = _motion_number(height, "height", 64, 4096)
    at = _motion_number(at, "at", 0, 1e9)
    speed = _motion_number(speed, "speed", 1, 480)
    points = []
    for point in (start, target):
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("point must have two coordinates")
        points.append([min(bound, max(0., _motion_number(v, "coordinate", -1e6, 1e6)))
                       for v, bound in zip(point, (width, height))])
    a, b = points
    return {"at": at, "duration": math.hypot(b[0] - a[0], b[1] - a[1]) / speed, "from": a, "to": b}


def world_motion_sample(segment: dict[str, Any], elapsed: float) -> list[float]:
    """Project a validated/generated segment at absolute elapsed seconds; endpoints hold."""
    elapsed = _motion_number(elapsed, "elapsed", 0, 1e9)
    at = _motion_number(segment["at"], "at", 0, 1e9)
    duration = _motion_number(segment["duration"], "duration", 0, 1e6)
    points = [segment[key] for key in ("from", "to")]
    if any(not isinstance(p, (list, tuple)) or len(p) != 2 for p in points):
        raise ValueError("point must have two coordinates")
    a, b = [[_motion_number(v, "coordinate", 0, 4096) for v in p] for p in points]
    fraction = (1. if elapsed >= at else 0.) if duration == 0 else min(1., max(0., (elapsed - at) / duration))
    return [a[i] + (b[i] - a[i]) * fraction for i in (0, 1)]


# A floor may carry a tile grid and props (desks, chairs, a blackboard ...). Solid props block walking; the walk
# is planned on the grid (breadth first, fixed neighbour order, so Python and the browser pick the same path) and
# played as a chain of the same constant-speed segments as above.
WORLD_PROPS = {"desk": True, "board": True, "wall": True, "shelf": True, "chair": False, "rug": False, "fire": False,
               "grass": False, "sand": False, "road": False, "bridge": False,
               "water": True, "tree": True, "cactus": True, "mountain": True, "house": True, "castle": True}   # kind -> blocks walking
# Ground kinds are laid first and open the tiles they cover (a road through trees, a bridge over water); the other kinds only block.
WORLD_GROUND = frozenset({"grass", "sand", "road", "bridge"})
# How the terrain kinds look: a colour (none: the ground shows through) and, for some, an emoji repeated once per tile, or drawn once across
# the prop (CSS only, written for the kinds a world uses). A floor becomes another place by swapping its kinds; the walking rules above are
# all the grid needs.
WORLD_LOOK = {"grass": ("#8fd694", "", False), "sand": ("#efd9a0", "", False), "road": ("#d2b48c", "", False), "bridge": ("#a9784a", "", False),
              "water": ("#5aaae0", "🌊", False), "mountain": ("#b8a58f", "⛰️", False), "tree": ("", "🌲", False), "cactus": ("", "🌵", False),
              "house": ("", "🏠", False), "castle": ("", "🏰", True), "fire": ("", "🔥", False)}
_WORLD_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
WORLD_SIGNS = ("led", "wood")      # a spot drawn as a small board on a bold dot: an electronic one (amber on black) or a wooden one


def world_blocked(width: int, height: int, tile: int, props: list[dict[str, Any]]) -> list[str]:
    """The walking grid: one string per tile row, ``"1"`` for a tile covered by a solid prop and ``"0"`` otherwise."""
    cells = [["0"] * (width // tile) for _ in range(height // tile)]
    for prop in props:
        if prop["kind"] in WORLD_GROUND or WORLD_PROPS[prop["kind"]]:
            mark = "0" if prop["kind"] in WORLD_GROUND else "1"
            for cy in range(prop["y"] // tile, (prop["y"] + prop["h"]) // tile):
                for cx in range(prop["x"] // tile, (prop["x"] + prop["w"]) // tile):
                    cells[cy][cx] = mark
    return ["".join(row) for row in cells]


def world_reach(blocked: list[str], start: tuple[int, int]) -> dict[tuple[int, int], tuple[int, int] | None]:
    """Every cell that can be walked to from ``start`` (always allowed), each with the cell it was reached from (``None`` for ``start``).

    Breadth first in a fixed neighbour order, so the dict's order is the search order and the paths are the same in Python and the browser.
    """
    cols, rows = len(blocked[0]), len(blocked)
    parent: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    order = [start]
    for cx, cy in order:
        for dx, dy in _WORLD_STEPS:
            n = (cx + dx, cy + dy)
            if 0 <= n[0] < cols and 0 <= n[1] < rows and blocked[n[1]][n[0]] == "0" and n not in parent:
                parent[n] = (cx, cy)
                order.append(n)
    return parent


def world_path(blocked: list[str], start: list[int], goal: list[int]) -> list[list[int]]:
    """Shortest 4-neighbour cell path from ``start`` (always allowed) to ``goal``.

    A goal that is solid, outside or cut off ends the path at the reachable cell nearest to it (the first such
    cell in search order). Cells clamp into the grid.
    """
    cols, rows = len(blocked[0]), len(blocked)
    def clamp(c: list[int]) -> tuple[int, int]:
        return min(cols - 1, max(0, int(c[0]))), min(rows - 1, max(0, int(c[1])))
    start, goal = clamp(start), clamp(goal)
    parent = world_reach(blocked, start)
    end = goal if goal in parent else min(parent, key=lambda c: (c[0] - goal[0]) ** 2 + (c[1] - goal[1]) ** 2)
    path = [end]
    while parent[path[-1]] is not None:
        path.append(parent[path[-1]])
    return [list(c) for c in reversed(path)]


def world_route_points(blocked: list[str], tile: int, start: list[float], target: list[float]) -> list[list[float]]:
    """Points to walk from ``start`` toward ``target`` on the grid: tile centres, ending at ``target`` itself when its tile is reachable."""
    def cell(p: list[float]) -> list[int]:
        return [min(n - 1, max(0, math.floor(v / tile))) for v, n in zip(p, (len(blocked[0]), len(blocked)))]
    path = world_path(blocked, cell(start), cell(target))
    centres = [[(c[0] + .5) * tile, (c[1] + .5) * tile] for c in path[1:]]
    return [list(start), *(centres[:-1] + [list(target)] if path[-1] == cell(target) else centres)]


def world_route(points: list[list[float]], *, at: float = 0, speed: float = 40,
                width: float = 1024, height: float = 768) -> list[dict[str, Any]]:
    """Constant-speed segments one after another through ``points`` (a single still segment when there is nowhere to go)."""
    route, t = [], _motion_number(at, "at", 0, 1e9)
    for a, b in zip(points, points[1:]):
        route.append(world_walk(a, b, at=t, speed=speed, width=width, height=height))
        t += route[-1]["duration"]
    return route or [world_walk(points[0], points[0], at=t, speed=speed, width=width, height=height)]


def world_route_sample(route: list[dict[str, Any]], elapsed: float) -> list[float]:
    """Position along a ``world_route`` at absolute elapsed seconds; the end holds."""
    for segment in route:
        if elapsed < segment["at"] + segment["duration"]:
            return world_motion_sample(segment, elapsed)
    return world_motion_sample(route[-1], elapsed)


def travel_seconds(x0: float, y0: float, x1: float, y1: float, speed: float) -> float:
    """Seconds to walk in a straight line at constant ``speed`` (map units per second)."""
    x0, y0, x1, y1 = [_motion_number(v, "coordinate", -1e6, 1e6) for v in (x0, y0, x1, y1)]
    speed = _motion_number(speed, "speed", 1, 480)
    return math.hypot(x1 - x0, y1 - y0) / speed


def minutes_until(now: float, at: int) -> int:
    """Ceil minutes to the daily next occurrence; zero only at the exact target.

    ``now`` is fractional minutes since midnight, ``at`` is an HH:MM minute.
    Immediately after the target, the next occurrence is tomorrow (up to 1440).
    """
    now = _motion_number(now, "now (minutes since midnight)", 0, 1440)
    at = _bounded_int(at, "at (minutes since midnight)", 0, 1439)
    return math.ceil((at - now) % 1440)


def board_clock(now: float, offset_minutes: int) -> dict[str, Any]:
    """Injected Unix seconds + fixed UTC-offset minutes, independent of host TZ. ``clock`` is ``HH:MM:SS`` (the board's own clock shows
    all of it; a zone chip and the stamp on a visitor's line keep ``HH:MM``, its first five characters)."""
    now = _motion_number(now, "now (Unix seconds)", 0, 253402214400)
    offset_minutes = _bounded_int(offset_minutes, "offset_minutes", -840, 840)
    seconds = (now + offset_minutes * 60) % 86400
    whole = math.floor(seconds)
    return {"clock": f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}", "minutes": seconds / 60}


def board_seconds(chars: int, chars_per_second: float = 8.0) -> float:
    """Seconds for one lap of the scrolling board: constant speed, never quicker than 8 s."""
    return max(8.0, math.floor(chars / chars_per_second * 10 + 0.5) / 10)


# Gauge glyph pairs, ``(elapsed, remaining)``. An hourglass is only one of them; any two short symbols work (``glyphs: ["🔥", "🪵"]``).
GAUGE_GLYPHS: dict[str, tuple[str, str]] = {
    "hourglass": ("⌛", "⏳"), "moon": ("🌕", "🌑"), "heart": ("❤️", "🤍"), "square": ("🟩", "⬜"),
    "dot": ("●", "○"), "block": ("█", "░"), "star": ("⭐", "☆"),
}


def gauge_state(now: int, start: int, end: int, cells: int) -> tuple[int, int, str]:
    """``(filled cells, percent, phase)`` of a window ``start``..``end`` (minutes since midnight; ``end`` before ``start`` runs past midnight)
    at minute ``now``. Integer arithmetic only, so the page agrees exactly. Outside the window the nearer edge decides: ``before`` (empty)
    or ``after`` (full); a tie counts as ``before``."""
    span = (end - start) % 1440 or 1440
    elapsed = (now - start) % 1440
    if elapsed < span:
        return elapsed * cells // span, elapsed * 100 // span, "active"
    return (0, 0, "before") if (start - now) % 1440 <= (now - end) % 1440 else (cells, 100, "after")


def gauge_cells(filled: int, cells: int, glyphs: tuple[str, str] | list[str]) -> str:
    """The gauge as text: ``filled`` elapsed glyphs, then the remaining ones, ``cells`` in all."""
    return glyphs[0] * filled + glyphs[1] * (cells - filled)


def clock_label(minutes: int) -> str:
    """``HH:MM`` for minutes since midnight: the stamp on a visitor's line."""
    return f"{minutes // 60 % 24:02d}:{minutes % 60:02d}"


ZONE_YEARS = (2020, 2040)   # the window a board's zone table covers, [start, end); outside it the nearest end's offset is kept


@functools.lru_cache(maxsize=None)
def zone_rows(tz: str) -> tuple[int, ...]:
    """Flat ``(utc_epoch_seconds, offset_minutes, ...)`` pairs: the offset in force from each instant on, from the start of ``ZONE_YEARS``.
    Built from the system IANA database with ``zoneinfo`` (no hand-written DST rules); the page only looks the table up.
    The scan and the bisection of each change to the second follow flutter_navigation_basic ``python/generate_zone_table.py``."""
    import datetime as dt
    import zoneinfo
    if not isinstance(tz, str) or not re.fullmatch(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+){0,2}", tz):
        raise ValueError(f"not a time zone name: {tz!r}")
    try:
        zone = zoneinfo.ZoneInfo(tz)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError(f"time zone {tz!r} is unknown or the system has no time zone data (install tzdata)") from error
    utc = dt.timezone.utc
    offset = lambda at: int(at.astimezone(zone).utcoffset().total_seconds() // 60)
    start, end = dt.datetime(ZONE_YEARS[0], 1, 1, tzinfo=utc), dt.datetime(ZONE_YEARS[1], 1, 1, tzinfo=utc)
    now, here = start, offset(start)
    rows = [int(start.timestamp()), here]
    while now < end:
        nxt = min(now + dt.timedelta(hours=6), end)
        there = offset(nxt)
        if there != here and nxt < end:
            low, high = int(now.timestamp()), int(nxt.timestamp())
            while high - low > 1:                                   # the first second the new offset applies
                mid = (low + high) // 2
                low, high = (mid, high) if offset(dt.datetime.fromtimestamp(mid, utc)) == here else (low, mid)
            rows += [high, there]
            here = there
        now = nxt
    return tuple(rows)


def zone_offset(rows: tuple[int, ...] | list[int], utc_seconds: float) -> int:
    """Minutes east of UTC in force at ``utc_seconds`` according to ``zone_rows``; before the first row, the first row's offset."""
    return rows[2 * max(bisect.bisect_right(rows[0::2], utc_seconds) - 1, 0) + 1]


def utc_offset_label(offset_minutes: int) -> str:
    """The time zone the board may show beside its clock: ``UTC``, ``UTC+9``, ``UTC+5:30``, ``UTC-5``. The offset only, never a place name."""
    if offset_minutes == 0:
        return "UTC"
    hours, minutes = divmod(abs(offset_minutes), 60)
    return f"UTC{'+' if offset_minutes > 0 else '-'}{hours}" + (f":{minutes:02d}" if minutes else "")


# The spaces the board collapses (ASCII spaces, NBSP, the Unicode space separators, line/paragraph separators); the page uses the same set.
_MESSAGE_SPACE = frozenset(" \t\n\r\f\v\u00a0\u1680\u2028\u2029\u202f\u205f\u3000") | {chr(c) for c in range(0x2000, 0x200B)}


def clean_message(text: Any, limit: int = 60) -> str | None:
    """What the board shows for a visitor's line: control characters dropped (a zero-width joiner stays, so emoji sequences survive),
    whitespace collapsed, cut to ``limit`` characters;
    ``None`` when nothing is left. The page applies the same rule and puts the result in as text, never as HTML."""
    if not isinstance(text, str):
        return None
    kept = "".join(" " if c in _MESSAGE_SPACE else c for c in text if c in _MESSAGE_SPACE or c == "\u200d" or c.isprintable())
    kept = " ".join(word for word in kept.split(" ") if word)[:limit].rstrip()
    return kept or None


def villager_path(seed: int, width: int, height: int, *, speed: float = 48.0, margin: int = 32, stops: int = 4) -> dict[str, Any]:
    """A seeded loop for one villager: straight walks at constant ``speed`` to random points, a random pause at each (1..4 s),
    then a walk back to the start so the loop is seamless. Returns ``{"duration": seconds, "keys": [(percent, x, y), ...]}``;
    between keys the motion is linear, a pause is two keys at the same point."""
    seed = _bounded_int(seed, "seed", 0, 2**32 - 1)
    width = _bounded_int(width, "width", 64, 4096)
    height = _bounded_int(height, "height", 64, 4096)
    margin = _bounded_int(margin, "margin", 0, min(width, height) // 2)
    stops = _bounded_int(stops, "stops", 1, 64)
    speed = _motion_number(speed, "speed", 1, 480)
    rng = random.Random(seed)
    point = lambda: (round(margin + rng.random() * max(0, width - 2 * margin), 1), round(margin + rng.random() * max(0, height - 2 * margin), 1))
    start = point()
    here, clock, steps = start, 0.0, [(0.0, start)]
    for _ in range(stops):
        target = point()
        clock += travel_seconds(*here, *target, speed)
        steps.append((clock, target))
        clock += 1.0 + rng.random() * 3.0
        steps.append((clock, target))
        here = target
    clock += travel_seconds(*here, *start, speed)
    steps.append((clock, start))
    total = max(clock, 1.0)
    return {"duration": total, "keys": [((t / total) * 100, x, y) for t, (x, y) in steps]}


def _world_text(value: Any, label: str, limit: int, *, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()) or len(value) > limit:
        raise ValueError(f"{label} must be {1 if required else 0}..{limit} characters")
    return value


def _world_id(value: Any, label: str, seen: set[str]) -> str:
    if not isinstance(value, str) or not _WORLD_TOKEN.fullmatch(value) or value in seen:
        raise ValueError(f"{label} must be a unique lowercase token: {value!r}")
    seen.add(value)
    return value


# Direction from two positions. A point is the centre of an object or the middle of one of its edges; the arrow says which way to go
# from the first point to reach the second (screen y grows downward, so a target below is ⬇️ and a target above and to the right is ↗️).
# The page repeats this arithmetic (``direction`` in WORLD_JS); integers only meet an integer slope test, so both always agree.
WORLD_ANCHORS = {"center": (.5, .5), "left": (0, .5), "right": (1, .5), "top": (.5, 0), "bottom": (.5, 1),
                 "top-left": (0, 0), "top-right": (1, 0), "bottom-left": (0, 1), "bottom-right": (1, 1)}
WORLD_HERE = "📍"
_WORLD_ARROWS = {(1, 0): "➡️", (1, 1): "↘️", (0, 1): "⬇️", (-1, 1): "↙️", (-1, 0): "⬅️", (-1, -1): "↖️", (0, -1): "⬆️", (1, -1): "↗️"}
# Plain, text and emoji forms of an arrow name the same anchor, as in Ironmate's focus arrows; 🎯 and 📍 mean the centre.
_WORLD_ARROW_ANCHORS = {"←": "left", "⬅": "left", "→": "right", "➡": "right", "↑": "top", "⬆": "top", "↓": "bottom", "⬇": "bottom",
                        "↖": "top-left", "↗": "top-right", "↙": "bottom-left", "↘": "bottom-right", "🎯": "center", "📍": "center"}


def world_point(rect: Any, at: str = "center") -> tuple[float, float]:
    """The point of ``rect`` (``(x, y, w, h)``, or a dict with those keys) named by ``at``: ``center``, an edge (``left``, ``right``,
    ``top``, ``bottom``) or a corner (``top-left`` ...). A spot or a person is a rect with no size."""
    if at not in WORLD_ANCHORS:
        raise ValueError(f"at is one of {', '.join(WORLD_ANCHORS)}: {at!r}")
    x, y, w, h = (rect[k] for k in "xywh") if isinstance(rect, dict) else rect
    return x + w * WORLD_ANCHORS[at][0], y + h * WORLD_ANCHORS[at][1]


def world_direction(a: Any, b: Any, eps: float = 8) -> str:
    """The arrow pointing from point ``a`` to point ``b``: eight sectors of 45 degrees, or 📍 when both axes are within ``eps``.

    The sectors are tested with an integer slope (5/12, about 22.6 degrees), so no trigonometry and no rounding can differ in the browser."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if abs(dx) <= eps and abs(dy) <= eps:
        return WORLD_HERE
    ax, ay = abs(dx), abs(dy)
    if ay * 12 <= ax * 5:
        key = (1 if dx > 0 else -1, 0)
    elif ax * 12 <= ay * 5:
        key = (0, 1 if dy > 0 else -1)
    else:
        key = (1 if dx > 0 else -1, 1 if dy > 0 else -1)
    return _WORLD_ARROWS[key]


def world_arrow_anchor(arrow: str) -> str:
    """The anchor an arrow emoji names (``↘️`` is ``bottom-right``, ``⬅`` is ``left``, ``🎯`` is ``center``); variation selectors are ignored."""
    name = arrow.replace("︎", "").replace("️", "")
    if name not in _WORLD_ARROW_ANCHORS:
        raise ValueError(f"not an arrow: {arrow!r}")
    return _WORLD_ARROW_ANCHORS[name]


def _world_emoji(value: Any) -> str:
    """An emoji (or any short non-ASCII symbol string); plain ASCII is refused so text cannot pose as a character."""
    if not isinstance(value, str) or not 1 <= len(value) <= 16 or any(c.isascii() for c in value):
        raise ValueError("emoji must be 1..16 non-ASCII characters")
    return value


def _world_mark(value: Any) -> str:
    """A spot's mark: the emoji (or 1..2 characters) drawn instead of the dot, and before the name when the name shows."""
    if not isinstance(value, str) or not 1 <= len(value) <= 8 or len(value.strip()) != len(value) or any(unicodedata.category(c) in ("Cc", "Cs", "Zl", "Zp", "Zs") or c in "\\\"'" for c in value):
        raise ValueError("a mark is one emoji or 1..2 characters, without spaces, quotes or control characters")
    return value


def _world_avatar(value: Any) -> str:
    """A visitor's character: an emoji, a short text (an initial, a name), or both, 1..16 characters. One label, never markup (the page sets
    it as text): control and line-separator characters, bidirectional overrides and spaces at either end are refused."""
    if (not isinstance(value, str) or not 1 <= len(value) <= 16 or "Zs" in (unicodedata.category(value[0]), unicodedata.category(value[-1]))
            or any(unicodedata.category(c) in ("Cc", "Cs", "Zl", "Zp") or c in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for c in value)):
        raise ValueError("an avatar is 1..16 characters of emoji or text, without control characters or edge spaces")
    return value


def _world_hhmm(value: Any, label: str) -> int:
    """Minutes since midnight for an ``HH:MM`` string."""
    if not (isinstance(value, str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)):
        raise ValueError(f"{label} must be HH:MM")
    return int(value[:2]) * 60 + int(value[3:])


def _gauge_glyph(value: Any) -> str:
    """One gauge cell: 1..8 visible characters (emoji sequences welcome); no spaces or control characters."""
    if not isinstance(value, str) or not 1 <= len(value) <= 8:
        raise ValueError("a gauge glyph is 1..8 visible characters")
    visible = any(unicodedata.category(c)[0] in "LNSP"
                  and c not in "\u115f\u1160\u2800\u3164\uffa0" for c in value)
    if not visible or any(c.isspace() or not (c.isprintable() or c == "\u200d") for c in value):
        raise ValueError("a gauge glyph is 1..8 visible characters")
    return value


def _world_gauge(gauge: Any) -> dict[str, Any]:
    """Checked, normalized gauge: ``{"from", "to", "cells", "glyphs": [elapsed, remaining]}``; ``glyphs`` may name a ``GAUGE_GLYPHS`` preset."""
    if not isinstance(gauge, dict) or set(gauge) - {"from", "to", "cells", "glyphs"}:
        raise ValueError("a gauge requires from and to; cells and glyphs are optional")
    start, end = _world_hhmm(gauge.get("from"), "from"), _world_hhmm(gauge.get("to"), "to")
    if start == end:
        raise ValueError("a gauge needs a window: from and to differ")
    glyphs = gauge.get("glyphs", "hourglass")
    if isinstance(glyphs, str):
        if glyphs not in GAUGE_GLYPHS:
            raise ValueError(f"unknown glyph set {glyphs!r} (one of {', '.join(GAUGE_GLYPHS)})")
        glyphs = GAUGE_GLYPHS[glyphs]
    elif not isinstance(glyphs, (list, tuple)) or len(glyphs) != 2:
        raise ValueError("glyphs is a preset name or [elapsed, remaining]")
    return {"from": gauge["from"], "to": gauge["to"], "cells": _bounded_int(gauge.get("cells", 10), "cells", 3, 20),
            "glyphs": [_gauge_glyph(g) for g in glyphs]}


def _world_tile(value: Any) -> int:
    """A tile size: 16..128 and a multiple of 8."""
    tile = _bounded_int(value, "tile", 16, 128)
    if tile % 8:
        raise ValueError("tile is a multiple of 8")
    return tile


def _bounded_int(value: Any, label: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer from {low} to {high}")
    return value


def board_validate(board: Any) -> dict[str, Any] | None:
    """The info board of a world (``None`` stays ``None``): a title, 1..12 items, optional zone clocks."""
    if board is None:
        return None
    if not isinstance(board, dict) or set(board) - {"title", "items", "post", "offset_label", "offset_minutes", "zones", "shared_issue"} or not isinstance(board.get("items"), list) \
            or not 1 <= len(board["items"]) <= 12 or not isinstance(board.get("post", False), bool) \
            or not isinstance(board.get("offset_label", False), bool):
        raise ValueError("a board has a title, 1..12 items, and optional post, offset_label, offset_minutes, zones and shared_issue")
    shared_issue = board.get("shared_issue")
    if shared_issue is not None:
        issue_bulletin_urls(shared_issue)
    zones, seen_zones = [], set()
    zones_in = board.get("zones", [])
    if not isinstance(zones_in, list) or len(zones_in) > 6:
        raise ValueError("zones is a list of up to 6 clocks")
    for entry in zones_in:
        if not isinstance(entry, dict) or set(entry) - {"id", "label", "tz"}:
            raise ValueError("a zone has id, label and tz")
        zone_rows(entry.get("tz"))                                                         # unknown names are refused here
        zones.append({"id": _world_id(entry.get("id"), "zone id", seen_zones), "label": _world_text(entry.get("label"), "label", 24),
                      "tz": entry["tz"]})
    items = []
    for item in board["items"]:
        if not isinstance(item, dict) or set(item) - {"text", "at", "gauge", "zone"}:
            raise ValueError("a board item has text and an optional at or gauge, and an optional zone")
        at, gauge = item.get("at"), item.get("gauge")
        if at is not None and gauge is not None:
            raise ValueError("a board item has either at or gauge, not both")
        if at is not None:
            _world_hhmm(at, "at")
        where = item.get("zone")
        if where is not None and (at is None and gauge is None or where not in seen_zones):
            raise ValueError("an item's zone names one of the board's zones and goes with at or gauge")
        items.append({"text": _world_text(item.get("text"), "text", 120), "at": at,
                      "gauge": None if gauge is None else _world_gauge(gauge), "zone": where})
    return {"title": _world_text(board.get("title", "INFO"), "title", 24), "items": items, "post": board.get("post", False),
            "offset_label": board.get("offset_label", False), "zones": zones, "shared_issue": shared_issue,
            "offset_minutes": (_bounded_int(board["offset_minutes"], "offset_minutes", -840, 840)
                               if board.get("offset_minutes") is not None else None)}


def _world_href(value: Any) -> str:
    """Where a tool or a row leads: a path of this site (``./``, ``../``, ``/``; never ``//host``), a fragment (``#``) or an ``https://`` address."""
    if not isinstance(value, str) or not 1 <= len(value) <= 200 or not re.fullmatch(r"(?:https://|\.{1,2}/|/(?!/)|#)[^\s\"'<>\\]*", value):
        raise ValueError("href is a ./ ../ / path, a # fragment or an https:// address, up to 200 characters")
    return value


def tools_validate(tools_in: Any, *, floor_ids: Any = (), spot_ids: Any = ()) -> dict[str, dict[str, Any]]:
    """The emoji a page adds to its header or side (``slot``), key → feature: each emoji does exactly one thing.

    ``floor``  jumps to a floor (a world)          ``spots``  a panel of the world's places
    ``href``   a link out (🏠 back, 🗼 another city)  ``links``  a panel of links (``[{"label", "href"}]``, up to 16)
    ``body``   a panel of words

    A world passes its floor and spot ids; without them ``floor`` and ``spots`` are refused."""
    tools: dict[str, dict[str, Any]] = {}
    if not isinstance(tools_in, dict) or len(tools_in) > 8:
        raise ValueError("tools maps up to 8 emoji to a feature")
    kinds = ("floor", "spots", "href", "links", "body") if floor_ids else ("href", "links", "body")
    for key, tool in tools_in.items():
        emoji = _world_emoji(key)
        if _plain_emoji(emoji) in WORLD_BUILTIN_TOOLS or emoji in tools:
            raise ValueError(f"{emoji} is already used by the page itself; tools take other emoji")
        if not isinstance(tool, dict) or set(tool) - _WORLD_TOOL_KEYS - set(kinds) or sum(k in tool for k in kinds) != 1:
            raise ValueError(f"a tool has label, label_en, labels, slot and exactly one of {', '.join(kinds)}")
        slot = tool.get("slot", "head")
        if slot not in ("head", "side"):
            raise ValueError("slot is head or side")
        label = _world_text(tool.get("label", emoji), "label", 24)
        built = {"label": label, "label_en": _world_text(tool.get("label_en", label), "label_en", 24), "slot": slot}
        more_labels = tool.get("labels", {})                                      # the other languages: {"fr": "Carte", "de": "Karte"}
        if not isinstance(more_labels, dict) or set(more_labels) - set(_WORLD_LANG_CODES[2:]):
            raise ValueError(f"labels maps language codes ({', '.join(_WORLD_LANG_CODES[2:])}) to words; ja and en are label and label_en")
        if more_labels:
            built["labels"] = {code: _world_text(text, "labels", 24) for code, text in more_labels.items()}
        if "floor" in tool:
            if tool["floor"] not in floor_ids:
                raise ValueError(f"tool floor must be one of {sorted(floor_ids)}")
            built["floor"] = tool["floor"]
        elif "spots" in tool:
            picked = tool["spots"]
            if not isinstance(picked, list) or not 1 <= len(picked) <= 16 or any(p not in spot_ids for p in picked):
                raise ValueError("tool spots lists 1..16 spot ids of the world")
            built["spots"] = list(picked)
        elif "href" in tool:
            built["href"] = _world_href(tool["href"])
        elif "links" in tool:
            links = tool["links"]
            if not isinstance(links, list) or not 1 <= len(links) <= 16 or any(not isinstance(l, dict) or set(l) != {"label", "href"} for l in links):
                raise ValueError("tool links lists 1..16 {label, href}")
            built["links"] = [{"label": _world_text(l["label"], "label", 40), "href": _world_href(l["href"])} for l in links]
        else:
            built["body"] = _world_text(tool["body"], "body", 400)
        tools[emoji] = built
    return tools


RPG_LEVEL_THRESHOLDS = (0, 30, 75, 140, 230, 350, 500, 700, 950, 1250)
RPG_LOOT_KINDS = ("drop", "chest")
RPG_ITEM_TYPES = ("heal", "mana", "food", "weapon", "armor", "charm", "scroll", "trophy")
RPG_QUEST_KINDS = ("talk", "drop", "chest", "battle", "item", "boss", "quiz", "floor")
RPG_SKILL_KINDS = ("attack", "heal", "guard")


def rpg_next_seed(seed: int) -> int:
    """Deterministic xorshift32 step delegated to PySaiyanWeBoo's ``play_random``."""
    return play_random(_bounded_int(seed, "seed", 0, 0xFFFFFFFF))


def rpg_orb_effect(amount: int, *, heal: bool = False) -> dict[str, Any]:
    """Battle/heal orb readout delegated to PySaiyanWeBoo's ``counter_effect`` and ``counter_label``."""
    amount = _bounded_int(amount, "amount", 0, 9999)
    signed = -amount if heal else amount
    effect = counter_effect(signed)
    return {**effect, "label": counter_label(signed)}


def rpg_level_for_exp(exp: int) -> dict[str, Any]:
    """Level and cumulative stat bonuses from total EXP (Lv 1..10)."""
    exp = _bounded_int(exp, "exp", 0, 999999)
    level = 1
    for idx, threshold in enumerate(RPG_LEVEL_THRESHOLDS, start=1):
        if exp >= threshold:
            level = idx
    next_exp = RPG_LEVEL_THRESHOLDS[level] if level < len(RPG_LEVEL_THRESHOLDS) else RPG_LEVEL_THRESHOLDS[-1]
    return {"level": level, "exp": exp, "next_exp": next_exp,
            "bonus_hp": (level - 1) * 6, "bonus_mp": (level - 1) * 3,
            "bonus_atk": (level - 1) * 2, "bonus_def": (level - 1) * 1}


def rpg_damage(atk: int, defense: int, roll_word: int, *, mult_pct: int = 100, guarding: bool = False,
               crit_pct: int = 12) -> dict[str, Any]:
    """Pure integer RPG battle damage matching ``WORLD_RPG_JS``."""
    atk = _bounded_int(atk, "atk", 1, 999)
    defense = _bounded_int(defense, "defense", 0, 999)
    roll_word = _bounded_int(roll_word, "roll_word", 0, 0xFFFFFFFF)
    mult_pct = _bounded_int(mult_pct, "mult_pct", 10, 500)
    crit_pct = _bounded_int(crit_pct, "crit_pct", 0, 100)
    if not isinstance(guarding, bool):
        raise ValueError("guarding must be bool")
    crit = (roll_word % 100) < crit_pct
    variance = ((roll_word >> 8) % 3) - 1
    raw = max(1, (atk * mult_pct) // 100 - defense // 2 + variance)
    if crit:
        raw = max(2, (raw * 3) // 2)
    if guarding:
        raw = max(1, raw // 2)
    return {"damage": raw, "crit": crit, "effect": rpg_orb_effect(raw)}


def rpg_validate(rpg_in: Any, *, spot_ids: set[str], floor_ids: set[str]) -> dict[str, Any]:
    """Checked copy of the optional ``rpg`` spec for contact dialogue, drops/chests, battles and gamification."""
    if not isinstance(rpg_in, dict) or set(rpg_in) - {"seed", "hero", "npcs", "loot", "enemies", "quests", "badges", "quizzes", "shop", "skills", "orbs"}:
        raise ValueError("rpg has seed, hero, npcs, loot, enemies, quests, badges, quizzes, shop, skills and orbs")
    seed = _bounded_int(rpg_in.get("seed", 20261126), "rpg seed", 0, 0xFFFFFFFF)
    hero_in = rpg_in.get("hero", {})
    if not isinstance(hero_in, dict) or set(hero_in) - {"hp", "mp", "atk", "def", "gold"}:
        raise ValueError("rpg hero has hp, mp, atk, def and gold")
    hero = {"hp": _bounded_int(hero_in.get("hp", 32), "hero hp", 1, 999),
            "mp": _bounded_int(hero_in.get("mp", 14), "hero mp", 0, 999),
            "atk": _bounded_int(hero_in.get("atk", 6), "hero atk", 1, 99),
            "def": _bounded_int(hero_in.get("def", 2), "hero def", 0, 99),
            "gold": _bounded_int(hero_in.get("gold", 0), "hero gold", 0, 99999)}
    npcs_in = rpg_in.get("npcs", {})
    if not isinstance(npcs_in, dict) or len(npcs_in) > 64:
        raise ValueError("rpg npcs maps up to 64 spot or actor ids")
    npcs: dict[str, dict[str, Any]] = {}
    for sid, entry in npcs_in.items():
        if sid not in spot_ids or not isinstance(entry, dict) or set(entry) - {"speaker", "emoji", "greeting", "lines", "topic", "on_contact", "heal", "shop", "quiz"}:
            raise ValueError(f"rpg npc {sid!r} must reference an existing spot or actor")
        lines = entry.get("lines", [])
        if not isinstance(lines, list) or len(lines) > 8:
            raise ValueError("rpg npc lines lists up to 8 strings")
        for flag in ("on_contact", "heal", "shop", "quiz"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise ValueError(f"rpg npc {flag} must be bool")
        topic = entry.get("topic")
        if topic is not None and (not isinstance(topic, dict) or set(topic) != {"question", "answer"}):
            raise ValueError("npc topic requires a question and an answer")
        npcs[sid] = {"speaker": _world_text(entry.get("speaker"), "speaker", 40),
                     "emoji": _world_emoji(entry.get("emoji")),
                     "greeting": _world_text(entry.get("greeting"), "greeting", 200),
                     "lines": [_world_text(line, "line", 240) for line in lines],
                     **({"topic": {k: _world_text(v, k, 240) for k, v in topic.items()}} if topic else {}),
                     **({"on_contact": True} if entry.get("on_contact") else {}),
                     **({"heal": True} if entry.get("heal") else {}),
                     **({"shop": True} if entry.get("shop") else {}),
                     **({"quiz": True} if entry.get("quiz") else {})}
    loot_in = rpg_in.get("loot", {})
    if not isinstance(loot_in, dict) or len(loot_in) > 64:
        raise ValueError("rpg loot maps up to 64 spot ids")
    loot: dict[str, dict[str, Any]] = {}
    for sid, entry in loot_in.items():
        if sid not in spot_ids or not isinstance(entry, dict) or set(entry) - {"kind", "item_type", "hp", "mp", "atk", "def", "exp", "gold", "consumable", "opened_mark", "requires_enemy"}:
            raise ValueError(f"rpg loot {sid!r} must reference an existing spot")
        kind = entry.get("kind")
        if kind not in RPG_LOOT_KINDS:
            raise ValueError(f"loot kind is one of {', '.join(RPG_LOOT_KINDS)}")
        itype = entry.get("item_type")
        if itype not in RPG_ITEM_TYPES:
            raise ValueError(f"item_type is one of {', '.join(RPG_ITEM_TYPES)}")
        if "consumable" in entry and not isinstance(entry["consumable"], bool):
            raise ValueError("consumable must be bool")
        req = entry.get("requires_enemy")
        if req is not None and req not in spot_ids:
            raise ValueError(f"requires_enemy {req!r} must reference an existing spot")
        loot[sid] = {"kind": kind, "item_type": itype,
                     "hp": _bounded_int(entry.get("hp", 0), "loot hp", 0, 999),
                     "mp": _bounded_int(entry.get("mp", 0), "loot mp", 0, 999),
                     "atk": _bounded_int(entry.get("atk", 0), "loot atk", 0, 99),
                     "def": _bounded_int(entry.get("def", 0), "loot def", 0, 99),
                     "exp": _bounded_int(entry.get("exp", 0), "loot exp", 0, 9999),
                     "gold": _bounded_int(entry.get("gold", 0), "loot gold", 0, 9999),
                     "consumable": bool(entry.get("consumable", itype in ("heal", "mana", "food", "scroll"))),
                     **({"opened_mark": _world_mark(entry["opened_mark"])} if "opened_mark" in entry else {}),
                     **({"requires_enemy": req} if req is not None else {})}
    enemies_in = rpg_in.get("enemies", {})
    if not isinstance(enemies_in, dict) or len(enemies_in) > 32:
        raise ValueError("rpg enemies maps up to 32 spot ids")
    enemies: dict[str, dict[str, Any]] = {}
    for sid, entry in enemies_in.items():
        if sid not in spot_ids or not isinstance(entry, dict) or set(entry) - {"name", "emoji", "level", "hp", "atk", "def", "exp", "gold", "weakness", "drop_spot", "boss", "on_contact", "taunt"}:
            raise ValueError(f"rpg enemy {sid!r} must reference an existing spot")
        drop_spot = entry.get("drop_spot")
        if drop_spot is not None and drop_spot not in spot_ids:
            raise ValueError(f"drop_spot {drop_spot!r} must reference an existing spot")
        for flag in ("boss", "on_contact"):
            if flag in entry and not isinstance(entry[flag], bool):
                raise ValueError(f"enemy {flag} must be bool")
        enemies[sid] = {"name": _world_text(entry.get("name"), "enemy name", 40),
                        "emoji": _world_emoji(entry.get("emoji")),
                        "level": _bounded_int(entry.get("level", 1), "enemy level", 1, 99),
                        "hp": _bounded_int(entry.get("hp"), "enemy hp", 1, 9999),
                        "atk": _bounded_int(entry.get("atk"), "enemy atk", 1, 999),
                        "def": _bounded_int(entry.get("def", 0), "enemy def", 0, 999),
                        "exp": _bounded_int(entry.get("exp", 10), "enemy exp", 0, 9999),
                        "gold": _bounded_int(entry.get("gold", 10), "enemy gold", 0, 9999),
                        "weakness": _world_text(entry.get("weakness", ""), "weakness", 32, required=False),
                        "taunt": _world_text(entry.get("taunt", ""), "taunt", 120, required=False),
                        **({"drop_spot": drop_spot} if drop_spot is not None else {}),
                        **({"boss": True} if entry.get("boss") else {}),
                        **({"on_contact": True} if entry.get("on_contact") else {})}
    quests_in = rpg_in.get("quests", [])
    if not isinstance(quests_in, list) or len(quests_in) > 24:
        raise ValueError("rpg quests lists up to 24 entries")
    quests, seen_q = [], set()
    for q in quests_in:
        if not isinstance(q, dict) or set(q) - {"id", "title", "desc", "kind", "target", "count", "reward_exp", "reward_gold", "reward_emoji", "reward_label"}:
            raise ValueError("quest has id, title, desc, kind, count, reward_exp, reward_gold")
        qkind = q.get("kind")
        if qkind not in RPG_QUEST_KINDS:
            raise ValueError(f"quest kind is one of {', '.join(RPG_QUEST_KINDS)}")
        target = q.get("target")
        if target is not None:
            if qkind == "floor" and target not in floor_ids:
                raise ValueError(f"quest floor target {target!r} unknown")
            if qkind in ("talk", "drop", "chest", "battle", "item", "boss") and target not in spot_ids:
                raise ValueError(f"quest spot target {target!r} unknown")
        quests.append({"id": _world_id(q.get("id"), "quest id", seen_q),
                       "title": _world_text(q.get("title"), "quest title", 48),
                       "desc": _world_text(q.get("desc"), "quest desc", 160),
                       "kind": qkind,
                       "count": _bounded_int(q.get("count", 1), "quest count", 1, 99),
                       "reward_exp": _bounded_int(q.get("reward_exp", 0), "reward_exp", 0, 9999),
                       "reward_gold": _bounded_int(q.get("reward_gold", 0), "reward_gold", 0, 9999),
                       **({"target": target} if target is not None else {}),
                       **({"reward_emoji": _world_emoji(q["reward_emoji"])} if "reward_emoji" in q else {}),
                       **({"reward_label": _world_text(q["reward_label"], "reward_label", 40)} if "reward_label" in q else {})})
    badges_in = rpg_in.get("badges", [])
    if not isinstance(badges_in, list) or len(badges_in) > 24:
        raise ValueError("rpg badges lists up to 24 entries")
    badges, seen_b = [], set()
    for b in badges_in:
        if not isinstance(b, dict) or set(b) - {"id", "emoji", "label", "desc"}:
            raise ValueError("badge has id, emoji, label and desc")
        badges.append({"id": _world_id(b.get("id"), "badge id", seen_b),
                       "emoji": _world_emoji(b.get("emoji")),
                       "label": _world_text(b.get("label"), "badge label", 40),
                       "desc": _world_text(b.get("desc"), "badge desc", 120)})
    quizzes_in = rpg_in.get("quizzes", [])
    if not isinstance(quizzes_in, list) or len(quizzes_in) > 24:
        raise ValueError("rpg quizzes lists up to 24 entries")
    quizzes = []
    for qz in quizzes_in:
        if not isinstance(qz, dict) or set(qz) - {"prompt", "choices", "correct", "explanation", "repo"}:
            raise ValueError("quiz has prompt, choices (3), correct (0..2) and explanation")
        choices = qz.get("choices")
        if not isinstance(choices, list) or len(choices) != 3:
            raise ValueError("quiz choices must have 3 items")
        quizzes.append({"prompt": _world_text(qz.get("prompt"), "quiz prompt", 200),
                        "choices": [_world_text(c, "quiz choice", 80) for c in choices],
                        "correct": _bounded_int(qz.get("correct"), "quiz correct", 0, 2),
                        "explanation": _world_text(qz.get("explanation"), "quiz explanation", 200),
                        **({"repo": _world_text(qz["repo"], "quiz repo", 80)} if "repo" in qz else {})})
    shop_in = rpg_in.get("shop", [])
    if not isinstance(shop_in, list) or len(shop_in) > 16:
        raise ValueError("rpg shop lists up to 16 items")
    shop, seen_sh = [], set()
    for sh in shop_in:
        if not isinstance(sh, dict) or set(sh) - {"id", "spot_id", "emoji", "label", "cost", "item_type", "hp", "mp", "desc"}:
            raise ValueError("shop item has id, emoji, label, cost, item_type, hp, mp and desc")
        itype = sh.get("item_type", "heal")
        if itype not in ("heal", "mana"):
            raise ValueError("shop item_type must be heal or mana")
        sid = sh.get("spot_id")
        if sid is not None and sid not in spot_ids:
            raise ValueError(f"shop spot_id {sid!r} must reference an existing spot")
        shop.append({"id": _world_id(sh.get("id"), "shop id", seen_sh),
                     "emoji": _world_emoji(sh.get("emoji")),
                     "label": _world_text(sh.get("label"), "shop label", 40),
                     "cost": _bounded_int(sh.get("cost"), "shop cost", 1, 9999),
                     "item_type": itype,
                     "hp": _bounded_int(sh.get("hp", 0), "shop hp", 0, 999),
                     "mp": _bounded_int(sh.get("mp", 0), "shop mp", 0, 999),
                     "desc": _world_text(sh.get("desc"), "shop desc", 160),
                     **({"spot_id": sid} if sid is not None else {})})
    skills_in = rpg_in.get("skills", [])
    if not isinstance(skills_in, list) or len(skills_in) > 8:
        raise ValueError("rpg skills lists up to 8 entries")
    skills, seen_sk = [], set()
    for sk in skills_in:
        if not isinstance(sk, dict) or set(sk) - {"id", "emoji", "label", "mp", "kind", "mult_pct", "power", "desc"}:
            raise ValueError("skill has id, emoji, label, mp, kind, mult_pct, power and desc")
        skind = sk.get("kind")
        if skind not in RPG_SKILL_KINDS:
            raise ValueError(f"skill kind is one of {', '.join(RPG_SKILL_KINDS)}")
        skills.append({"id": _world_id(sk.get("id"), "skill id", seen_sk),
                       "emoji": _world_emoji(sk.get("emoji")),
                       "label": _world_text(sk.get("label"), "skill label", 40),
                       "mp": _bounded_int(sk.get("mp", 0), "skill mp", 0, 99),
                       "kind": skind,
                       "mult_pct": _bounded_int(sk.get("mult_pct", 100), "skill mult_pct", 10, 500),
                       "power": _bounded_int(sk.get("power", 0), "skill power", 0, 999),
                       "desc": _world_text(sk.get("desc"), "skill desc", 160)})
    orbs_in = rpg_in.get("orbs")
    if orbs_in is None:
        orbs = {"attack": list(COUNTER_ATTACK_ORBS), "heal": list(COUNTER_HEAL_ORBS), "max": COUNTER_MAX_ORBS}
    else:
        if not isinstance(orbs_in, dict) or set(orbs_in) != {"attack", "heal", "max"}:
            raise ValueError("rpg orbs has attack, heal and max")
        orbs = {"attack": [_world_emoji(e) for e in orbs_in["attack"]],
                "heal": [_world_emoji(e) for e in orbs_in["heal"]],
                "max": _bounded_int(orbs_in["max"], "orbs max", 1, 12)}
    return {"seed": seed, "hero": hero, "npcs": npcs, "loot": loot, "enemies": enemies,
            "quests": quests, "badges": badges, "quizzes": quizzes, "shop": shop, "skills": skills, "orbs": orbs}


def world_validate(spec: Any) -> dict[str, Any]:
    """Checked copy of a ``web-ui-world/1`` spec: optional ``shots`` (scroll scenes) and ``floors`` (maps with spots)."""
    if not isinstance(spec, dict) or spec.get("schema") != WORLD_SCHEMA:
        raise ValueError(f"expected schema {WORLD_SCHEMA}")
    if set(spec) - {"schema", "id", "title", "shots", "floors", "zoom_max", "board", "avatars", "shell", "tools", "names", "mark_scale", "move", "rpg"}:
        raise ValueError("a world has schema, id, title, shots, floors, zoom_max, board, avatars, shell, tools, names, mark_scale, move and rpg")
    move = spec.get("move", "direct")
    if move not in ("direct", "confirm"):
        raise ValueError("move is direct or confirm")
    mark_scale = spec.get("mark_scale", [1, 1])
    if not isinstance(mark_scale, list) or len(mark_scale) != 2 or any(type(v) not in (int, float) or not .5 <= v <= 4 for v in mark_scale):
        raise ValueError("mark_scale is [x, y], each from 0.5 to 4: the width and height factor of every mark (dot or emoji)")
    names = spec.get("names", "names")
    if names not in WORLD_NAMES:
        raise ValueError("names is names (every spot shows its name), dots (a dot; the name beside the player, under the pointer or focused) or off (dots only)")
    shell = spec.get("shell", False)
    if not isinstance(shell, bool):
        raise ValueError("shell is true or false")
    avatars = spec.get("avatars", [])
    if not isinstance(avatars, list) or len(avatars) > 24 or len(set(map(str, avatars))) != len(avatars):
        raise ValueError("avatars is a list of up to 24 different emoji or short texts")
    avatars = [_world_avatar(a) for a in avatars]
    world_id = spec.get("id", "world")
    if not isinstance(world_id, str) or not _WORLD_ID.fullmatch(world_id):
        raise ValueError("id must be a lowercase token")
    shots_in, floors_in = spec.get("shots", []), spec.get("floors", [])
    if not isinstance(shots_in, list) or not isinstance(floors_in, list) or not (shots_in or floors_in):
        raise ValueError("a world needs shots or floors")
    if len(shots_in) > 12 or len(floors_in) > 8:
        raise ValueError("at most 12 shots and 8 floors")
    zoom_max = spec.get("zoom_max", 4)
    if type(zoom_max) not in (int, float) or not 1 <= zoom_max <= 8:
        raise ValueError("zoom_max must be from 1 to 8")
    ids: set[str] = set()
    shots = []
    for shot in shots_in:
        if not isinstance(shot, dict) or set(shot) - {"id", "label", "title", "body", "bg"}:
            raise ValueError("a shot has id, label, title, body and an optional bg")
        bg = shot.get("bg")
        if bg is not None and not (isinstance(bg, str) and _WORLD_HEX.fullmatch(bg)):
            raise ValueError("bg must be #rrggbb")
        shots.append({"id": _world_id(shot.get("id"), "shot id", ids), "label": _world_text(shot.get("label"), "label", 40),
                      "title": _world_text(shot.get("title"), "title", 80),
                      "body": _world_text(shot.get("body", ""), "body", 400, required=False), "bg": bg})
    floors, spot_ids = [], set()
    for floor in map(_expand_floor, floors_in):
        if not isinstance(floor, dict) or set(floor) - {"id", "label", "width", "height", "spots", "actors", "player", "tile", "props", "real"}:
            raise ValueError("a floor has id, label, width, height, spots, actors, player, tile, props and real")
        if not isinstance(floor.get("real", False), bool):
            raise ValueError("real is true or false")
        width, height = _bounded_int(floor.get("width"), "width", 64, 4096), _bounded_int(floor.get("height"), "height", 64, 4096)
        tile, props_in, props = floor.get("tile"), floor.get("props", []), []
        if tile is not None:
            tile = _world_tile(tile)
            if width % tile or height % tile:
                raise ValueError("tile divides the floor width and height")
        if not isinstance(props_in, list) or len(props_in) > 512 or (props_in and tile is None):
            raise ValueError("props (at most 512) need a tile grid")
        for prop in props_in:
            if not isinstance(prop, dict) or set(prop) != {"kind", "x", "y", "w", "h"} or prop["kind"] not in tuple(WORLD_PROPS):
                raise ValueError(f"a prop has kind ({', '.join(WORLD_PROPS)}), x, y, w and h")
            x, y = _bounded_int(prop["x"], "x", 0, width), _bounded_int(prop["y"], "y", 0, height)
            w, h = _bounded_int(prop["w"], "w", tile, width), _bounded_int(prop["h"], "h", tile, height)
            if any(v % tile for v in (x, y, w, h)) or x + w > width or y + h > height:
                raise ValueError("a prop lies on tiles, inside the floor")
            props.append({"kind": prop["kind"], "x": x, "y": y, "w": w, "h": h})
        spots_in = floor.get("spots")
        if not isinstance(spots_in, list) or not 1 <= len(spots_in) <= 64:
            raise ValueError("a floor lists 1..64 spots")
        spots = []
        for spot in spots_in:
            if not isinstance(spot, dict) or set(spot) - {"id", "x", "y", "label", "category", "body", "flip", "sign", "mark", "item", "always_named"}:
                raise ValueError("a spot has id, x, y, label, category, body, flip, sign, mark, item and always_named")
            if "sign" in spot and spot["sign"] not in WORLD_SIGNS:
                raise ValueError(f"sign is one of {', '.join(WORLD_SIGNS)}")
            named = spot.get("always_named", False)
            if not (isinstance(named, bool) or named in ("left", "right")) or (named and "sign" in spot):
                raise ValueError("always_named is true, left or right (the side its name hangs on), and a sign keeps its own dot and text")
            category = spot.get("category", "")
            if category != "" and not (isinstance(category, str) and _WORLD_TOKEN.fullmatch(category)):
                raise ValueError("category must be a lowercase token")
            item = None
            if "item" in spot:
                item_in = spot["item"]
                if not isinstance(item_in, dict) or set(item_in) - {"emoji", "label", "body"} or "emoji" not in item_in or "label" not in item_in:
                    raise ValueError("a spot item has emoji, label and optional body")
                item = {"emoji": _world_emoji(item_in["emoji"]), "label": _world_text(item_in["label"], "label", 40),
                        "body": _world_text(item_in.get("body", ""), "body", 400, required=False)}
            spots.append({"id": _world_id(spot.get("id"), "spot id", spot_ids), "x": _bounded_int(spot.get("x"), "x", 0, width),
                          "y": _bounded_int(spot.get("y"), "y", 0, height), "label": _world_text(spot.get("label"), "label", 40),
                          "category": category, "body": _world_text(spot.get("body", ""), "body", 400, required=False),
                          **({"flip": _world_text(spot["flip"], "flip", 16)} if "flip" in spot else {}),
                          **({"sign": spot["sign"]} if "sign" in spot else {}),
                          **({"mark": _world_mark(spot["mark"])} if "mark" in spot else {}),
                          **({"always_named": named} if named else {}),
                          **({"item": item} if item is not None else {})})
        actors = []
        actors_in = floor.get("actors", [])
        if not isinstance(actors_in, list) or len(actors_in) > 16:
            raise ValueError("a floor lists at most 16 actors")
        for actor in actors_in:
            if not isinstance(actor, dict) or set(actor) - {"id", "emoji", "label", "body", "seed", "speed"}:
                raise ValueError("an actor has id, emoji, label, body, seed and speed")
            seed = actor.get("seed")
            if seed is not None:
                _bounded_int(seed, "seed", 0, 2**31 - 1)
            speed = actor.get("speed", 48)
            if type(speed) not in (int, float) or not 8 <= speed <= 240:
                raise ValueError("speed must be from 8 to 240 (map units per second)")
            actors.append({"id": _world_id(actor.get("id"), "actor id", spot_ids), "emoji": _world_emoji(actor.get("emoji")),
                           "label": _world_text(actor.get("label"), "label", 40),
                           "body": _world_text(actor.get("body", ""), "body", 400, required=False), "seed": seed, "speed": speed})
        player = floor.get("player")
        if player is not None:
            if not isinstance(player, dict) or set(player) - {"emoji", "x", "y", "speed"}:
                raise ValueError("a player has emoji, x, y and speed")
            speed = player.get("speed", 96)
            if type(speed) not in (int, float) or not 8 <= speed <= 480:
                raise ValueError("speed must be from 8 to 480 (map units per second)")
            player = {"emoji": _world_avatar(player.get("emoji")), "x": _bounded_int(player.get("x"), "x", 0, width),
                      "y": _bounded_int(player.get("y"), "y", 0, height), "speed": speed}
            if tile and world_blocked(width, height, tile, props)[min(player["y"], height - 1) // tile][min(player["x"], width - 1) // tile] == "1":
                raise ValueError("the player starts on a free tile")
        floors.append({"id": _world_id(floor.get("id"), "floor id", ids), "label": _world_text(floor.get("label"), "label", 40),
                       "width": width, "height": height, "spots": spots, "actors": actors, "player": player,
                       **({"tile": tile, "props": props} if tile else {}), **({"real": True} if floor.get("real") else {})})
    board = board_validate(spec.get("board"))
    if spec.get("tools") and not floors:
        raise ValueError("tools maps up to 8 emoji to a feature, on a world with floors")
    tools = tools_validate(spec.get("tools", {}), floor_ids={f["id"] for f in floors}, spot_ids={s["id"] for f in floors for s in f["spots"]})
    rpg = rpg_validate(spec["rpg"], spot_ids=spot_ids, floor_ids={f["id"] for f in floors}) if spec.get("rpg") is not None else None
    if rpg is not None and not floors:
        raise ValueError("rpg requires a world with floors")
    return {"schema": WORLD_SCHEMA, "id": world_id, "title": _world_text(spec.get("title", "World"), "title", 80),
            "shots": shots, "floors": floors, "zoom_max": zoom_max, "board": board, "names": names, "move": move, "mark_scale": [float(v) for v in mark_scale], **({"avatars": avatars} if avatars else {}),
            **({"shell": True} if shell else {}), **({"tools": tools} if tools else {}), **({"rpg": rpg} if rpg is not None else {})}


def _floor_kit(tile: int, id: str) -> tuple[Any, Any]:
    """Makers a generated floor shares, in tile units: ``prop(kind, x, y, w=1, h=1)`` and ``spot(name, label, x, y, body)`` (a spot may sit between tiles)."""
    prop = lambda kind, x, y, w=1, h=1: {"kind": kind, "x": x * tile, "y": y * tile, "w": w * tile, "h": h * tile}  # noqa: E731
    spot = lambda name, text, x, y, body: {"id": f"{id}-{name}", "x": int(x * tile), "y": int(y * tile), "label": text, "body": body}  # noqa: E731
    return prop, spot


def _expand_floor(floor: Any) -> Any:
    """``{"id", "label", "classroom": {rows, groups, per_group, tile}}`` stands for ``classroom_floor(...)``, ``{"land": {theme, cols, rows, seed,
    tile}}`` for ``land_floor(...)`` and ``{"place": {points, meters, ...}}`` for ``place_floor(...)``, so JSON alone (no Python in the calling
    repository) can ask for a classroom, a land or a real place; ``spots``,
    ``actors`` and ``player`` given beside it replace the generated ones, and ``real`` marks it as a floor with a photo or camera behind it."""
    if not isinstance(floor, dict):
        return floor
    makers = {"classroom": (classroom_floor, {"rows", "groups", "per_group", "tile"}), "land": (land_floor, {"theme", "cols", "rows", "seed", "tile"}),
              "place": (place_floor, _PLACE_KEYS)}
    kind = next((k for k in makers if k in floor), None)
    if kind is None:
        return floor
    build, allowed = makers[kind]
    params, own = floor[kind], {"id", "label", kind, "spots", "actors", "player", "real"}
    if (not isinstance(params, dict) or set(params) - allowed or set(floor) - own
            or not all(isinstance(floor[k], str) for k in ("id", "label") if k in floor)):
        raise ValueError(f"a {kind} floor has id, label, {kind} ({', '.join(sorted(allowed))}) and optionally spots, actors, player and real")
    built = build(**params, **{k: floor[k] for k in ("id", "label") if k in floor})
    return {**built, **{k: floor[k] for k in ("spots", "actors", "player", "real") if k in floor}}


def classroom_floor(rows: int = 4, groups: int = 3, *, per_group: int = 2, tile: int = 32,
                    id: str = "classroom", label: str = "教室") -> dict[str, Any]:
    """A classroom floor: ``rows`` rows of desks, each with a chair below it, in ``groups`` blocks of ``per_group`` desks
    with an aisle between blocks; a blackboard and teacher's desk at the front, shelves and a door at the back.
    Every size is a multiple of ``tile`` (a multiple of 8). The player starts at the door.
    """
    rows, groups, per_group = (_bounded_int(rows, "rows", 1, 8), _bounded_int(groups, "groups", 1, 6),
                               _bounded_int(per_group, "per_group", 1, 4))
    tile = _world_tile(tile)
    side, front, back = 2, 5, 3                                           # tiles: side walkway, board area, door area
    cols, depth = 2 * side + groups * per_group + groups - 1, front + 2 * rows + back
    prop, spot = _floor_kit(tile, id)
    desk_w = min(3, cols - 2 * side)
    props = [prop("board", side, 0, cols - 2 * side), prop("desk", (cols - desk_w) // 2, 2, desk_w)]
    for r in range(rows):
        for g in range(groups):
            for k in range(per_group):
                x, y = side + g * (per_group + 1) + k, front + 2 * r
                props += [prop("desk", x, y), prop("chair", x, y + 1)]
    door = cols // 2 - 1                                                  # a two-tile gap in the back shelves
    props += [prop("shelf", 0, depth - 1, door), prop("shelf", door + 2, depth - 1, cols - door - 2)]
    return {"id": id, "label": label, "width": cols * tile, "height": depth * tile, "tile": tile, "props": props, "actors": [],
            "spots": [spot("board", "黒板", cols / 2, .5, "今日の連絡や課題を書く場所です。"),
                      spot("teacher", "先生の机", cols / 2, 3.5, "先生の席です。"),
                      spot("door", "出入口", cols / 2, depth - 1.5 - 1, "廊下や校庭へ出られます。")],
            "player": {"emoji": "🙂", "x": int((door + .5) * tile), "y": int((depth - .5) * tile), "speed": 96}}


# The lands of an overworld, like the countries of a Dragon Quest map: each theme swaps the objects (ground, edge, scatter, pond, houses) and
# nothing else. ``houses`` is how many of the village's eight plots are built; ``pond`` is (w, h) tiles, or "sea" for a strip along the north.
LAND_THEMES = {
    "meadow": {"label": "🌱 草原", "ground": "grass", "edge": "water", "fill": "tree", "density": .07, "pond": (4, 3), "houses": 6, "castle": False,
               "town": ("🏘️ はじまりの村", "家がならぶ、のどかな村です。"), "landmark": ("🌼 ひろば", "見晴らしのよい広場です。")},
    "forest": {"label": "🌲 森", "ground": "grass", "edge": "tree", "fill": "tree", "density": .28, "pond": None, "houses": 2, "castle": False,
               "town": ("🏡 森の家", "木々にかこまれた小さな家です。"), "landmark": ("⛩️ ほこら", "森の奥にある古いほこらです。")},
    "mountain": {"label": "⛰️ 山", "ground": "grass", "edge": "mountain", "fill": "mountain", "density": .16, "pond": None, "houses": 2, "castle": False,
                 "town": ("⛺ 山のふもと", "旅人が休むキャンプ地です。"), "landmark": ("🕳️ ほら穴", "山の奥へ続くほら穴です。")},
    "desert": {"label": "🏜️ 砂漠", "ground": "sand", "edge": "mountain", "fill": "cactus", "density": .05, "pond": (3, 2), "houses": 4, "castle": False,
               "town": ("🏜️ 砂の町", "日よけの屋根がならぶ町です。"), "landmark": ("🌴 オアシス", "水と木陰のある休み場です。")},
    "coast": {"label": "🌊 海辺", "ground": "sand", "edge": "water", "fill": "tree", "density": .04, "pond": "sea", "houses": 6, "castle": False,
              "town": ("⚓ みなと町", "船がとまる小さな港町です。"), "landmark": ("🐚 砂浜", "貝がらが落ちている浜辺です。")},
    "castle": {"label": "🏰 城下町", "ground": "grass", "edge": "mountain", "fill": "tree", "density": .06, "pond": None, "houses": 4, "castle": True,
               "town": ("🏰 お城", "町を見まもる大きなお城です。"), "landmark": ("🎪 広場", "市が立つにぎやかな広場です。")},
}
_LAND_PLOTS = ((-2, -1), (2, -1), (-2, 1), (2, 1), (-4, -1), (4, -1), (-4, 1), (4, 1))        # village plots beside the crossroads (tiles)


def land_floor(theme: str = "meadow", cols: int = 24, rows: int = 16, *, seed: int = 1, tile: int = 32,
               id: str = "land", label: str | None = None) -> dict[str, Any]:
    """One land of an overworld: ground, an edge, scattered trees or rocks, perhaps a pond, a village on a crossroads and a road to it.

    The same arguments always give the same land (a small seeded generator, not ``random``). The player starts at the foot of the road; two
    spots, the town and a landmark (the nearest bank of the water, else the farthest reachable tile), sit on tiles that can be walked to.
    """
    look = LAND_THEMES.get(theme)
    if look is None:
        raise ValueError(f"theme is one of {', '.join(LAND_THEMES)}")
    cols, rows, seed = _bounded_int(cols, "cols", 12, 48), _bounded_int(rows, "rows", 12, 32), _bounded_int(seed, "seed", 0, 2**31 - 1)
    tile = _world_tile(tile)
    if cols * tile > 4096 or rows * tile > 4096:
        raise ValueError("the land fits in 4096 units")
    state = seed % 2147483646 + 1
    def rand() -> float:                                                                   # Park-Miller: the same numbers in every Python
        nonlocal state
        state = state * 48271 % 2147483647
        return state / 2147483647
    cx, cy = cols // 2, rows // 2
    prop, spot = _floor_kit(tile, id)
    props: list[dict[str, Any]] = []
    put = lambda *args: props.append(prop(*args))                                            # noqa: E731  (laid in order: later kinds paint over earlier ones)
    taken: set[tuple[int, int]] = set()                                                    # tiles with something solid on them
    reserved: set[tuple[int, int]] = {(cx, y) for y in range(cy - 1 if look["castle"] else cy, rows - 1)}
    reserved |= {(x, cy) for x in range(max(1, cx - 4), min(cols - 1, cx + 5))} | {(x, rows - 2) for x in range(cx - 1, cx + 2)}
    put(look["ground"], 0, 0, cols, rows)
    for kind_args in ((0, 0, cols, 1), (0, rows - 1, cols, 1), (0, 1, 1, rows - 2), (cols - 1, 1, 1, rows - 2)):
        put(look["edge"], *kind_args)
    water: set[tuple[int, int]] = set()
    if look["pond"] == "sea":
        put("water", 1, 1, cols - 2, 3)
        water = {(x, y) for x in range(1, cols - 1) for y in range(1, 4)}
    elif look["pond"]:
        pw, ph = look["pond"]
        for _ in range(40):                                                                # away from the crossroads, or no pond at all
            x, y = 2 + int(rand() * (cols - pw - 3)), 2 + int(rand() * (rows - ph - 3))
            if not any(abs(x + i - cx) <= 6 and y + j >= cy - 4 for i in range(pw) for j in range(ph)):
                put("water", x, y, pw, ph)
                water = {(x + i, y + j) for i in range(pw) for j in range(ph)}
                break
    taken |= water
    plots = [(cx + dx, cy + dy) for dx, dy in _LAND_PLOTS[:look["houses"]]]
    for x, y in plots:
        put("house", x, y)
    if look["castle"]:
        put("castle", cx - 1, cy - 3, 3, 2)
        taken |= {(cx + i, cy - 3 + j) for i in range(-1, 2) for j in range(2)}
    taken |= set(plots)
    for y in range(1, rows - 1):                                                           # scattered trees or rocks, a row of them in one prop
        run = 0
        for x in range(1, cols):
            here = x < cols - 1 and (x, y) not in taken and (x, y) not in reserved and rand() < look["density"]
            if here:
                run += 1
            elif run:
                put(look["fill"], x - run, y, run, 1)
                run = 0
    put("road", cx, cy - (1 if look["castle"] else 0), 1, rows - 1 - cy + (1 if look["castle"] else 0))
    put("road", max(1, cx - 4), cy, min(cols - 1, cx + 5) - max(1, cx - 4), 1)
    blocked = world_blocked(cols * tile, rows * tile, tile, props)
    dist: dict[tuple[int, int], int] = {}                                                  # steps from the start, in search order
    for cell, came_from in world_reach(blocked, (cx, rows - 2)).items():
        dist[cell] = 0 if came_from is None else dist[came_from] + 1
    shore = [c for c in dist if c != (cx, cy) and any((c[0] + dx, c[1] + dy) in water for dx, dy in _WORLD_STEPS)]
    far = (min(shore, key=lambda c: (dist[c], c[1], c[0])) if shore                       # with water: the nearest bank; without: the farthest tile
           else min((c for c in dist if c != (cx, cy)), key=lambda c: (-dist[c], c[1], c[0])))
    place = lambda name, text, at: spot(name, text[0], at[0] + .5, at[1] + .5, text[1])      # noqa: E731  (a spot stands in the middle of its tile)
    return {"id": id, "label": label or look["label"], "width": cols * tile, "height": rows * tile, "tile": tile, "props": props, "actors": [],
            "spots": [place("town", look["town"], (cx, cy)), place("landmark", look["landmark"], far)],
            "player": {"emoji": "🙂", "x": int((cx + .5) * tile), "y": int((rows - 1.5) * tile), "speed": 96}}


# A real place in miniature: points with a latitude and longitude laid on the tile grid (``meters`` of ground per tile), roads between linked
# points, and rivers as bands of water that roads cross as bridges. The projection and the box come from the coordinate tools below (the same
# Earth radius and ``tolerance_area``), so a place is only data: a list of points, nothing drawn by hand.
_PLACE_KEYS = {"points", "meters", "tile", "links", "rivers", "area", "start", "scatter", "marks", "always_named"}
_PLACE_POINT_KEYS = {"id", "label", "lat", "lon", "maps", "category", "body", "flip", "sign", "mark"}


def _place_point(point: Any, seen: set[str]) -> dict[str, Any]:
    if not isinstance(point, dict) or set(point) - _PLACE_POINT_KEYS or ("maps" in point) == ("lat" in point or "lon" in point) \
            or ("lat" in point) != ("lon" in point):
        raise ValueError("a point has id, label, category, body, flip, sign, mark and either lat and lon or maps (a Maps URL)")
    if "maps" in point:
        found = try_parse_maps_url(point["maps"]) if isinstance(point["maps"], str) else None
        if found is None:
            raise ValueError("maps has no coordinates in it")
        lat, lon = found
    else:
        lat, lon = parse_coordinate(point["lat"], point["lon"])
    category = point.get("category", "")
    if category != "" and not (isinstance(category, str) and _WORLD_TOKEN.fullmatch(category)):
        raise ValueError("category must be a lowercase token")
    if "sign" in point and point["sign"] not in WORLD_SIGNS:
        raise ValueError(f"sign is one of {', '.join(WORLD_SIGNS)}")
    return {"id": _world_id(point.get("id"), "point id", seen), "label": _world_text(point.get("label"), "label", 40), "lat": lat, "lon": lon,
            "category": category, "body": _world_text(point.get("body", ""), "body", 400, required=False),
            **({"flip": _world_text(point["flip"], "flip", 16)} if "flip" in point else {}),
            **({"sign": point["sign"]} if "sign" in point else {}), **({"mark": _world_mark(point["mark"])} if "mark" in point else {})}


def _place_meters(lat: float, lon: float, north: float, west: float, mid: float) -> tuple[float, float]:
    """Metres east of ``west`` and south of ``north`` on a flat map whose scale is that of latitude ``mid`` (good for a few kilometres)."""
    return ((lon - west) * math.cos(mid * math.pi / 180) * math.pi / 180 * EARTH_RADIUS_M, (north - lat) * math.pi / 180 * EARTH_RADIUS_M)


def _place_rects(cells: set[tuple[int, int]]) -> list[tuple[int, int, int, int]]:
    """Tiles as rectangles ``(x, y, w, h)``: horizontal runs, then equal runs on the rows below stacked into one, so a road is a few props, not one per tile."""
    open_rects: dict[tuple[int, int], list[int]] = {}                                       # (x, w) -> [y, h] of the rectangle still growing
    done: list[tuple[int, int, int, int]] = []
    for y in range(min((c[1] for c in cells), default=0), max((c[1] for c in cells), default=-1) + 1):
        xs = sorted(x for x, cy in cells if cy == y)
        runs, start = [], None
        for i, x in enumerate(xs):
            if start is None:
                start = x
            if i + 1 == len(xs) or xs[i + 1] != x + 1:
                runs.append((start, x - start + 1))
                start = None
        for key in [k for k in open_rects if k not in runs]:
            top, height = open_rects.pop(key)
            done.append((key[0], top, key[1], height))
        for run in runs:
            if run in open_rects:
                open_rects[run][1] += 1
            else:
                open_rects[run] = [y, 1]
    done += [(key[0], top, key[1], height) for key, (top, height) in open_rects.items()]
    return sorted(done, key=lambda r: (r[1], r[0]))


def place_floor(points: list[dict[str, Any]], *, meters: int = 64, tile: int = 32, links: Any = (), rivers: Any = (), area: Any = None,
                start: str | None = None, scatter: Any = None, marks: Any = None, always_named: Any = (), id: str = "place",
                label: str = "場所") -> dict[str, Any]:
    """A real place as a floor: each point (``id``, ``label``, ``lat`` and ``lon``, or ``maps`` with a Maps URL; optional ``category`` and ``body``) becomes a
    spot on the tile its position falls on, ``meters`` of ground per tile.

    ``links`` are pairs of point ids joined by an L-shaped road; ``rivers`` are ``{"line": [[lat, lon], ...], "width": tiles}`` bands of water, and a road
    that crosses one becomes a bridge. ``area`` is ``{"center": [lat, lon], "radius": metres}``, the box ``tolerance_area`` gives (without it the map is the
    points' box and a margin of two tiles). Two points on one tile are moved to the nearest free tile (the earlier point keeps its tile), and a
    point that is cut off from the player's start by water is an error, so every spot can be walked to. The player starts at ``start`` (a point id,
    default the first point that is not a sign). A point's ``flip`` is a second face that its pill swaps with the label when it is pressed.

    A point with a ``sign`` (``led`` or ``wood``) is a small board on a bold dot at the nearest **tile corner** instead of the middle of a tile, so
    it takes no tile and sits between the stations; two signs on one corner go to the nearest free corner, and it must touch a tile that can be walked on.

    ``marks`` is ``{category: emoji}``: a point without its own ``mark`` gets its category's emoji as the mark drawn instead of the dot
    (``mark_scale`` on the world sets the marks' width and height factors). ``always_named`` lists the categories whose points always show
    their names, faint in the name layer behind the marks, whatever the world's ``names`` says (a sign keeps its own dot and text). Their names
    hang away from the middle of the group (west of it to the left, east of it to the right), the mark staying on the point, so the two sides
    of a station do not cover each other; a spot's own ``always_named`` is ``true`` (centred), ``"left"`` or ``"right"``.

    ``scatter`` is ``{"kind": "fire", "every": 8, "seed": 1}``: the map is cut into blocks of ``every`` tiles and one free tile in each gets the kind
    (a decoration such as ``fire``: not ground, not solid), chosen by a small seeded generator, so the same arguments give the same places.
    """
    tile, meters = _world_tile(tile), _bounded_int(meters, "meters", 8, 2000)
    if not isinstance(points, list) or not 1 <= len(points) <= 64:
        raise ValueError("a place lists 1..64 points")
    seen: set[str] = set()
    pts = [_place_point(p, seen) for p in points]
    if area is not None:
        if not isinstance(area, dict) or set(area) != {"center", "radius"} or not isinstance(area["center"], list) or len(area["center"]) != 2 \
                or type(area["radius"]) not in (int, float):
            raise ValueError("area is {center: [lat, lon], radius: metres}")
        clat, clon = parse_coordinate(area["center"][0], area["center"][1])
        box = tolerance_area(clat, clon, area["radius"])
        if box["wraps"] or box["full_longitude"]:
            raise ValueError("the area must not cross the date line or reach a pole")
        north, west, south, east = box["north"], box["west"], box["south"], box["east"]
        margin = 0
    else:
        lats, lons = [p["lat"] for p in pts], [p["lon"] for p in pts]
        north, west, south, east, margin = max(lats), min(lons), min(lats), max(lons), 2
    mid = (north + south) / 2
    extent_x, extent_y = _place_meters(south, east, north, west, mid)
    cols, rows = int(extent_x // meters) + 1 + 2 * margin, int(extent_y // meters) + 1 + 2 * margin
    cols, rows = max(cols, 12), max(rows, 12)
    if cols * tile > 4096 or rows * tile > 4096:
        raise ValueError("the place fits in 4096 units: raise meters or lower tile")
    ox, oy = (cols - int(extent_x // meters) - 1) // 2, (rows - int(extent_y // meters) - 1) // 2    # centre the box on the grid
    def cell(lat: float, lon: float) -> tuple[int, int]:
        x, y = _place_meters(lat, lon, north, west, mid)
        return int(x // meters) + ox, int(y // meters) + oy
    def corner(lat: float, lon: float) -> tuple[int, int]:
        x, y = _place_meters(lat, lon, north, west, mid)
        return math.floor(x / meters + .5) + ox, math.floor(y / meters + .5) + oy
    signs = [p for p in pts if "sign" in p]
    pts = [p for p in pts if "sign" not in p]
    if not pts:
        raise ValueError("a place needs a point that is not a sign")
    for p in pts:
        p["cell"] = cell(p["lat"], p["lon"])
        if not (0 <= p["cell"][0] < cols and 0 <= p["cell"][1] < rows):
            raise ValueError(f"{p['id']} lies outside the area")
    for p in signs:
        p["corner"] = corner(p["lat"], p["lon"])
        if not (0 <= p["corner"][0] <= cols and 0 <= p["corner"][1] <= rows):
            raise ValueError(f"{p['id']} lies outside the area")
    water: set[tuple[int, int]] = set()
    rivers = list(rivers or ())
    for river in rivers:
        if not isinstance(river, dict) or set(river) != {"line", "width"} or not isinstance(river["line"], list) or not 2 <= len(river["line"]) <= 32:
            raise ValueError("a river is {line: [[lat, lon], ...] (2..32 points), width: tiles}")
        width_tiles = _bounded_int(river["width"], "width", 1, 8)
        line = [cell(*parse_coordinate(a, b)) for a, b in river["line"]]
        for (x0, y0), (x1, y1) in zip(line, line[1:]):
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for i in range(steps + 1):
                x, y = x0 + round((x1 - x0) * i / steps), y0 + round((y1 - y0) * i / steps)
                for dx in range(-(width_tiles // 2), width_tiles - width_tiles // 2):
                    for dy in range(-(width_tiles // 2), width_tiles - width_tiles // 2):
                        if 0 <= x + dx < cols and 0 <= y + dy < rows:
                            water.add((x + dx, y + dy))
    taken: set[tuple[int, int]] = set()
    for p in pts:                                                                        # one spot per tile, none in the water
        cx, cy = p["cell"]
        for ring in range(max(cols, rows)):
            near = sorted(((cx + dx, cy + dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1) if max(abs(dx), abs(dy)) == ring),
                          key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2, c[1], c[0]))
            free = [c for c in near if 0 <= c[0] < cols and 0 <= c[1] < rows and c not in taken and c not in water]
            if free:
                p["cell"] = free[0]
                break
        taken.add(p["cell"])
    touching = lambda c: [(x, y) for x, y in ((c[0] - 1, c[1] - 1), (c[0], c[1] - 1), (c[0] - 1, c[1]), c) if 0 <= x < cols and 0 <= y < rows]   # noqa: E731
    corners: set[tuple[int, int]] = set()
    for p in signs:                                                                      # one sign per corner, on dry land
        cx, cy = p["corner"]
        for ring in range(max(cols, rows) + 1):
            near = sorted(((cx + dx, cy + dy) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1) if max(abs(dx), abs(dy)) == ring),
                          key=lambda c: ((c[0] - cx) ** 2 + (c[1] - cy) ** 2, c[1], c[0]))
            free = [c for c in near if 0 <= c[0] <= cols and 0 <= c[1] <= rows and c not in corners and any(t not in water for t in touching(c))]
            if free:
                p["corner"] = free[0]
                break
        corners.add(p["corner"])
    by_id = {p["id"]: p for p in pts}
    if start is not None and start not in by_id:
        raise ValueError("start is the id of one of the points that is not a sign")
    road: set[tuple[int, int]] = set()
    if not isinstance(links, (list, tuple)) or len(links) > 128:
        raise ValueError("links is a list of up to 128 pairs of point ids")
    for pair in links:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2 or any(k not in by_id for k in pair) or pair[0] == pair[1]:
            raise ValueError("a link joins two different point ids of the place")
        (x0, y0), (x1, y1) = by_id[pair[0]]["cell"], by_id[pair[1]]["cell"]
        road |= {(x, y0) for x in range(min(x0, x1), max(x0, x1) + 1)} | {(x1, y) for y in range(min(y0, y1), max(y0, y1) + 1)}
    bridge = road & water
    prop, spot = _floor_kit(tile, id)
    props = [prop("grass", 0, 0, cols, rows)]
    for kind, cells in (("water", water), ("road", road - water), ("bridge", bridge)):               # roads after water: a bridge opens its tiles
        props += [prop(kind, *rect) for rect in _place_rects(cells)]
    if scatter is not None:
        if not isinstance(scatter, dict) or set(scatter) != {"kind", "every", "seed"} or scatter["kind"] not in WORLD_PROPS \
                or scatter["kind"] in WORLD_GROUND or WORLD_PROPS[scatter["kind"]]:
            raise ValueError("scatter is {kind: a decoration (not ground, not solid), every: tiles per block, seed}")
        every, state = _bounded_int(scatter["every"], "every", 2, 64), _bounded_int(scatter["seed"], "seed", 0, 2**31 - 1) % 2147483646 + 1
        used = water | road | {p["cell"] for p in pts}
        for by in range(0, rows, every):
            for bx in range(0, cols, every):
                free = [(x, y) for y in range(by, min(by + every, rows)) for x in range(bx, min(bx + every, cols)) if (x, y) not in used]
                state = state * 48271 % 2147483647                                              # Park-Miller, as land_floor
                if free:
                    props.append(prop(scatter["kind"], *free[int(state / 2147483647 * len(free))], 1, 1))
    if len(props) > 512:
        raise ValueError("the place has too many tiles of road, water and scatter: raise meters")
    first = by_id[start or pts[0]["id"]]
    reach = world_reach(world_blocked(cols * tile, rows * tile, tile, props), first["cell"])
    lost = [p["id"] for p in pts if p["cell"] not in reach] + [p["id"] for p in signs if not any(t in reach for t in touching(p["corner"]))]
    if lost:
        raise ValueError(f"cut off by water from {first['id']}: {', '.join(lost)} (add a link across the river)")
    if marks is not None and not (isinstance(marks, dict) and all(isinstance(k, str) and _WORLD_TOKEN.fullmatch(k) for k in marks)):
        raise ValueError("marks is {category: emoji}")
    marks = {k: _world_mark(v) for k, v in (marks or {}).items()}
    mark = lambda p: {"mark": p["mark"]} if "mark" in p else {"mark": marks[p["category"]]} if p["category"] in marks else {}   # noqa: E731
    if isinstance(always_named, str) or not all(isinstance(k, str) and _WORLD_TOKEN.fullmatch(k) for k in always_named):
        raise ValueError("always_named is a list of categories")
    group = [p["cell"][0] for p in pts if p["category"] in always_named]
    middle = sum(group) / len(group) if group else 0                                  # names hang away from the middle of their group, so two rows
    named = lambda p: ({"always_named": "left" if p["cell"][0] < middle else "right" if p["cell"][0] > middle else True}   # noqa: E731  (do not cover
                       if p["category"] in always_named else {})                                                          # each other)
    spots = [{"id": f"{id}-{p['id']}", "x": int((p["cell"][0] + .5) * tile), "y": int((p["cell"][1] + .5) * tile), "label": p["label"],
              "category": p["category"], "body": p["body"], **({"flip": p["flip"]} if "flip" in p else {}), **mark(p), **named(p)} for p in pts]
    spots += [{"id": f"{id}-{p['id']}", "x": p["corner"][0] * tile, "y": p["corner"][1] * tile, "label": p["label"], "category": p["category"],
               "body": p["body"], "sign": p["sign"], **({"flip": p["flip"]} if "flip" in p else {}), **mark(p)} for p in signs]
    return {"id": id, "label": label, "width": cols * tile, "height": rows * tile, "tile": tile, "props": props, "actors": [], "spots": spots,
            "player": {"emoji": "🙂", "x": int((first["cell"][0] + .5) * tile), "y": int((first["cell"][1] + .5) * tile), "speed": 96}}


def _shots_html(world: dict[str, Any]) -> str:
    wid, shots = world["id"], world["shots"]
    articles = "".join(
        f'<article class="ui-shot" data-i="{i}"><p class="ui-shot-hud">{escape(s["label"])} / {len(shots):02d}</p>'
        f'<h3>{escape(s["title"])}</h3><p>{escape(s["body"])}</p></article>' for i, s in enumerate(shots))
    marks = "".join(f'<div class="ui-shot-mark" data-i="{i}" style="--i:{i}"></div>' for i in range(len(shots)))
    return (f'<section class="ui-world ui-world-shots" id="{wid}-shots" data-ui-world="shots" style="--shots:{len(shots)}" '
            f'aria-label="{escape(world["title"], quote=True)}"><div class="ui-shots-scroll"><div class="ui-shots-track">'
            f'<div class="ui-shots-stage">{articles}</div>{marks}</div></div></section>')


def issue_bulletin_urls(target: str) -> tuple[str, str]:
    """Return anonymous read URL and native GitHub post link for an Issues bulletin."""
    if not isinstance(target, str) or (len(target.split("/")) == 3 and target.split("/")[1] in {".", ".."}) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}/[1-9][0-9]{0,8}", target):
        raise ValueError("shared_issue must be owner/repository/positive-issue-number")
    owner, repo, number = target.split("/")
    return (f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments?per_page=100",
            f"https://github.com/{owner}/{repo}/issues/{number}#new_comment_field")


def bulletin_html(post_url: str, *, title: str, notice: str, post_label: str) -> str:
    """Render a bulletin with a trusted HTTPS destination; never accept a feed URL here."""
    return _bulletin_html(post_url, title=title, notice=notice, post_label=post_label)


def _bulletin_html(post_url: str, *, title: str, notice: str, post_label: str, issue_api: str | None = None) -> str:
    if not isinstance(post_url, str) or any(ord(c) <= 32 or ord(c) == 127 or c == "\\" for c in post_url):
        raise ValueError("bulletin post URL must be an absolute HTTPS URL without credentials")
    parts = urlsplit(post_url)
    if parts.scheme != "https" or not parts.hostname or parts.username is not None:
        raise ValueError("bulletin post URL must be an absolute HTTPS URL without credentials")
    api_attr = f' data-api="{escape(issue_api, quote=True)}"' if issue_api else ""
    return (f'<details class="ui-board-shared"{api_attr}>'
            f'<summary>{escape(title)}</summary><p>{escape(notice)}</p>'
            f'<a href="{escape(post_url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(post_label)}</a> '
            '<button type="button" data-shared-refresh>共有コメントを取得・更新</button>'
            '<p role="status" data-shared-status>未取得。自動更新なし。更新間隔は最低120秒。</p>'
            '<ul data-shared-comments></ul></details>')


def issue_bulletin_html(target: str, *, extra_notice: str = "") -> str:
    """Render a public, GitHub-posted bulletin independent of any World."""
    api_url, post_url = issue_bulletin_urls(target)
    return _bulletin_html(
        post_url, title="共有掲示板（GitHub公開コメント）",
        notice="投稿はGitHubへのログインが必要です。本文・アカウント名・投稿時刻はインターネットに公開されます。"
               "個人情報や秘密の待ち合わせ情報は書かないでください。" + extra_notice,
        post_label="GitHubで公開投稿（別タブ）", issue_api=api_url,
    )


def _board_html(board: dict[str, Any] | None, *, timed: bool = True) -> str:
    """The info board: a clock (``HH:MM:SS``) and a constant-speed scrolling line; items with ``at`` get "in N min" from the page's clock.
    ``timed=False`` leaves the lap time off the markup (no ``style`` attribute, for a page whose CSP refuses them): the script sets it."""
    if not board:
        return ""
    def item(entry: dict[str, Any], hidden: bool) -> str:
        extra, where = "", f' data-zone="{entry["zone"]}"' if entry["zone"] else ""
        if entry["at"]:
            extra = f' <span class="ui-board-min" data-at="{entry["at"]}"{where}></span>'
        elif entry["gauge"]:
            g = entry["gauge"]
            done, todo = (escape(glyph, quote=True) for glyph in g["glyphs"])
            extra = (f' <span class="ui-board-gauge" data-from="{g["from"]}" data-to="{g["to"]}" data-cells="{g["cells"]}"{where} '
                     f'data-done="{done}" data-todo="{todo}"><span class="ui-board-cells" aria-hidden="true">'
                     f'{escape(gauge_cells(0, g["cells"], g["glyphs"]))}</span> <span class="ui-board-pct">0%</span></span>')
        aria_hidden = ' aria-hidden="true"' if hidden else ""
        return f'<span class="ui-board-item"{aria_hidden}>{escape(entry["text"])}{extra}</span>'
    def item_chars(entry: dict[str, Any]) -> int:
        # Budget the longest cell combination and percentage, including separators.
        gauge = entry["gauge"]
        extra = 10 if entry["at"] else 0
        if gauge:
            extra += 1 + max(len(gauge_cells(n, gauge["cells"], gauge["glyphs"]))
                             for n in range(gauge["cells"] + 1)) + len(" 100%")
        return len(entry["text"]) + extra
    chars = sum(item_chars(entry) for entry in board["items"])
    run = "".join(item(e, False) for e in board["items"]) + "".join(item(e, True) for e in board["items"])
    form = ('<form class="ui-board-post"><input class="ui-input" name="message" maxlength="60" placeholder="Leave a line" '
            'aria-label="Leave a line on the board" autocomplete="off"><button class="ui-button" type="submit">Post</button></form>'
            if board["post"] else "")
    shared = (issue_bulletin_html(board["shared_issue"], extra_notice="ページ内Postはこのページだけで、共有されません。")
              if board.get("shared_issue") else "")
    label = " data-offset-label" if board["offset_label"] else ""
    chips = "".join(f'<span class="ui-board-zone" data-zone-id="{z["id"]}" data-rows="{json.dumps(list(zone_rows(z["tz"])), separators=(",", ":"))}">'
                    f'{escape(z["label"])} <b data-zone-clock>--:--</b></span>' for z in board["zones"])
    chips = f'<span class="ui-board-zones">{chips}</span>' if chips else ""
    offset = board["offset_minutes"] if board["offset_minutes"] is not None else ""
    duration_style = f' style="animation-duration:{board_seconds(chars)}s"' if timed else ""
    return (f'<div class="ui-board" aria-live="off" data-offset="{offset}" data-chars="{chars}"{label}><strong>{escape(board["title"])}</strong><span class="ui-board-clock" data-clock>--:--:--</span>{chips}'
            f'<div class="ui-board-track"><div class="ui-board-run"{duration_style}>{run}</div></div>{form}{shared}</div>')


# The words of a shell world's chrome that are the world's own. The page shows icons; these are the aria-label and tooltip. 🌐 picks the
# language, PySaiyanWeBoo's eleven (CHROME_LANGS; ja is the page's own, so it is what the markup carries until JS switches it), and the
# words a tool page's chrome shares (🏠 ⭐ ⚙️ 🌐 ☰ ⋯, 🫧 🚪 📦, "in N min") are PySaiyanWeBoo's catalogue (chrome_word): written once.
WORLD_NAMES = ("names", "dots", "off")   # the name layer of a map: see docs/world-classroom.md "Layers"
WORLD_TEXT = {
    #            ja  en  fr  es  pt  ar  zh  ru  id  de  sw
    "avatar": ("絵文字を変える", "Change emoji", "Changer d'emoji", "Cambiar emoji", "Mudar emoji", "تغيير الرمز التعبيري", "更换表情", "Сменить эмодзи", "Ganti emoji", "Emoji ändern", "Badilisha emoji"),
    "zoom": ("ズーム（回して拡大・縮小）", "Zoom (turn to zoom in or out)", "Zoom (tournez pour agrandir ou réduire)", "Zoom (gira para acercar o alejar)",
             "Zoom (gire para aproximar ou afastar)", "التكبير (أدر للتكبير أو التصغير)", "缩放（旋转以放大或缩小）", "Масштаб (поверните, чтобы приблизить или отдалить)",
             "Zum (putar untuk memperbesar atau memperkecil)", "Zoom (drehen zum Vergrößern oder Verkleinern)", "Kuza (zungusha kukuza au kupunguza)"),
    "overlay": ("地図の上の操作類の透け具合", "How see-through the controls over the map are", "Transparence des commandes sur la carte", "Transparencia de los controles sobre el mapa",
                "Transparência dos controles sobre o mapa", "شفافية عناصر التحكم فوق الخريطة", "地图上控件的透明度", "Прозрачность элементов управления над картой",
                "Transparansi kontrol di atas peta", "Durchsichtigkeit der Bedienelemente über der Karte", "Uwazi wa vidhibiti juu ya ramani"),
    "names": ("名前の層: 🏷️ 名前 / ● 点（近く・指先で名前） / ✖️ 点だけ", "Name layer: 🏷️ names / ● dots (names near you or under the pointer) / ✖️ dots only",
              "Couche des noms : 🏷️ noms / ● points (noms près de vous ou sous le pointeur) / ✖️ points seulement",
              "Capa de nombres: 🏷️ nombres / ● puntos (nombres cerca de ti o bajo el puntero) / ✖️ solo puntos",
              "Camada de nomes: 🏷️ nomes / ● pontos (nomes perto de você ou sob o ponteiro) / ✖️ só pontos",
              "طبقة الأسماء: 🏷️ أسماء / ● نقاط (الأسماء قربك أو تحت المؤشر) / ✖️ نقاط فقط",
              "名称层：🏷️ 名称 / ● 圆点（靠近或指向时显示名称） / ✖️ 仅圆点", "Слой имён: 🏷️ имена / ● точки (имена рядом или под указателем) / ✖️ только точки",
              "Lapisan nama: 🏷️ nama / ● titik (nama di dekatmu atau di bawah penunjuk) / ✖️ titik saja",
              "Namensebene: 🏷️ Namen / ● Punkte (Namen nahe bei dir oder unter dem Zeiger) / ✖️ nur Punkte",
              "Tabaka ya majina: 🏷️ majina / ● nukta (majina karibu nawe au chini ya kielekezi) / ✖️ nukta tu"),
    "me": ("自分の場所", "Find me", "Où suis-je", "Mi ubicación", "Minha posição", "موقعي", "我的位置", "Где я", "Posisi saya", "Mein Standort", "Nilipo"),
    "walk": ("ここへ歩く", "Walk here", "Aller ici", "Caminar aquí", "Caminhar até aqui", "امشِ إلى هنا", "走到这里", "Идти сюда", "Jalan ke sini", "Hierhin gehen", "Tembea hapa"),
    "close": ("閉じる", "Close", "Fermer", "Cerrar", "Fechar", "إغلاق", "关闭", "Закрыть", "Tutup", "Schließen", "Funga"),
    "floor": ("フロアを移動", "Go to floor", "Aller à l'étage", "Ir a la planta", "Ir para o andar", "الانتقال إلى طابق", "前往楼层", "Перейти на этаж", "Pindah lantai", "Zur Etage", "Nenda ghorofa"),
    "move": ("移動", "Move", "Déplacer", "Mover", "Mover", "تحرك", "移动", "Движение", "Gerak", "Bewegen", "Sogea"),
    "left": ("左へ", "Left", "Gauche", "Izquierda", "Esquerda", "يسار", "左", "Влево", "Kiri", "Links", "Kushoto"),
    "right": ("右へ", "Right", "Droite", "Derecha", "Direita", "يمين", "右", "Вправо", "Kanan", "Rechts", "Kulia"),
    "pick": ("あなたの絵文字をえらんでください", "Pick your emoji", "Choisissez votre emoji", "Elige tu emoji", "Escolha seu emoji", "اختر رمزك التعبيري", "选择你的表情", "Выберите свой эмодзи", "Pilih emojimu", "Wähle dein Emoji", "Chagua emoji yako"),
    "other": ("ほかの絵文字・文字（16文字まで）", "Another emoji or text (up to 16)", "Autre emoji ou texte (16 max)", "Otro emoji o texto (hasta 16)", "Outro emoji ou texto (até 16)", "رمز أو نص آخر (حتى 16)", "其他表情或文字（最多16个）", "Другой эмодзи или текст (до 16)", "Emoji atau teks lain (maks. 16)", "Anderes Emoji oder Text (bis 16)", "Emoji au maandishi mengine (hadi 16)"),
    "ok": ("これにする", "Use this", "Choisir", "Usar este", "Usar este", "استخدم هذا", "就用这个", "Выбрать", "Pakai ini", "Nehmen", "Tumia hii"),
    "invalid": ("1〜16文字の絵文字か文字を入力してください", "Enter 1 to 16 emoji or characters", "Saisissez 1 à 16 emoji ou caractères", "Escribe de 1 a 16 emoji o caracteres", "Digite de 1 a 16 emoji ou caracteres", "أدخل من 1 إلى 16 رمزًا أو حرفًا", "请输入1到16个表情或文字", "Введите от 1 до 16 эмодзи или символов", "Masukkan 1 sampai 16 emoji atau karakter", "Gib 1 bis 16 Emoji oder Zeichen ein", "Weka emoji au herufi 1 hadi 16"),
    "backdrop": ("写真かカメラをうしろに映す", "Show a photo or the camera behind", "Afficher une photo ou la caméra derrière", "Mostrar una foto o la cámara detrás", "Mostrar uma foto ou a câmera atrás", "عرض صورة أو الكاميرا في الخلفية", "在背后显示照片或相机", "Показать фото или камеру на фоне", "Tampilkan foto atau kamera di belakang", "Foto oder Kamera dahinter zeigen", "Onyesha picha au kamera nyuma"),
    "camera": ("カメラ", "Camera", "Caméra", "Cámara", "Câmera", "الكاميرا", "相机", "Камера", "Kamera", "Kamera", "Kamera"),
    "photo": ("写真をえらぶ", "Choose a photo", "Choisir une photo", "Elegir una foto", "Escolher uma foto", "اختر صورة", "选择照片", "Выбрать фото", "Pilih foto", "Foto wählen", "Chagua picha"),
    "clear": ("もとにもどす", "Clear it", "Effacer", "Quitar", "Remover", "مسح", "清除", "Убрать", "Hapus", "Entfernen", "Ondoa"),
    "unavailable": ("つかえません（許可かカメラを確認）", "Not available (check permission or camera)", "Indisponible (vérifiez l'autorisation ou la caméra)", "No disponible (revisa el permiso o la cámara)", "Indisponível (verifique a permissão ou a câmera)", "غير متاح (تحقق من الإذن أو الكاميرا)", "无法使用（请检查权限或相机）", "Недоступно (проверьте разрешение или камеру)", "Tidak tersedia (periksa izin atau kamera)", "Nicht verfügbar (Berechtigung oder Kamera prüfen)", "Haipatikani (angalia ruhusa au kamera)"),
    "bag": ("どうぐ", "Bag", "Sac", "Bolsa", "Bolsa", "الحقيبة", "道具", "Сумка", "Tas", "Tasche", "Mkoba"),
    "take": ("どうぐに出し入れする", "Add or remove item", "Ajouter ou retirer l'objet", "Añadir o quitar objeto", "Adicionar ou remover item", "إضافة أو إزالة أداة", "放入或取出道具", "Добавить или убрать предмет", "Tambah atau hapus barang", "Gegenstand hinzufügen oder entfernen", "Ongeza au ondoa kifaa"),
    # 🌐 the words of the shell and the scenes' buttons that 🌐 finds by their words (sayIn), and those of the site's parts on a world page
    "self": ("自分", "Me", "Moi", "Yo", "Eu", "أنا", "我", "Я", "Saya", "Ich", "Mimi"),
    "world": ("ワールド", "World", "Monde", "Mundo", "Mundo", "العالم", "世界", "Мир", "Dunia", "Welt", "Ulimwengu"),
    "spaces": ("空間一覧", "Spaces", "Espaces", "Espacios", "Espaços", "المساحات", "空间列表", "Пространства", "Ruang", "Räume", "Nafasi"),
    "adventure": ("冒険ステータス", "Adventure status", "Statut d'aventure", "Estado de la aventura", "Status da aventura", "حالة المغامرة", "冒险状态", "Статус приключения", "Status petualangan", "Abenteuerstatus", "Hali ya safari"),
    "notebook": ("冒険手帳（クエスト・実績・図鑑）", "Adventure notebook (quests, achievements, field guide)", "Carnet d'aventure (quêtes, succès, bestiaire)", "Cuaderno de aventura (misiones, logros, guía)", "Caderno de aventura (missões, conquistas, guia)", "دفتر المغامرة (المهام والإنجازات والدليل)", "冒险手册（任务、成就、图鉴）", "Дневник приключений (квесты, достижения, справочник)", "Buku petualangan (misi, pencapaian, ensiklopedia)", "Abenteuerbuch (Quests, Erfolge, Lexikon)", "Daftari la safari (kazi, mafanikio, viumbe)"),
    "hunt": ("この周辺で魔物をさがす", "Look for monsters nearby", "Chercher des monstres alentour", "Buscar monstruos cerca", "Procurar monstros por perto", "ابحث عن الوحوش القريبة", "在附近寻找怪物", "Искать монстров рядом", "Cari monster di sekitar", "Monster in der Nähe suchen", "Tafuta majini karibu"),
    "cat": ("散歩猫", "Strolling cat", "Chat en balade", "Gato paseando", "Gato passeando", "قطة تتنزه", "散步的猫", "Гуляющий кот", "Kucing jalan-jalan", "Spazierkatze", "Paka anayetembea"),
    "watchdog": ("村の番犬", "Village watchdog", "Chien de garde du village", "Perro guardián del pueblo", "Cão de guarda da vila", "كلب حراسة القرية", "村里的看门狗", "Сторожевой пёс деревни", "Anjing penjaga desa", "Dorfwachhund", "Mbwa mlinzi wa kijiji"),
    "pigeon": ("伝令バト", "Messenger pigeon", "Pigeon messager", "Paloma mensajera", "Pombo-correio", "حمامة زاجلة", "信鸽", "Почтовый голубь", "Merpati pos", "Brieftaube", "Njiwa mjumbe"),
    "child": ("こども", "Child", "Enfant", "Niño", "Criança", "طفل", "孩子", "Ребёнок", "Anak", "Kind", "Mtoto"),
    "dog": ("いぬ", "Dog", "Chien", "Perro", "Cão", "كلب", "狗", "Собака", "Anjing", "Hund", "Mbwa"),
    "bird": ("とり", "Bird", "Oiseau", "Pájaro", "Pássaro", "طائر", "鸟", "Птица", "Burung", "Vogel", "Ndege"),
    "pet": ("ドラゴンをなでる", "Pet the dragon", "Caresser le dragon", "Acariciar al dragón", "Acariciar o dragão", "داعب التنين", "抚摸龙", "Погладить дракона", "Elus naga", "Den Drachen streicheln", "Mpapase joka"),
    "hue": ("ドラゴンの体色", "Dragon's color", "Couleur du dragon", "Color del dragón", "Cor do dragão", "لون التنين", "龙的颜色", "Цвет дракона", "Warna naga", "Farbe des Drachen", "Rangi ya joka"),
    "fill": ("背景の塗りつぶし", "Background fill", "Remplissage du fond", "Relleno del fondo", "Preenchimento do fundo", "تعبئة الخلفية", "背景填充", "Заливка фона", "Isi latar", "Hintergrundfüllung", "Ujazo wa mandhari"),
    "talk": ("話しかける", "Talk to it", "Lui parler", "Hablarle", "Falar com ele", "تحدّث إليه", "和它聊聊", "Поговорить", "Ajak bicara", "Ansprechen", "Zungumza nayo"),
    "ask": ("何を聞いてみる？", "What will you ask?", "Que voulez-vous demander ?", "¿Qué quieres preguntar?", "O que você quer perguntar?", "ماذا تريد أن تسأل؟", "想问什么？", "О чём спросить?", "Mau tanya apa?", "Was möchtest du fragen?", "Ungependa kuuliza nini?"),
    "scroll": ("竜の巻物", "Dragon scroll", "Parchemin du dragon", "Pergamino del dragón", "Pergaminho do dragão", "لفيفة التنين", "龙之卷轴", "Свиток дракона", "Gulungan naga", "Drachenschriftrolle", "Hati-kunjo ya joka"),
    "tools": ("道具", "Tools", "Outils", "Herramientas", "Ferramentas", "أدوات", "工具", "Инструменты", "Alat", "Werkzeuge", "Zana"),
    "guide": ("攻略ガイド", "Strategy guide", "Guide stratégique", "Guía de estrategia", "Guia de estratégia", "دليل الاستراتيجية", "攻略指南", "Руководство", "Panduan strategi", "Lösungshilfe", "Mwongozo wa mbinu"),
    "nothing": ("まだありません", "Nothing yet", "Rien pour l'instant", "Nada todavía", "Nada ainda", "لا شيء بعد", "还没有", "Пока ничего", "Belum ada", "Noch nichts", "Bado hakuna"),
    "effect": ("効果", "Effect", "Effet", "Efecto", "Efeito", "التأثير", "效果", "Эффект", "Efek", "Wirkung", "Athari"),
    "village": ("村", "Village", "Village", "Pueblo", "Vila", "القرية", "村庄", "Деревня", "Desa", "Dorf", "Kijiji"),
    "school": ("学校", "School", "École", "Escuela", "Escola", "المدرسة", "学校", "Школа", "Sekolah", "Schule", "Shule"),
    "tokyo": ("パラレル東京", "Parallel Tokyo", "Tokyo parallèle", "Tokio paralelo", "Tóquio paralela", "طوكيو الموازية", "平行东京", "Параллельный Токио", "Tokyo Paralel", "Paralleles Tokio", "Tokyo sambamba"),
}
WORLD_BUILTIN_TOOLS = ("🏠", "⭐", "🎒", "⚙", "🌐", "☰", "⋯", "🛗", "🚪", "🖼", "📷", "🧹")   # emoji the page itself uses (🛗 its floors; 🚪 is the site foot's); a tool of your own takes another
_WORLD_TOOL_KEYS = {"label", "label_en", "labels", "slot"}
_WORLD_LANG_CODES = tuple(code for code, _ in CHROME_LANGS)


def _plain_emoji(value: str) -> str:
    return value.replace("\ufe0e", "").replace("\ufe0f", "")


def _wt(key: str, labels: dict[str, str] | None = None) -> str:
    """aria-label and title of one word of the chrome in the page's own language (ja); ``data-t`` names the catalogue entry that 🌐 swaps in,
    or ``labels`` (language code → words) carries the words of a tool of your own."""
    ja = labels["ja"] if labels else WORLD_TEXT[key][0] if key in WORLD_TEXT else chrome_word(key)
    swap = f'data-labels="{escape(json.dumps(labels, ensure_ascii=False, separators=(",", ":")), quote=True)}"' if labels else f'data-t="{key}"'
    return f'aria-label="{escape(ja, quote=True)}" title="{escape(ja, quote=True)}" {swap}'


def _world_shell(world: dict[str, Any]) -> bool:
    """Header, side and footer instead of chips on top and controls below: every grid world, or any world with ``"shell": true``."""
    return bool(world.get("shell") or world.get("tools") or any(f.get("tile") or f.get("real") for f in world["floors"]))


def _world_categories(floors: list[dict[str, Any]]) -> list[str]:
    """The category tokens the spots use, sorted (the filter chips and the radios behind them)."""
    return sorted({s["category"] for f in floors for s in f["spots"] if s["category"]})


def _world_playable(world: dict[str, Any]) -> bool:
    """Something moves (a board, a player or an actor), so the page gets its motion controls."""
    return bool(world["board"] or any(f["player"] or f["actors"] for f in world["floors"]))


def _floor_html(wid: str, f: dict[str, Any], close: str, *, confirm: bool = False, rpg: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """One floor's stage (props, spots, actors, player) and the info sheet articles of its spots and actors (``close`` is their closing link)."""
    flip = lambda s: (f' data-flip="{escape(s["flip"], quote=True)}"' if s.get("flip") else "") + (f' data-sign="{s["sign"]}"' if s.get("sign") else "") + (f' data-named="{"" if s["always_named"] is True else s["always_named"]}"' if s.get("always_named") else "")   # noqa: E731
    mark = lambda s: f';--mark:\'{escape(s["mark"], quote=True)}\'' if s.get("mark") else ""   # noqa: E731  (the dot's replacement, read by CSS content)
    def rpg_kind(sid: str) -> str:
        if not rpg:
            return ""
        if sid in rpg["enemies"]:
            return ' data-rpg-kind="enemy"'
        if sid in rpg["loot"]:
            return f' data-rpg-kind="{rpg["loot"][sid]["kind"]}"'
        if sid in rpg["npcs"]:
            return ' data-rpg-kind="npc"'
        return ""
    spots = "".join(
        f'<a class="ui-spot" href="#{wid}-spot-{s["id"]}" data-x="{s["x"]}" data-y="{s["y"]}" data-category="{s["category"]}"'
        f'{rpg_kind(s["id"])} style="left:{s["x"]}px;top:{s["y"]}px{mark(s)}"{flip(s)}>{escape(s["label"])}</a>' for s in f["spots"])
    actors = "".join(
        f'<a class="ui-actor" id="{wid}-actor-{a["id"]}" href="#{wid}-spot-{a["id"]}"{rpg_kind(a["id"])} aria-label="{escape(a["label"], quote=True)}">'
        f'<span>{escape(a["emoji"])}</span></a>' for a in f["actors"])
    pl = f["player"]
    player = (f'<span class="ui-player" data-x="{pl["x"]}" data-y="{pl["y"]}" data-speed="{pl["speed"]}" '
              f'style="--px:{pl["x"]};--py:{pl["y"]}" role="img" aria-label="自分" data-t="self"><span>{escape(pl["emoji"])}</span></span>') if pl else ""
    tile = f.get("tile")
    props = "".join(f'<div class="ui-prop" data-kind="{q["kind"]}" aria-hidden="true" '
                    f'style="left:{q["x"]}px;top:{q["y"]}px;width:{q["w"]}px;height:{q["h"]}px"></div>' for q in f.get("props", []))
    grid = (f' data-tile="{tile}" data-blocked="{",".join(world_blocked(f["width"], f["height"], tile, f["props"]))}"') if tile else ""
    stage = (f'<div class="ui-floor" data-floor="{f["id"]}" data-w="{f["width"]}" data-h="{f["height"]}"{grid}{" data-real" if f.get("real") else ""} '
             f'style="width:{f["width"]}px;height:{f["height"]}px{f";--tile:{tile}px" if tile else ""}">{props}{spots}{actors}{player}</div>')
    def take(s: dict[str, Any]) -> str:
        item = s.get("item")
        if not item:
            return ""
        note = f'{escape(item["emoji"])} {escape(item["label"])}' + (f': {escape(item["body"])}' if item["body"] else "")
        return (f'<p class="ui-world-item-note">{note}</p>'
                f'<button type="button" class="ui-world-take" data-item-id="{wid}-spot-{s["id"]}" '
                f'data-item-emoji="{escape(item["emoji"], quote=True)}" data-item-label="{escape(item["label"], quote=True)}" '
                f'aria-pressed="false" hidden {_wt("take")}>{escape(item["emoji"])} <span class="ui-world-take-mark" aria-hidden="true">＋</span></button>')
    def go_btn(s: dict[str, Any]) -> str:
        if not (confirm and pl and "x" in s and "y" in s):
            return ""
        return (f'<button type="button" class="ui-world-go" data-go-floor="{f["id"]}" '
                f'data-go-x="{s["x"]}" data-go-y="{s["y"]}" hidden {_wt("walk")}>🚶</button>')
    sheet = [f'<article class="ui-sheet-item" id="{wid}-spot-{s["id"]}"><h3>{escape(s["label"])}</h3><p>{escape(s["body"])}</p>{take(s)}{go_btn(s)}{close}</article>'
             for s in [*f["spots"], *f["actors"]]]
    return stage, sheet


def _pick_html(wid: str, avatars: list[str], shell: bool) -> str:
    """The emoji picker (a plain ``div`` in the map, shown by the script): words for a classic world, icons and aria-labels for a shell world."""
    if not avatars:
        return ""
    grid = '<div class="ui-world-pick-grid">' + "".join(f'<button type="button" data-emoji="{escape(e, quote=True)}">{escape(e)}</button>' for e in avatars) + '</div>'
    if shell:
        return (f'<div class="ui-world-pick" role="group" {_wt("pick")} hidden><div><h3 aria-hidden="true">🙂👇</h3>{grid}'
                '<form class="ui-world-pick-form"><label><span aria-hidden="true">✏️</span> <input name="emoji" maxlength="32" size="8" autocomplete="off" '
                f'placeholder="🙂 A" {_wt("other")}></label><button {_wt("ok")}>✅</button></form></div></div>')
    return (f'<div class="ui-world-pick" role="group" aria-labelledby="{wid}-pick" hidden><div><h3 id="{wid}-pick">あなたの絵文字をえらんでください</h3>{grid}'
            '<form class="ui-world-pick-form"><label>ほかの絵文字・文字 <input name="emoji" maxlength="32" size="8" autocomplete="off" placeholder="16文字まで"></label>'
            '<button>これにする</button></form></div></div>')


def _classic_html(world: dict[str, Any], *, head: str, radios: str, labels: str, view: str, tail: str) -> str:
    """A world without a grid, tools or ``shell``: chips on top, the map, the controls below (the markup older worlds keep)."""
    extra = '<button type="button" data-pick-open>絵文字を変える</button>' if world.get("avatars") else ""
    controls = ('<div class="ui-world-motion-controls" hidden><button type="button" class="ui-world-pause" aria-pressed="false">動きを停止</button>'
                '<form class="ui-world-walk"><label>X <input name="x" type="number" min="0" step="any" required></label>'
                f'<label>Y <input name="y" type="number" min="0" step="any" required></label><button>ここへ歩く</button></form>{extra}</div>'
                if _world_playable(world) else "")
    return f'{head}{radios}<nav class="ui-world-bar">{labels}</nav>{_board_html(world["board"])}{view}{controls}{tail}'


def _menu_html(kind: str, glyph: str, attrs: str, panel: str, hidden: bool = False) -> str:
    """One 48px button whose panel opens over the page: ☰ ⋯ ⭐ ⚙️ and any emoji of your own (``hidden`` until the script shows it)."""
    return (f'<details class="ui-world-menu" data-menu="{kind}"{" hidden" if hidden else ""}><summary {attrs}>{glyph}</summary>'
            f'<div class="ui-world-panel">{panel}</div></details>')


def _tool_html(emoji: str, tool: dict[str, Any], *, wid: str = "", spot_rows: Callable[[list[str]], str] | None = None) -> str:
    """An emoji of your own (``tools_validate``): a floor shortcut or a link is the button itself, the other kinds open a panel."""
    attrs = _wt("", {"ja": tool["label"], "en": tool["label_en"], **tool.get("labels", {})})
    if "floor" in tool:                                                       # a floor shortcut: its radio, so it works without JS too
        return f'<label class="ui-world-tool" for="{wid}-floor-{tool["floor"]}" {attrs}>{escape(emoji)}</label>'
    if "href" in tool:
        return f'<a class="ui-world-tool" href="{escape(tool["href"], quote=True)}" {attrs}>{escape(emoji)}</a>'
    if "spots" in tool:
        panel = spot_rows(tool["spots"])
    elif "links" in tool:
        panel = '<ul class="ui-world-rows">' + "".join(
            f'<li><a href="{escape(l["href"], quote=True)}">{escape(l["label"])}</a></li>' for l in tool["links"]) + '</ul>'
    else:
        panel = f'<p>{escape(tool["body"])}</p>'
    return _menu_html("tool", escape(emoji), attrs, panel)


def _rpg_hud_html(rpg: dict[str, Any] | None) -> str:
    """Compact RPG status bar for worlds with ``rpg`` (hidden until script binds)."""
    if not rpg:
        return ""
    hero = rpg["hero"]
    total_q = len(rpg["quests"])
    return (
        '<div class="ui-rpg-hud" hidden aria-label="冒険ステータス">'
        '<span class="ui-rpg-stat ui-rpg-hero" data-rpg-hero>🧙 Lv.1</span>'
        f'<span class="ui-rpg-stat ui-rpg-hp" data-rpg-hp-wrap><span class="ui-rpg-meter"><i data-rpg-hp-bar style="width:100%"></i></span><b data-rpg-hp>❤️ {hero["hp"]}/{hero["hp"]}</b></span>'
        f'<span class="ui-rpg-stat ui-rpg-mp" data-rpg-mp-wrap><span class="ui-rpg-meter ui-rpg-meter-mp"><i data-rpg-mp-bar style="width:100%"></i></span><b data-rpg-mp>💧 {hero["mp"]}/{hero["mp"]}</b></span>'
        f'<span class="ui-rpg-stat" data-rpg-exp>✨ 0/30</span>'
        f'<span class="ui-rpg-stat" data-rpg-gold>🪙 {hero["gold"]}G</span>'
        f'<span class="ui-rpg-stat" data-rpg-gear>⚔️ {hero["atk"]} 🛡️ {hero["def"]}</span>'
        f'<button type="button" class="ui-rpg-pill" data-rpg-journal-btn aria-label="冒険手帳（クエスト・実績・図鑑）">📜 <span data-rpg-qcount>0/{total_q}</span></button>'
        '<button type="button" class="ui-rpg-pill" data-rpg-explore aria-label="この周辺で魔物をさがす">⚔️ 探索</button>'
        '</div>'
    )


def _shell_html(world: dict[str, Any], *, head: str, radios: str, view: str, tail: str, floor_labels: str, embedded: bool) -> str:
    """A shell world keeps the page short and says it with icons (the words are the aria-label and title, in 11 languages):

    header  the board and the tools of the whole world: 🏠 home, ⭐ favourites, ⚙️ settings, and any emoji of your own (``tools``)
    side    ☰ the places of this floor, ⋯ the controls of this screen; 48px buttons whose panel opens over the map
    footer  🛗 the pulldown that moves between floors (plain floor labels stand in for it until JS runs)
    """
    wid, floors, avatars, tools = world["id"], world["floors"], world.get("avatars", []), world.get("tools", {})
    categories, playable, tiled = _world_categories(floors), _world_playable(world), any(f.get("tile") for f in floors)
    icon = _menu_html
    on_floor = {sp["id"]: f["id"] for f in floors for sp in f["spots"]}
    def rows(ul_class: str, spots: list[dict[str, Any]], star: bool = False, data: str = "") -> str:
        return f'<ul class="ui-world-rows {ul_class}"{data}>' + "".join(
            f'<li data-category="{sp["category"]}"><a href="#{wid}-spot-{sp["id"]}" data-x="{sp["x"]}" data-y="{sp["y"]}" data-floor="{on_floor[sp["id"]]}">'
            f'<span class="ui-world-arrow" aria-hidden="true">{WORLD_HERE}</span>{escape(sp["label"])}</a>'
            + (f'<button type="button" class="ui-world-star" aria-pressed="false" {_wt("star")}>☆</button>' if star else "") + '</li>' for sp in spots) + '</ul>'
    by_id = {sp["id"]: sp for f in floors for sp in f["spots"]}
    def custom(emoji: str, tool: dict[str, Any]) -> str:
        return _tool_html(emoji, tool, wid=wid, spot_rows=lambda ids: rows("", [by_id[i] for i in ids]))
    chips = ("".join(f'<label for="{wid}-cat-{"value-" + c if c else "all"}" data-cat="{c}">{escape(c or "all")}</label>' for c in ["", *categories])
             if categories else "")
    side = icon("spots", "📍" if embedded else "☰", _wt("places"), (f'<nav class="ui-world-chips">{chips}</nav>' if chips else "") +
                "".join(rows("ui-world-spots", f["spots"], star=True, data=f' data-floor="{f["id"]}"') for f in floors))
    side += "".join(custom(e, t) for e, t in tools.items() if t["slot"] == "side")
    real = any(f.get("real") for f in floors)
    if playable or real:
        me = f'<button type="button" class="ui-world-grid-only" data-me hidden {_wt("me")}>🎯</button>' if tiled else ""
        walk = ('<div class="ui-world-motion-controls" hidden><form class="ui-world-walk"><label>X <input name="x" type="number" min="0" step="any" required></label>'
                f'<label>Y <input name="y" type="number" min="0" step="any" required></label><button {_wt("walk")}>🚶</button></form>{me}</div>') if playable else ""
        backdrop = f'<button type="button" class="ui-world-real" data-real hidden {_wt("backdrop")}>🖼️📷</button>' if real else ""
        side += icon("more", "⋯", _wt("screen"), walk + backdrop, hidden=True)
    settings = ((f'<button type="button" class="ui-world-pause" aria-pressed="false" data-pause="⏸️" data-resume="▶️" {_wt("pause")}>⏸️</button>' if playable else "") +
                (f'<button type="button" data-pick-open {_wt("avatar")}>🙂✏️</button>' if avatars else "") +
                f'<label class="ui-world-lang">🌐 <select data-lang {_wt("language")}>' +
                "".join(f'<option value="{code}" lang="{code}"{" selected" if i == 0 else ""}>{name}</option>' for i, (code, name) in enumerate(CHROME_LANGS)) +
                '</select></label>' +
                f'<label class="ui-world-zoom">🔍 {dial_html("zoom", minimum=0.1, maximum=world["zoom_max"], step=0.05, value=1, attrs=_wt("zoom"))}</label>' +
                f'<label class="ui-world-alpha">🫥 <input type="range" data-alpha min="0.2" max="1" step="0.1" value="0.9" {_wt("overlay")}></label>' +
                (f'<label class="ui-world-names">🏷️ <select data-names-pick {_wt("names")}>' +
                 "".join(f'<option value="{v}"{" selected" if v == world["names"] else ""}>{t}</option>' for v, t in zip(WORLD_NAMES, ("🏷️", "●", "✖️"))) +
                 '</select></label>' if any(f["spots"] for f in floors) else ""))
    bag = (icon("bag", "🎒", _wt("bag"), '<p class="ui-world-empty" aria-hidden="true">🎒</p><ul class="ui-world-rows ui-world-bag"></ul>', hidden=True)
           if any("item" in s for f in floors for s in f["spots"]) else "")
    header_tools = (f'<a class="ui-world-home" href="#{wid}-map" data-home {_wt("home")}>🏠</a>' +
                    "".join(custom(e, t) for e, t in tools.items() if t["slot"] == "head") +
                    icon("favorites", "⭐", _wt("favorites"), '<p class="ui-world-empty" aria-hidden="true">☆</p><ul class="ui-world-rows ui-world-favs"></ul>', hidden=True) +
                    bag +
                    icon("settings", "⚙️", _wt("settings"), settings, hidden=True))
    steps = "".join(f'<button type="button" data-step="{d}" {_wt(k)}>{g}</button>'
                    for d, k, g in (("0,-1", "up", "▲"), ("-1,0", "left", "◀"), ("1,0", "right", "▶"), ("0,1", "down", "▼")))
    dpad = f'<div class="ui-world-dpad ui-world-grid-only" role="group" data-overlay {_wt("move")} hidden>{steps}</div>' if tiled and playable else ""
    foot = (f'<footer class="ui-world-foot"><nav class="ui-world-bar">{floor_labels}</nav>'
            f'<label class="ui-world-goto-wrap">🛗 <select class="ui-world-goto" {_wt("floor")}>' +
            "".join(f'<option value="{f["id"]}"{" selected" if i == 0 else ""}>{escape(f["label"])}</option>' for i, f in enumerate(floors)) +
            '</select></label></footer>') if len(floors) > 1 else ""
    rpg_hud = _rpg_hud_html(world.get("rpg"))
    toolbar = "div" if embedded else "header"
    return (f'{head}{radios}<{toolbar} class="ui-world-head">{_board_html(world["board"])}<nav class="ui-world-tools">{header_tools}</nav></{toolbar}>'
            f'{rpg_hud}<div class="ui-world-body">{view}{dpad}<div class="ui-world-side">{side}</div></div>{foot}{tail}')


def _map_html(world: dict[str, Any], *, embedded: bool = False) -> str:
    wid, floors, shell = world["id"], world["floors"], _world_shell(world)
    rpg = world.get("rpg")
    categories = _world_categories(floors)
    cat_ids = [""] + categories
    radios = "".join(
        f'<input class="ui-world-radio" type="radio" name="{wid}-floor" id="{wid}-floor-{f["id"]}" value="{f["id"]}"'
        f'{" checked" if i == 0 else ""}>' for i, f in enumerate(floors))
    radios += "".join(
        f'<input class="ui-world-radio" type="radio" name="{wid}-cat" id="{wid}-cat-{"value-" + c if c else "all"}" value="{c}"'
        f'{" checked" if not c else ""}>' for c in cat_ids)
    floor_labels = labels = "".join(f'<label for="{wid}-floor-{f["id"]}">{escape(f["label"])}</label>' for f in floors)
    if categories:
        labels += "".join(f'<label for="{wid}-cat-{"value-" + c if c else "all"}" data-cat="{c}">{escape(c or "all")}</label>' for c in cat_ids)
    close = f'<a class="ui-sheet-close" href="#{wid}-map"' + (f' {_wt("close")}>✖️</a>' if shell else ">Close</a>")          # an icon in a shell world
    confirm = world["move"] == "confirm"
    built = [_floor_html(wid, f, close, confirm=confirm, rpg=rpg) for f in floors]
    scale = "" if world["mark_scale"] == [1, 1] else f' style="--mark-x:{world["mark_scale"][0]:g};--mark-y:{world["mark_scale"][1]:g}"'
    move_attr = ' data-move="confirm"' if confirm else ""
    rpg_attr = ' data-rpg' if rpg else ""
    rpg_json = ('<script type="application/json" class="ui-rpg-data">' + json.dumps(rpg, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c") + '</script>') if rpg else ""
    head = (f'<section class="ui-world ui-world-map" id="{wid}-map" data-ui-world="map" data-zoom-max="{world["zoom_max"]}" data-names="{world["names"]}"'
            f'{move_attr}{rpg_attr}{scale}'
            f'{" data-grid" if any(f.get("tile") for f in floors) else ""}{" data-shell" if shell else ""} aria-label="{escape(world["title"], quote=True)}">')
    view = f'<div class="ui-world-view" tabindex="0"><div class="ui-world-cam" style="--fx:0;--fy:0;--z:1">{"".join(stage for stage, _ in built)}</div></div>'
    tail = f'<aside class="ui-sheet" aria-live="polite">{"".join(a for _, articles in built for a in articles)}</aside>{_pick_html(wid, world.get("avatars", []), shell)}{rpg_json}</section>'
    if shell:
        return _shell_html(world, head=head, radios=radios, view=view, tail=tail, floor_labels=floor_labels, embedded=embedded)
    return _classic_html(world, head=head, radios=radios, labels=labels, view=view, tail=tail)


def world_html(spec: Any, *, embedded: bool = False) -> str:
    """Semantic HTML for a world; every label and body is escaped. Works without JavaScript (scroll, :target, radios)."""
    world = world_validate(spec)
    return (_shots_html(world) if world["shots"] else "") + (_map_html(world, embedded=embedded) if world["floors"] else "")





_WORLD_CSS = (
    ".ui-world{--ui-world-h:min(70vh,560px);position:relative;margin:1rem 0;border:1px solid var(--ui-border);background:var(--ui-bg);"
    "color:var(--ui-fg);border-radius:var(--ui-radius);overflow:hidden}"
    ".ui-world-motion-controls{padding:8px}.ui-world-walk{display:flex;gap:8px;flex-wrap:wrap}.ui-world-walk input{width:6em}.ui-world-walk[hidden]{display:none}.ui-world[data-js] .ui-player{transition:none}.ui-world[data-motion-paused] .ui-actor,.ui-world[data-motion-paused] .ui-board-run{animation-play-state:paused!important}"
    ".ui-world-radio{position:absolute;opacity:0;pointer-events:none}"
    ".ui-world-bar{display:flex;flex-wrap:wrap;gap:8px;padding:8px;border-bottom:1px solid var(--ui-border)}"
    ".ui-world-bar label{border:1px solid var(--ui-border);padding:.35rem .75rem;cursor:pointer;background:var(--ui-panel);border-radius:var(--ui-radius)}"
    ".ui-world-view{position:relative;overflow:auto;height:var(--ui-world-h);container-type:size}"
    ".ui-world[data-js] .ui-world-view{overflow:hidden;touch-action:none;cursor:grab}"
    ".ui-world[data-js][data-drag] .ui-world-view{cursor:grabbing}"
    ".ui-world-cam{position:relative;transform-origin:0 0}"
    ".ui-world[data-js] .ui-world-cam{transform:translate(calc(50cqw - var(--fx,0) * var(--z,1) * 1px),calc(50cqh - var(--fy,0) * var(--z,1) * 1px)) "
    "scale(var(--z,1));transition:transform .24s ease-out}"
    ".ui-world[data-js][data-drag] .ui-world-cam{transition:none}"
    ".ui-floor{position:relative;display:none;background-color:var(--ui-panel);background-image:linear-gradient(var(--ui-border) 1px,transparent 1px),"
    "linear-gradient(90deg,var(--ui-border) 1px,transparent 1px);background-size:64px 64px}"
    # Layers of a map, back to front, like the z-order of a slide: the ground (props), the names (spot pills), the marks (dots and signs),
    # the player and actors, the sheet. data-names on .ui-world moves every plain spot between the name layer (names) and the mark layer
    # (dots: a dot; the one the player stands by, the one under the pointer and the focused one show their names; off: dots only).
    + DIAL_CSS +
    ".ui-world-map{--ui-layer-ground:0;--ui-layer-name:1;--ui-layer-mark:2;--ui-layer-player:3;--ui-layer-sheet:4}"
    ".ui-spot{position:absolute;z-index:var(--ui-layer-name);transform:translate(-50%,-50%) scale(calc(1 / var(--z,1)));white-space:nowrap;border:1px solid transparent;"
    "background:transparent;color:color-mix(in srgb,var(--ui-fg) 76%,transparent);padding:.15rem .45rem;border-radius:999px;text-decoration:none;font-size:.74rem;"
    "text-shadow:0 0 3px var(--ui-bg),0 0 3px var(--ui-bg),0 1px 2px var(--ui-bg)}"
    ".ui-spot:not([data-sign]):is(:hover,:focus-visible,[data-near],[data-selected]){background:var(--ui-bg);border-color:var(--ui-accent);color:var(--ui-fg);"
    "font-size:.82rem;padding:.2rem .6rem;text-shadow:none;z-index:var(--ui-layer-mark)}"
    ".ui-spot[data-sign],.ui-world[data-names=dots] .ui-spot:not([data-sign]):not([data-near]):not(:hover):not(:focus-visible):not([data-named]),"
    ".ui-world[data-names=off] .ui-spot:not([data-sign]):not(:hover):not(:focus-visible):not([data-named])"
    "{z-index:var(--ui-layer-mark);padding:.3rem .5rem;border-radius:4px;font-size:0;line-height:1;letter-spacing:.04em;background:color-mix(in srgb,var(--ui-bg) 78%,transparent);border-color:color-mix(in srgb,var(--ui-border) 80%,transparent);text-shadow:none}"
    ".ui-spot[data-sign]::before,.ui-world[data-names=dots] .ui-spot:not([data-sign]):not([data-near]):not(:hover):not(:focus-visible):not([data-named])::before,"
    ".ui-world[data-names=off] .ui-spot:not([data-sign]):not(:hover):not(:focus-visible):not([data-named])::before{content:var(--mark,\"●\");font-size:.7rem}"
    # A mark (an emoji in --mark) stands in for the dot and leads the name; --mark-x / --mark-y on the world scale every mark's width and height.
    ".ui-spot::before{display:inline-block;transform:scale(var(--mark-x,1),var(--mark-y,1))}"
    # A spot with data-named (always_named) stays in the name layer in every mode: its name shows faint behind the marks, like a village's name on a land.
    ".ui-world[data-names=names] .ui-spot:not([data-sign])::before,.ui-world[data-names=dots] .ui-spot[data-near]:not([data-sign])::before,.ui-spot[data-named]::before,"
    ".ui-world:not([data-names=names]) .ui-spot:not([data-sign]):hover::before,.ui-world:not([data-names=names]) .ui-spot:not([data-sign]):focus-visible::before{content:var(--mark);margin-right:.3em}"
    ".ui-world[data-names]:not([data-names=names]) .ui-spot:not([data-sign]){border-radius:999px}"
    # data-named=left / right: the name hangs on that side and the mark stays on the point (the camera's zoom --z keeps both where they are).
    ".ui-spot[data-named=left]{display:flex;flex-direction:row-reverse;transform-origin:right center;transform:translate(calc(-100% + .85rem / var(--z,1)),-50%) scale(calc(1 / var(--z,1)))}"
    ".ui-spot[data-named=left]::before{margin:0 0 0 .3em}"
    ".ui-spot[data-named=right]{transform-origin:left center;transform:translate(calc(-.85rem / var(--z,1)),-50%) scale(calc(1 / var(--z,1)))}"
    ".ui-world[data-names=dots] .ui-spot[data-near],.ui-world:not([data-names=names]) .ui-spot:hover,.ui-world:not([data-names=names]) .ui-spot:focus-visible{z-index:var(--ui-layer-mark)}"
    ".ui-spot[data-sign][data-show]{padding:.05rem .4rem;font-size:.7rem}.ui-spot[data-sign][data-show]::before{content:var(--mark,\"●\");margin-right:.3em}"
    ".ui-spot[data-sign=led]{background:#111;color:#ffb000;border-color:#ffb000;font-family:monospace;text-shadow:0 0 4px #ffb000}"
    ".ui-spot[data-sign=wood]{background:#8b5a2b;color:#fff3d6;border:2px solid #5d3a1a}"
    ".ui-sheet{position:absolute;z-index:var(--ui-layer-sheet);left:8px;right:8px;bottom:8px;max-height:45%;overflow:auto;border:1px solid var(--ui-border);"
    "background:var(--ui-panel);border-radius:var(--ui-radius);padding:1rem}"
    ".ui-world:not([data-js]) .ui-sheet:not(:has(.ui-sheet-item:target)){display:none}"
    ".ui-world[data-js] .ui-sheet:not(:has(.ui-sheet-item[data-open])){display:none}"
    ".ui-sheet-item{display:none}.ui-world:not([data-js]) .ui-sheet-item:target,.ui-world[data-js] .ui-sheet-item[data-open]{display:block}.ui-sheet h3{margin:0 0 .5rem}"
    ".ui-shot{padding:1.5rem;transition:opacity .4s,transform .4s}"
    ".ui-shot-hud{font-family:var(--ui-font-mono);letter-spacing:.12em;margin:0 0 .5rem;font-size:.8rem}"
    ".ui-world[data-js] .ui-shots-scroll{height:var(--ui-world-h);overflow:auto;position:relative}"
    ".ui-world[data-js] .ui-shots-track{position:relative;height:calc(var(--shots) * var(--ui-world-h))}"
    ".ui-world[data-js] .ui-shots-stage{position:sticky;top:0;height:var(--ui-world-h);overflow:hidden;background:var(--ui-bg);transition:background .6s}"
    ".ui-world[data-js] .ui-shot{position:absolute;inset:0;opacity:0;transform:translateY(16px)}"
    ".ui-shot-mark{position:absolute;left:0;top:calc(var(--i) * var(--ui-world-h));width:1px;height:var(--ui-world-h);pointer-events:none}"
    ".ui-actor{position:absolute;left:0;top:0;text-decoration:none;color:inherit}"
    ".ui-actor span,.ui-player span{display:block;transform:translate(-50%,-50%) scale(calc(1 / var(--z,1)));font-size:1.5rem;line-height:1}"
    ".ui-player{position:absolute;z-index:var(--ui-layer-player);left:0;top:0;pointer-events:none;transform:translate(calc(var(--px,0) * 1px),calc(var(--py,0) * 1px));"
    "transition:transform var(--walk,0s) linear}"
    ".ui-board{display:flex;flex-wrap:wrap;align-items:center;gap:4px 8px;padding:4px 8px;border-bottom:1px solid var(--ui-border);background:var(--ui-panel);"
    "font-family:var(--ui-font-mono);font-size:.85rem;overflow:hidden}"
    ".ui-board:has(.ui-board-shared){flex-wrap:wrap}.ui-board-shared{flex-basis:100%;white-space:normal;font-family:var(--ui-font);overflow-wrap:anywhere}.ui-board-shared ul{max-height:14rem;overflow:auto}"
    ".ui-board-clock{flex:none;white-space:nowrap;border:1px solid var(--ui-accent);padding:0 .5rem;border-radius:var(--ui-radius);font-variant-numeric:tabular-nums}"
    ".ui-board-track{flex:4 1 14rem;min-width:0;overflow:hidden;white-space:nowrap}"
    ".ui-board-run{display:inline-flex;animation:ui-board-scroll 24s linear infinite}"
    ".ui-board-item{padding-right:3rem}"
    ".ui-board-zones{display:flex;flex-wrap:wrap;gap:0 12px}"
    ".ui-board-zone{flex:none;white-space:nowrap;color:var(--ui-muted)}.ui-board-zone b{color:var(--ui-fg);font-weight:400;font-variant-numeric:tabular-nums}"
    ".ui-board-stamp{margin-right:.25rem;color:var(--ui-muted);font-variant-numeric:tabular-nums}"
    ".ui-board-gauge{white-space:nowrap}.ui-board-cells{letter-spacing:.05em}.ui-board-pct{font-variant-numeric:tabular-nums}"
    ".ui-board-post{display:flex;gap:4px;flex:1 1 13rem}.ui-board-post .ui-input{flex:1;min-width:0;width:auto;padding:.2rem .5rem}.ui-board-post .ui-button{padding:.2rem .6rem}"
    "@keyframes ui-board-scroll{from{transform:translateX(0)}to{transform:translateX(-50%)}}"
    ".ui-floor[data-tile]{background-size:var(--tile) var(--tile)}"
    ".ui-prop{position:absolute;z-index:var(--ui-layer-ground);box-sizing:border-box;pointer-events:none;border:2px solid var(--ui-border);border-radius:4px}"
    ".ui-prop[data-kind=desk]{background:color-mix(in srgb,var(--ui-accent) 24%,var(--ui-panel))}"
    ".ui-prop[data-kind=board]{background:color-mix(in srgb,var(--ui-accent) 55%,#000)}"
    ".ui-prop[data-kind=wall]{background:var(--ui-border)}"
    ".ui-prop[data-kind=shelf]{background:color-mix(in srgb,var(--ui-muted) 35%,var(--ui-panel))}"
    ".ui-prop[data-kind=chair]{border:0;background:radial-gradient(circle,var(--ui-muted) 0 52%,transparent 54%)}"
    ".ui-prop[data-kind=rug]{border-style:dashed;background:color-mix(in srgb,var(--ui-accent) 10%,transparent)}"
    ".ui-world[data-shell]{--ui-world-h:min(56vh,512px);--ui-world-foot:56px}"
    # Header: the info board. Side: this screen's own controls, as 48px buttons that open a panel over the map (the page never grows taller).
    # Footer: the door-to-door pulldown.
    ".ui-world-body{position:relative;display:flex}.ui-world-body>.ui-world-view{flex:1;min-width:0}"
    ".ui-world-side{display:flex;flex-direction:column;gap:8px;padding:8px;z-index:2;border-left:1px solid var(--ui-border);background:var(--ui-panel)}"
    ".ui-world-menu[hidden]{display:none}"
    ".ui-world-menu>summary{display:flex;align-items:center;justify-content:center;width:48px;height:48px;box-sizing:border-box;list-style:none;cursor:pointer;"
    "user-select:none;-webkit-user-select:none;font-size:1.25rem;line-height:1;border:1px solid var(--ui-border);background:var(--ui-bg);color:var(--ui-fg);border-radius:var(--ui-radius)}"
    ".ui-world-menu>summary::-webkit-details-marker{display:none}.ui-world-menu[open]>summary{background:var(--ui-accent);color:var(--ui-bg)}"
    ".ui-world-home,.ui-world-tool{display:flex;align-items:center;justify-content:center;width:48px;height:48px;box-sizing:border-box;text-decoration:none;color:var(--ui-fg);cursor:pointer;"
    "font-size:1.25rem;line-height:1;border:1px solid var(--ui-border);background:var(--ui-bg);border-radius:var(--ui-radius)}"
    ".ui-world-head{position:relative;z-index:3;display:flex;align-items:center;border-bottom:1px solid var(--ui-border);background:var(--ui-panel)}"
    ".ui-world-head .ui-board{flex:1;min-width:0;border-bottom:0}.ui-world-head .ui-board-track{flex:4 1 4rem}"
    ".ui-world-tools{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:8px;padding:4px 8px}"   # at 320px seven 40px tools wrap into two rows instead of leaving the window
    ".ui-world-tools .ui-world-home,.ui-world-tools .ui-world-tool,.ui-world-tools .ui-world-menu>summary{width:40px;height:40px}"
    "@media(max-width:600px){.ui-world-head{flex-wrap:wrap}.ui-world-head .ui-board{flex-basis:100%;box-sizing:border-box}.ui-world-head .ui-world-tools{width:100%;box-sizing:border-box}}"
    ".ui-world-panel p{margin:0}.ui-world-panel>button{min-width:48px}.ui-world-panel button[aria-pressed=true]{background:var(--ui-accent);color:var(--ui-bg)}"
    ".ui-world-tools .ui-world-panel{top:100%;right:8px;width:min(320px,calc(100% - 16px));max-height:min(60vh,384px)}"
    ".ui-world-settings,.ui-world-tools .ui-world-panel{display:flex;flex-wrap:wrap;gap:8px}.ui-world-tools .ui-world-panel[hidden]{display:none}"
    ".ui-world-star,.ui-world-bag-rm{flex:none;min-width:40px;min-height:40px;border:0;background:none;color:var(--ui-accent);font-size:1.25rem;line-height:1;cursor:pointer;display:none}"
    ".ui-world[data-js] .ui-world-star,.ui-world[data-js] .ui-world-bag-rm{display:inline-flex;align-items:center;justify-content:center}"
    ".ui-world-rows li{display:flex;align-items:center}.ui-world-rows li>a{flex:1;min-width:0}"
    ".ui-world-favs,.ui-world-bag{width:100%}.ui-world-favs:empty,.ui-world-bag:empty{display:none}"
    ".ui-world-empty{margin:0;width:100%;text-align:center;font-size:1.5rem;color:var(--ui-muted)}"
    ".ui-world-panel:has(.ui-world-favs:not(:empty),.ui-world-bag:not(:empty)) .ui-world-empty{display:none}"
    ".ui-sheet-item .ui-world-take,.ui-sheet-item .ui-world-go{display:inline-flex;align-items:center;gap:.35rem;margin-right:.5rem;padding:.35rem .75rem;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-bg);color:var(--ui-fg);font-size:1rem;cursor:pointer}"
    ".ui-sheet-item .ui-world-take[hidden],.ui-sheet-item .ui-world-go[hidden]{display:none}"
    ".ui-sheet-item .ui-world-take[aria-pressed=true]{background:var(--ui-accent);color:var(--ui-bg)}"
    ".ui-world-item-note{margin:0 0 .5rem;font-size:.9rem;color:var(--ui-muted)}"
    ".ui-world-panel{position:absolute;top:8px;right:72px;width:min(320px,calc(100% - 88px));max-height:calc(100% - 16px);overflow:auto;box-sizing:border-box;"
    "padding:16px;border:1px solid var(--ui-border);background:var(--ui-panel);color:var(--ui-fg);border-radius:var(--ui-radius);box-shadow:0 8px 24px rgb(0 0 0 / .25)}"
    ".ui-world-panel h3{margin:0 0 8px}.ui-world-panel button{min-height:40px}"
    ".ui-world[data-shell] .ui-world-motion-controls{display:flex;flex-direction:column;align-items:stretch;gap:8px;padding:0}"
    ".ui-world[data-shell] .ui-world-motion-controls[hidden]{display:none}.ui-world-motion-controls .ui-world-walk{align-items:end}"
    ".ui-world-chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}"
    ".ui-world-chips label{border:1px solid var(--ui-border);padding:.25rem .75rem;cursor:pointer;background:var(--ui-bg);border-radius:var(--ui-radius)}"
    ".ui-world-rows{list-style:none;margin:0;padding:0}.ui-world-spots{display:none}"
    ".ui-world-rows a{display:flex;align-items:center;gap:8px;min-height:40px;padding:0 8px;color:inherit;text-decoration:none;border-radius:var(--ui-radius)}"
    ".ui-world-rows a:hover,.ui-world-rows a:focus-visible{background:var(--ui-bg)}"
    ".ui-world-arrow{flex:none;width:2em;text-align:center}"
    ".ui-world-foot{display:flex;align-items:center;gap:8px;box-sizing:border-box;min-height:var(--ui-world-foot);padding:8px;border-top:1px solid var(--ui-border)}"
    ".ui-world-foot .ui-world-bar{padding:0;border:0}"
    ".ui-world-goto-wrap{display:none;align-items:center;gap:8px;flex:1}.ui-world[data-js] .ui-world-goto-wrap{display:flex}.ui-world[data-js] .ui-world-foot .ui-world-bar{display:none}"
    ".ui-world-goto{flex:1;min-width:0;max-width:384px;min-height:40px;font:inherit;color:var(--ui-fg);background:var(--ui-bg);border:1px solid var(--ui-border);border-radius:var(--ui-radius)}"
    ".ui-world[data-shell] .ui-sheet{z-index:3;right:80px;bottom:calc(var(--ui-world-foot) + 8px)}.ui-world[data-shell]:not(:has(.ui-world-foot)) .ui-sheet{bottom:8px}"
    # Controls drawn over the map (data-overlay: the pad) share one opacity, --ui-overlay-alpha, that 🫥 in ⚙️ sets from .2 to 1.
    ".ui-world-body>.ui-world-dpad{position:absolute;left:8px;bottom:8px;z-index:1}.ui-world [data-overlay]{opacity:var(--ui-overlay-alpha,.9)}.ui-world-dpad[hidden]{display:none}"
    ".ui-world-zoom,.ui-world-alpha{display:inline-flex;align-items:center;gap:8px}.ui-world-alpha input{width:96px;accent-color:var(--ui-accent)}"
    ".ui-world-dpad{display:grid;grid-template-columns:repeat(3,48px);grid-auto-rows:48px;gap:8px}"
    ".ui-world-dpad button{min-width:48px;min-height:48px;font-size:1.25rem;line-height:1;border:1px solid var(--ui-border);background:var(--ui-panel);"
    "color:var(--ui-fg);border-radius:var(--ui-radius);cursor:pointer;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none;touch-action:none}"
    ".ui-world-dpad [data-step=\"0,-1\"]{grid-column:2}.ui-world-dpad [data-step=\"-1,0\"]{grid-column:1;grid-row:2}"
    ".ui-world-dpad [data-step=\"1,0\"]{grid-column:3;grid-row:2}.ui-world-dpad [data-step=\"0,1\"]{grid-column:2;grid-row:3}"
    ".ui-world-pick{position:absolute;inset:0;z-index:3;display:flex;padding:16px;overflow:auto;background:color-mix(in srgb,var(--ui-bg) 90%,transparent)}"
    ".ui-world-pick[hidden]{display:none}"
    ".ui-world-pick>div{margin:auto;max-width:384px;width:100%;box-sizing:border-box;text-align:center;border:1px solid var(--ui-border);"
    "background:var(--ui-panel);border-radius:var(--ui-radius);padding:16px}"
    ".ui-world-pick h3{margin:0 0 8px}"
    ".ui-world-pick-grid{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-bottom:8px}"
    ".ui-world-pick-grid button{min-height:48px;font-size:1.5rem;line-height:1;border:1px solid var(--ui-border);background:var(--ui-bg);"
    "border-radius:var(--ui-radius);cursor:pointer;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;min-width:48px;max-width:100%;padding:0 8px}"
    ".ui-world-pick-form{display:flex;flex-wrap:wrap;gap:8px;align-items:center;justify-content:center}"
    ".ui-real{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;pointer-events:none;user-select:none;-webkit-user-select:none}"
    ".ui-world[data-js] .ui-floor[data-real]:not([data-backdrop])::after{content:\"🖼️📷\";position:absolute;left:50%;top:50%;font-size:48px;line-height:1;opacity:.5;"
    "pointer-events:none;transform:translate(-50%,-50%) scale(calc(1 / var(--z,1)))}.ui-world-real{font-size:1.5rem;line-height:1}"
    ".ui-world[data-pick] .ui-player{visibility:hidden}.ui-player span{white-space:nowrap}"
    "@media(prefers-reduced-motion:reduce){.ui-world *{transition:none!important}.ui-actor,.ui-board-run{animation-play-state:paused!important}}"
)

_WORLD_RPG_CSS = (
    ".ui-world[data-shell][data-rpg]{--ui-world-h:min(50vh,464px)}"
    ".ui-rpg-hud{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;padding:6px 10px;border-bottom:1px solid var(--ui-border);background:var(--ui-panel);font-size:.8rem;line-height:1.25}"
    ".ui-rpg-hud[hidden]{display:none}"
    ".ui-rpg-stat{display:inline-flex;align-items:center;gap:5px;white-space:nowrap;font-variant-numeric:tabular-nums}"
    ".ui-rpg-hero{font-weight:700}"
    ".ui-rpg-meter{display:inline-block;width:54px;height:8px;border-radius:999px;background:color-mix(in srgb,var(--ui-fg) 16%,transparent);overflow:hidden;vertical-align:middle}"
    ".ui-rpg-meter>i{display:block;height:100%;background:#2e9d5b;border-radius:999px;transition:width .25s ease}"
    ".ui-rpg-meter-mp>i{background:#3b82f6}"
    ".ui-rpg-meter-foe>i{background:#ef4444}"
    ".ui-rpg-pill{display:inline-flex;align-items:center;gap:4px;min-height:28px;padding:2px 9px;border:1px solid var(--ui-border);border-radius:999px;background:var(--ui-bg);color:var(--ui-fg);font:inherit;font-size:.78rem;font-weight:600;cursor:pointer;white-space:nowrap}"
    ".ui-rpg-pill:hover,.ui-rpg-pill:focus-visible{border-color:var(--ui-accent);outline:none}"
    "[data-rpg-kind=\"chest\"][data-rpg-opened],[data-rpg-kind=\"drop\"][data-rpg-collected],[data-rpg-kind=\"enemy\"][data-rpg-defeated]{opacity:.58}"
    "[data-rpg-kind=\"enemy\"][data-rpg-boss]{border-color:#d946ef!important;box-shadow:0 0 0 2px color-mix(in srgb,#d946ef 32%,transparent)}"
    "[data-rpg-kind=\"npc\"]{border-color:color-mix(in srgb,var(--ui-accent) 45%,transparent)}"
    ".ui-rpg-overlay{position:absolute;inset:0;z-index:10;display:grid;place-items:center;padding:12px;background:color-mix(in srgb,var(--ui-bg) 70%,transparent);backdrop-filter:blur(4px)}"
    ".ui-rpg-overlay[hidden]{display:none}"
    ".ui-rpg-card{width:min(100%,480px);max-height:100%;overflow:auto;border:2px solid var(--ui-fg);border-radius:var(--ui-radius);background:var(--ui-bg);color:var(--ui-fg);padding:12px 14px;box-shadow:0 12px 32px rgba(0,0,0,.35);display:flex;flex-direction:column;gap:10px}"
    ".ui-rpg-journal-card{width:min(100%,540px)}"
    ".ui-rpg-card-head{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:1px solid var(--ui-border);padding-bottom:6px}"
    ".ui-rpg-card-title{display:flex;align-items:center;gap:8px;font-weight:700;font-size:.98rem;margin:0}"
    ".ui-rpg-close{min-width:34px;min-height:34px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel);color:var(--ui-fg);cursor:pointer;font-size:1rem;line-height:1}"
    ".ui-rpg-text{margin:0;font-size:.9rem;line-height:1.5;white-space:pre-line}"
    ".ui-rpg-subnote{margin:0;font-size:.78rem;color:color-mix(in srgb,var(--ui-fg) 75%,transparent)}"
    ".ui-rpg-actions,.ui-rpg-cmd-grid,.ui-rpg-tabs{display:flex;flex-wrap:wrap;gap:8px}"
    ".ui-rpg-btn{min-height:36px;padding:6px 11px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel);color:var(--ui-fg);font:inherit;font-size:.84rem;font-weight:600;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:5px;text-align:left}"
    ".ui-rpg-btn:hover:not(:disabled),.ui-rpg-btn:focus-visible:not(:disabled){border-color:var(--ui-accent);background:color-mix(in srgb,var(--ui-accent) 14%,var(--ui-panel))}"
    ".ui-rpg-btn:disabled{opacity:.48;cursor:not-allowed}"
    ".ui-rpg-btn[data-primary]{background:var(--ui-accent);color:var(--ui-bg);border-color:var(--ui-accent)}"
    ".ui-rpg-btn[aria-selected=\"true\"]{background:var(--ui-accent);color:var(--ui-bg);border-color:var(--ui-accent)}"
    ".ui-rpg-cmd-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}"
    ".ui-rpg-foe-box{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel)}"
    ".ui-rpg-foe-sprite{font-size:2.4rem;line-height:1;min-width:48px;text-align:center}"
    ".ui-rpg-foe-info{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}"
    ".ui-rpg-foe-meta{display:flex;flex-wrap:wrap;align-items:center;gap:6px;font-size:.82rem}"
    ".ui-rpg-intent{display:inline-flex;align-items:center;gap:4px;padding:2px 7px;border-radius:999px;background:color-mix(in srgb,#f59e0b 20%,var(--ui-bg));border:1px solid #f59e0b;font-size:.74rem;font-weight:700}"
    ".ui-rpg-orbs{min-height:28px;display:flex;flex-wrap:wrap;align-items:center;gap:4px;padding:4px 8px;border:1px dashed var(--ui-border);border-radius:var(--ui-radius);font-size:.82rem}"
    ".ui-rpg-orb{display:inline-block;animation:ui-rpg-rise .55s ease-out}"
    "@keyframes ui-rpg-rise{0%{opacity:.2;transform:translateY(6px) scale(.85)}100%{opacity:1;transform:none}}"
    ".ui-rpg-log{margin:0;padding:8px 10px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel);font-size:.82rem;line-height:1.45;min-height:48px;max-height:108px;overflow:auto}"
    ".ui-rpg-subpanel{display:flex;flex-direction:column;gap:6px;padding:8px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel)}"
    ".ui-rpg-subpanel[hidden]{display:none}"
    ".ui-rpg-list{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}"
    ".ui-rpg-row{padding:8px 10px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel);display:flex;flex-direction:column;gap:4px;font-size:.82rem}"
    ".ui-rpg-row-top{display:flex;align-items:center;justify-content:space-between;gap:8px;font-weight:700}"
    ".ui-rpg-badges{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:8px}"
    ".ui-rpg-badge{padding:8px;border:1px solid var(--ui-border);border-radius:var(--ui-radius);background:var(--ui-panel);font-size:.78rem;display:flex;flex-direction:column;gap:2px}"
    ".ui-rpg-badge[data-unlocked=\"false\"]{opacity:.5}"
    ".ui-rpg-toast{position:absolute;left:50%;bottom:54px;transform:translateX(-50%);z-index:9;max-width:min(92%,420px);padding:6px 12px;border-radius:999px;border:1px solid var(--ui-accent);background:var(--ui-bg);color:var(--ui-fg);font-size:.8rem;font-weight:600;box-shadow:0 6px 18px rgba(0,0,0,.25);pointer-events:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}"
    ".ui-rpg-toast[hidden]{display:none}"
    ".ui-spot[data-scroll-found]{outline:3px solid var(--ui-accent);outline-offset:2px;animation:scroll-glow 1s ease-in-out 3}"
    "@keyframes scroll-glow{50%{box-shadow:0 0 12px 5px gold}}"
    "@media(prefers-reduced-motion:reduce){.ui-spot[data-scroll-found]{animation:none}}"
    "@media(max-width:640px){.ui-rpg-hud{padding:5px 8px;gap:4px 8px;font-size:.75rem}.ui-rpg-meter{width:42px}.ui-rpg-cmd-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.ui-rpg-card{padding:10px 11px}}"
    "@media(prefers-reduced-motion:reduce){.ui-rpg-orb,.ui-rpg-meter>i{animation:none!important;transition:none!important}}"
)

_WALL_CSS = (
    ".ui-wall{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}"
    ".ui-wall-cell{border:1px solid var(--ui-border);padding:16px;border-radius:var(--ui-radius);background:var(--ui-bg);color:var(--ui-fg)}"
    ".ui-wall-cell h3{margin:0 0 8px}"
)


def world_base_css() -> str:
    """Fixed world rules, shared by the Portfolio web build."""
    return _WORLD_CSS


def world_css(spec: Any, *, base: bool = True) -> str:
    """CSS for a world: fixed rules plus one rule per floor, category and shot (radios and data-lit drive them through :has).

    ``base=False`` leaves the fixed rules out, for a second world on a page that already has them.
    """
    world = world_validate(spec)
    wid, rules = world["id"], [world_base_css()] if base else []
    if world.get("rpg"):
        rules.append(_WORLD_RPG_CSS)
    for f in world["floors"]:
        radio = f"#{wid}-floor-{f['id']}"
        rules.append(f'.ui-world:has({radio}:checked) .ui-floor[data-floor="{f["id"]}"]{{display:block}}')
        rules.append(f'.ui-world:has({radio}:checked) label[for="{wid}-floor-{f["id"]}"]{{background:var(--ui-accent);color:var(--ui-bg)}}')
    for kind in sorted({q["kind"] for f in world["floors"] for q in f.get("props", [])} & WORLD_LOOK.keys()):
        colour, glyph, once = WORLD_LOOK[kind]
        picture = ""
        if glyph:
            svg = f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text x='16' y='25' font-size='26' text-anchor='middle'>{glyph}</text></svg>"
            picture = f'url("data:image/svg+xml,{quote(svg)}") ' + ("center/contain no-repeat," if once else "0 0/var(--tile) var(--tile),")
        rules.append(f".ui-prop[data-kind={kind}]{{border:0;border-radius:0;background:{picture}{colour or 'transparent'}}}")
    categories = _world_categories(world["floors"])
    if _world_shell(world):
        for f in world["floors"]:
            rules.append(f'.ui-world:has(#{wid}-floor-{f["id"]}:checked) .ui-world-spots[data-floor="{f["id"]}"]{{display:block}}')
        for c in categories:
            rules.append(f'.ui-world:has(#{wid}-cat-value-{c}:checked) .ui-world-spots li:not([data-category="{c}"]){{display:none}}')
    for f in world["floors"]:
        for a in f["actors"]:
            path = villager_path(a["seed"] if a["seed"] is not None else zlib.crc32(f"{wid}:{a['id']}".encode()),
                                 f["width"], f["height"], speed=a["speed"])
            name = f"ui-walk-{wid}-{a['id']}"
            frames = "".join(f"{pct}%{{transform:translate({x}px,{y}px)}}" for pct, x, y in path["keys"])
            rules.append(f"@keyframes {name}{{{frames}}}#{wid}-actor-{a['id']}{{animation:{name} {path['duration']}s linear infinite}}")
    for c in categories:
        radio = f"#{wid}-cat-value-{c}"
        rules.append(f'.ui-world:has({radio}:checked) .ui-spot:not([data-category="{c}"]){{display:none}}')
    for c in [""] + categories if categories else []:
        rules.append(f'.ui-world:has(#{wid}-cat-{"value-" + c if c else "all"}:checked) label[for="{wid}-cat-{"value-" + c if c else "all"}"]'
                     f'{{background:var(--ui-accent);color:var(--ui-bg)}}')
    if world["shots"]:
        rules.append('.ui-world-shots[data-js]:not(:has(.ui-shot-mark[data-lit])) .ui-shot[data-i="0"]{opacity:1;transform:none}')
    for i, s in enumerate(world["shots"]):
        lit = f'#{wid}-shots:has(.ui-shot-mark[data-i="{i}"][data-lit])'
        rules.append(f'{lit} .ui-shot[data-i="{i}"]{{opacity:1;transform:none}}')
        if s["bg"]:
            rules.append(f'{lit} .ui-shots-stage{{background:{s["bg"]};color:{ink_for(s["bg"])}}}')
    return "@layer components{" + "".join(rules) + "}"


# Browser arithmetic is a projection of the Python oracle, not Python execution.
WORLD_MOTION_JS = r"""
export function motionSample(s,t){const f=s.duration===0?(t>=s.at?1:0):Math.min(1,Math.max(0,(t-s.at)/s.duration));return s.from.map((v,i)=>v+(s.to[i]-v)*f)}
export function motionWalk(a,b,t,speed,w,h){const point=p=>p.map((v,i)=>Math.min(i?h:w,Math.max(0,v)));a=point(a);b=point(b);return{at:t,duration:Math.hypot(b[0]-a[0],b[1]-a[1])/speed,from:a,to:b}}
export function motionRoute(pts,t,speed,w,h){const out=[];for(let i=0;i<pts.length-1;i++){const s=motionWalk(pts[i],pts[i+1],t,speed,w,h);out.push(s);t+=s.duration}return out.length?out:[motionWalk(pts[0],pts[0],t,speed,w,h)]}
export function routeSample(r,t){for(const s of r)if(t<s.at+s.duration)return motionSample(s,t);return motionSample(r[r.length-1],t)}
export function gridPath(rows,s,g){const W=rows[0].length,H=rows.length,fit=c=>[Math.min(W-1,Math.max(0,c[0])),Math.min(H-1,Math.max(0,c[1]))],k=c=>c[1]*W+c[0];s=fit(s);g=fit(g);
 const parent=new Map([[k(s),null]]),order=[s];
 for(let i=0;i<order.length;i++){const[x,y]=order[i];for(const[dx,dy]of[[1,0],[-1,0],[0,1],[0,-1]]){const n=[x+dx,y+dy];if(n[0]>=0&&n[0]<W&&n[1]>=0&&n[1]<H&&rows[n[1]][n[0]]==="0"&&!parent.has(k(n))){parent.set(k(n),order[i]);order.push(n)}}}
 let end=g;if(!parent.has(k(g))){const d=c=>(c[0]-g[0])**2+(c[1]-g[1])**2;end=order.reduce((a,b)=>d(b)<d(a)?b:a)}
 const path=[end];for(let p=parent.get(k(end));p;p=parent.get(k(p)))path.push(p);return path.reverse()}
export function gridRoute(rows,tile,a,b){const cell=p=>[Math.min(rows[0].length-1,Math.max(0,Math.floor(p[0]/tile))),Math.min(rows.length-1,Math.max(0,Math.floor(p[1]/tile)))],t=cell(b),path=gridPath(rows,cell(a),t),mid=path.slice(1).map(c=>[(c[0]+.5)*tile,(c[1]+.5)*tile]),end=path[path.length-1];return end[0]===t[0]&&end[1]===t[1]?[a,...mid.slice(0,-1),b]:[a,...mid]}
export function direction(a,b,eps=8){const dx=b[0]-a[0],dy=b[1]-a[1];if(Math.abs(dx)<=eps&&Math.abs(dy)<=eps)return"📍";const ax=Math.abs(dx),ay=Math.abs(dy),sx=dx>0?1:-1,sy=dy>0?1:-1;if(ay*12<=ax*5)return sx>0?"➡️":"⬅️";if(ax*12<=ay*5)return sy>0?"⬇️":"⬆️";return sx>0?(sy>0?"↘️":"↗️"):(sy>0?"↙️":"↖️")}
export function cleanAvatar(text){const t=String(text).trim(),n=[...t].length;return n>=1&&n<=16&&!/[\p{Cc}\p{Cs}\p{Zl}\p{Zp}‪-‮⁦-⁩]|^\p{Zs}|\p{Zs}$/u.test(t)?t:null}
function bindPlayer(el,floor,onMove){
 const controls=el.querySelector('.ui-world-motion-controls');if(!controls)return ()=>{};
 const reduced=matchMedia('(prefers-reduced-motion: reduce)'),states=new Map(),button=el.querySelector('.ui-world-pause'),form=controls.querySelector('form'),gridOnly=[...el.querySelectorAll('.ui-world-grid-only')];
 let paused=false,base=performance.now(),elapsed=0;
 const time=()=>Math.min(1e9,elapsed+(paused||reduced.matches?0:(performance.now()-base)/1000));
 const freeze=()=>{elapsed=time();base=performance.now()};
 for(const f of el.querySelectorAll('.ui-floor')){const player=f.querySelector('.ui-player');if(!player)continue;const w=+f.dataset.w,h=+f.dataset.h,speed=+player.dataset.speed,point=[+player.dataset.x,+player.dataset.y],grid=f.dataset.blocked?{rows:f.dataset.blocked.split(','),tile:+f.dataset.tile}:null;states.set(f,{w,h,speed,player,grid,own:motionRoute([point,point],0,speed,w,h)});}
 const place=(s,t)=>{const p=routeSample(s.own,t);
  const dx=p[0]-parseFloat(s.player.style.getPropertyValue('--px')),dy=p[1]-parseFloat(s.player.style.getPropertyValue('--py'));
  if(dx||dy)s.player.dataset.facing=Math.abs(dx)>Math.abs(dy)?(dx>0?'east':'west'):(dy>0?'south':'north');
  s.player.style.setProperty('--px',p[0]);s.player.style.setProperty('--py',p[1]);return p};
 const walk=(x,y)=>{const s=states.get(floor());if(!s||![x,y].every(Number.isFinite))return;const t=time(),a=routeSample(s.own,t);s.own=motionRoute(s.grid?gridRoute(s.grid.rows,s.grid.tile,a,[x,y]):[a,[x,y]],t,s.speed,s.w,s.h);const end=s.own[s.own.length-1].to;if(reduced.matches)s.own=motionRoute([end,end],t,s.speed,s.w,s.h);s.player.style.setProperty('--walk',s.own.reduce((n,g)=>n+g.duration,0)+'s');s.player.dataset.targetX=end[0];s.player.dataset.targetY=end[1];place(s,t);};
 // One tile in a direction (arrow keys, WASD, the on-screen pad); false on a floor without a grid, true otherwise (a wall just stops).
 walk.step=(dx,dy)=>{const s=states.get(floor());if(!s||!s.grid)return false;const{rows,tile}=s.grid,p=routeSample(s.own,time()),cx=Math.floor(p[0]/tile)+dx,cy=Math.floor(p[1]/tile)+dy;if(rows[cy]?.[cx]==="0")walk((cx+.5)*tile,(cy+.5)*tile);return true};
 walk.where=()=>{const s=states.get(floor());return s&&routeSample(s.own,time())};
 for(const b of el.querySelectorAll('[data-step]')){const[dx,dy]=b.dataset.step.split(',').map(Number);let timer=0;const stop=()=>{clearInterval(timer);timer=0};
  b.addEventListener('pointerdown',e=>{e.preventDefault();walk.step(dx,dy);stop();const s=states.get(floor());timer=setInterval(()=>walk.step(dx,dy),s&&s.grid?Math.max(40,500*s.grid.tile/s.speed):160)});
  for(const n of['pointerup','pointercancel','pointerleave'])b.addEventListener(n,stop);
  b.addEventListener('click',e=>{if(e.detail===0)walk.step(dx,dy)})}
 button.addEventListener('click',()=>{freeze();paused=!paused;el.toggleAttribute('data-motion-paused',paused);button.setAttribute('aria-pressed',String(paused));button.textContent=paused?(button.dataset.resume||'動きを再開'):(button.dataset.pause||'動きを停止');});
 let wasReduced=reduced.matches;
 reduced.addEventListener('change',()=>{if(!wasReduced&&!paused)elapsed=Math.min(1e9,elapsed+(performance.now()-base)/1000);base=performance.now();wasReduced=reduced.matches;for(const s of states.values())place(s,time());});
 form.addEventListener('submit',e=>{e.preventDefault();if(form.reportValidity())walk(+form.elements.x.value,+form.elements.y.value)});
 const tick=()=>{if(!el.isConnected)return;controls.hidden=false;const active=states.get(floor()),t=time();form.hidden=!active;for(const n of gridOnly)n.hidden=!(active&&active.grid);
  if(active){form.elements.x.max=active.w;form.elements.y.max=active.h;const p=place(active,t);if(onMove)onMove(p);}
  requestAnimationFrame(tick);
 };requestAnimationFrame(tick);return walk;
}
"""


ISSUE_BULLETIN_JS = r"""
// GET only. No credentials, storage, Markdown rendering, or automatic polling.
export function cleanMessage(text,limit=60){if(typeof text!=="string")return null;const kept=[...text].map(c=>/[ \t\n\r\f\v\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/.test(c)?" ":(c!=="\u200d"&&/[\p{Cc}\p{Cf}\p{Cn}\p{Co}\p{Cs}\p{Zs}\p{Zl}\p{Zp}]/u.test(c)?"":c)).join("").split(" ").filter(Boolean).join(" ");const cut=[...kept].slice(0,limit).join("").trimEnd();return cut||null}
export function sharedLines(comments){
 if(!Array.isArray(comments))throw new Error("Invalid comments response");
 return comments.slice(0,100).filter(c=>c&&typeof c.body==="string"&&typeof c.user?.login==="string")
 .slice(-5).reverse().map(c=>({text:cleanMessage(c.body),author:c.user.login.slice(0,100),
 time:typeof c.created_at==="string"?c.created_at.slice(0,30):""})).filter(line=>line.text);
}
export function sharedWait(response,now){
 const retry=response.headers.get("retry-after"),reset=response.headers.get("x-ratelimit-reset");
 return Math.max(now+120000, retry&&Number.isFinite(Number(retry))?now+Number(retry)*1000:0,
 response.headers.get("x-ratelimit-remaining")==="0"&&Number.isFinite(Number(reset))?Number(reset)*1000:0);
}
// read is supplied by trusted code, never a URL or expression from a spec.
export function bindBulletin(panel,read,{rangeText="最大5件、本文60文字。",moreText="続きは投稿先で確認してください。",errorText="取得できませんでした。前回の表示を保持します。"}={}){
 if(!panel||typeof read!=="function")return;
 const button=panel.querySelector("[data-shared-refresh]"),status=panel.querySelector("[data-shared-status]"),list=panel.querySelector("[data-shared-comments]");
 let next=0,busy=false;
 button.addEventListener("click",async()=>{
  if(busy)return;
  if(Date.now()<next){status.textContent="更新待機中。"+Math.ceil((next-Date.now())/1000)+"秒後に再試行できます。";return}
  busy=true;button.disabled=true;next=Date.now()+120000;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
  try{
   const result=await read(controller.signal,headers=>{next=sharedWait({headers},Date.now())});
   if(!Array.isArray(result?.lines))throw new Error("Invalid bulletin lines");
   if(!panel.isConnected)return;
   const nodes=[];
   for(const line of result.lines.slice(0,5)){
    const text=cleanMessage(line?.text);if(!text)continue;
    const author=cleanMessage(line.author,100)||"",time=cleanMessage(line.time,30)||"";
    const li=document.createElement("li");li.textContent=author+" · "+time+" — "+text;nodes.push(li);
   }
   list.replaceChildren(...nodes);
   status.textContent="取得済み（"+new Date().toLocaleTimeString()+"）。"+rangeText+(result.more?moreText:"");
  }catch(error){if(panel.isConnected)status.textContent=errorText}
  finally{clearTimeout(timeout);busy=false;button.disabled=false}
 });
}
export function bindIssueBulletin(panel){
 if(!panel)return;
 const api=panel.dataset.api;
 const target=typeof api==="string"&&/^https:\/\/api\.github\.com\/repos\/[A-Za-z0-9][A-Za-z0-9-]{0,38}\/([A-Za-z0-9_.-]{1,100})\/issues\/[1-9][0-9]{0,8}\/comments\?per_page=100$/.exec(api);
 if(!target||target[0]!==api||target[1]==="."||target[1]==="..")return;
 bindBulletin(panel,async(signal,observe)=>{
  const response=await fetch(api,{method:"GET",cache:"no-store",credentials:"omit",redirect:"error",referrerPolicy:"no-referrer",headers:{Accept:"application/vnd.github+json"},signal});
  observe(response.headers);
  if(!response.ok)throw new Error("HTTP "+response.status);
  return {lines:sharedLines(await response.json()), more:response.headers.get("link")?.includes('rel="next"')};
 }, {rangeText:"先頭100コメント内の末尾最大5件、本文60文字。",moreText:"続きはGitHubで確認してください。",errorText:"取得できませんでした（通信・API制限・公開設定を確認）。前回の表示を保持します。"});
}

"""

# Backward-compatible exports for existing world.js consumers.
WORLD_SHARED_JS = ISSUE_BULLETIN_JS + r"""
export function bindSharedBoard(board){bindIssueBulletin(board.querySelector(".ui-board-shared"))}
"""
# ── The shell: a world's header and side, PySaiyanWeBoo's (shell_js: the catalogue with the world's own words, 🌐, the board, the
# menus, the cache), the one a tool page's chrome is made of; then the site's names a world page carries (data-words) join the catalogue.
SHELL_JS = shell_js(WORLD_TEXT, page="") + r"""
if(typeof document!=="undefined")for(const n of document.querySelectorAll('.ui-world-head[data-words]'))addWords(JSON.parse(n.dataset.words),true);
"""
WORLD_JS = WORLD_MOTION_JS + WORLD_SHARED_JS + SHELL_JS + DIAL_JS + r"""/* web-ui world: one page, a camera. Shots: scroll marks light up (data-lit). Map: drag, wheel and pinch move a camera; spots open a sheet. No page changes. */
const clamp=(v,lo,hi)=>Math.min(hi,Math.max(lo,v));
export function fitZoom(w,h,vw,vh){return Math.min(vw/w,vh/h)}
export function travelSeconds(x0,y0,x1,y1,speed){return Math.hypot(x1-x0,y1-y0)/speed}
export function clampFocus(fx,fy,z,w,h,vw,vh){const hw=vw/(2*z),hh=vh/(2*z);return[w>2*hw?clamp(fx,hw,w-hw):w/2,h>2*hh?clamp(fy,hh,h-hh):h/2]}
function bindShots(el){el.dataset.js="";const marks=[...el.querySelectorAll(".ui-shot-mark")];if(typeof IntersectionObserver==="undefined"){marks[0].dataset.lit="";return el}const io=new IntersectionObserver(es=>{for(const e of es){if(e.isIntersecting)e.target.dataset.lit="";else delete e.target.dataset.lit}},{root:el.querySelector(".ui-shots-scroll"),threshold:0.5});for(const m of marks)io.observe(m);return el}
// ⭐ the ★ of a place lists it in the header's ⭐ panel, on any floor. A row is known by its href.
function bindFavs(el,say,kept,save){const favs=el.querySelector('.ui-world-favs');if(!favs)return;const fav=new Set(),rows=()=>[...el.querySelectorAll('.ui-world-spots a')],key=a=>a.dataset.fav||a.getAttribute('href'),
 show=()=>{for(const a of rows()){const on=fav.has(key(a)),b=a.parentElement.querySelector('.ui-world-star');b.setAttribute('aria-pressed',String(on));b.textContent=on?'★':'☆'}
  favs.replaceChildren(...rows().filter(a=>fav.has(key(a))).map(a=>{const li=document.createElement('li'),b=document.createElement('button');b.type='button';b.className='ui-world-star';b.setAttribute('aria-pressed','true');b.dataset.t='star';b.textContent='★';li.append(a.cloneNode(true),b);return li}));say(favs)};
 el.addEventListener('click',e=>{const b=e.target.closest('.ui-world-star');if(!b)return;const h=key(b.parentElement.querySelector('a'));if(fav.has(h))fav.delete(h);else fav.add(h);show();save({fav:[...fav]})});
 for(const a of rows())if(Array.isArray(kept.fav)&&kept.fav.includes(key(a)))fav.add(key(a));if(fav.size)show()}
function bindMap(el){el.dataset.js="";const view=el.querySelector(".ui-world-view"),cam=el.querySelector(".ui-world-cam"),zmax=Number(el.dataset.zoomMax||4),pts=new Map();let fx=0,fy=0,z=1,moved=0,onFloor=()=>{};
// The floor and the category are radios (they work without JS): read the checked floor, tick a floor, or clear the category filter.
const shown=()=>el.querySelector('input[name$="-floor"]:checked'),radio=(kind,value)=>el.querySelector(`input[name$="-${kind}"][value="${value}"]`),
 allCategories=()=>{const all=radio('cat','');if(all)all.checked=true},
 setFloor=(value,notify)=>{const r=radio('floor',value);if(r){r.checked=true;const select=el.querySelector('.ui-world-goto');if(select)select.value=r.value;if(notify)r.dispatchEvent(new Event('change',{bubbles:true}))}};
const floor=()=>{const r=shown();return(r&&el.querySelector(`.ui-floor[data-floor="${r.value}"]`))||el.querySelector(".ui-floor")};
const size=()=>{const f=floor();return[Number(f.dataset.w),Number(f.dataset.h),view.clientWidth,view.clientHeight]};
// Reserve sheet space below the map too: the bottom-edge clamp must not undo the lift.
const sheetInset=()=>{const s=el.querySelector(".ui-sheet");return s&&el.querySelector(".ui-sheet-item[data-open]")?s.offsetHeight+16:0};
const zoomDial=el.querySelector('.ui-world-zoom input[type="range"]');
const apply=()=>{const[w,h,vw,vh]=size();if(!vw||!vh)return;z=clamp(z,fitZoom(w,h,vw,vh),zmax);[fx,fy]=clampFocus(fx,fy,z,w,h+sheetInset()/z,vw,vh);cam.style.setProperty("--fx",fx);cam.style.setProperty("--fy",fy);cam.style.setProperty("--z",z);
 if(zoomDial&&Math.abs(Number(zoomDial.value)-z)>.001){syncing=true;zoomDial.value=z.toFixed(2);zoomDial.dispatchEvent(new Event("input"));syncing=false}onFloor()};
// 🔍 the zoom dial (dial.js) turns the camera; the camera turns the dial back (syncing keeps the two from chasing each other across the clamp).
// 🫥 sets the opacity of the controls over the map (data-overlay).
let syncing=false;bindDial(el);zoomDial?.addEventListener("input",()=>{if(syncing)return;z=Number(zoomDial.value);apply()});
const alpha=el.querySelector("[data-alpha]"),setAlpha=v=>{v=Number(v);if(!(v>=.2&&v<=1))return;el.style.setProperty("--ui-overlay-alpha",v);if(alpha)alpha.value=v};
alpha?.addEventListener("input",()=>{setAlpha(alpha.value);save({alpha:Number(alpha.value)})});
const go=(x,y,zoom)=>{fx=x;fy=y;z=zoom;apply()};
const home=()=>{const[w,h,vw,vh]=size();go(w/2,h/2,vw&&vh?fitZoom(w,h,vw,vh):1)};
const confirmMove=el.dataset.move==='confirm';
if(confirmMove)for(const b of el.querySelectorAll('.ui-world-go'))b.hidden=false;
const open=id=>{for(const i of el.querySelectorAll(".ui-sheet-item"))i.toggleAttribute("data-open",i.id===id);for(const s of el.querySelectorAll(".ui-spot"))s.toggleAttribute("data-selected",Boolean(id)&&s.getAttribute("href")==="#"+id)};
// Side menus (☰ ⋯), the footer pulldown (door to door) and the arrows from the player to each listed spot.
const shut=bindMenus(el),goto=el.querySelector('.ui-world-goto'),rows='.ui-world-rows a';
// The spot the player stands by (the closest within 1.5 tiles) carries data-near: in the dots layer it alone shows its name.
const near=p=>{const f=floor(),t=(Number(f.dataset.tile)||16)*1.5;let best=null,bd=Infinity;for(const a of f.querySelectorAll(".ui-spot[data-x]")){const d=Math.max(Math.abs(Number(a.dataset.x)-p[0]),Math.abs(Number(a.dataset.y)-p[1]));if(d<=t&&d<bd){best=a;bd=d}}for(const a of f.querySelectorAll(".ui-spot[data-near]"))if(a!==best)a.removeAttribute("data-near");if(best&&!best.hasAttribute("data-near"))best.setAttribute("data-near","")};
const aim=p=>{near(p);for(const a of el.querySelectorAll(rows)){if(!a.offsetParent)continue;const out=a.querySelector('.ui-world-arrow'),f=floor(),g=a.dataset.floor===f.dataset.floor?direction(p,[Number(a.dataset.x),Number(a.dataset.y)],Number(f.dataset.tile)||16):'🛗';if(out.textContent!==g)out.textContent=g}if(goto){const r=shown();if(r&&goto.value!==r.value)goto.value=r.value}};
// While a sheet is open the camera aims below the player or the spot, so they stay in the view above the sheet.
const lift=()=>sheetInset()/(2*z);
let follow=false,lx,ly;const walk=bindPlayer(el,floor,p=>{if(follow&&(p[0]!==lx||p[1]!==ly)){lx=p[0];ly=p[1];go(p[0],p[1]+lift(),z)}aim(p)});
view.addEventListener('pointerdown',shut);
// ⭐ favourites, 🌐 language and 🏷️ the name layer are all a world keeps, as a small cache in this browser (one key per world, nothing else is written):
// the emoji you pick and the board messages you post stay in the page.
const slot='ui-world:'+el.id,[loadLocal,saveLocal]=stored(slot),unified=el.closest('[data-world-shell]');
const [readStars,saveStars]=stored('portfolio-world:favorites/1');
const load=()=>{const state=loadLocal(),all=unified&&readStars();
 if(!all)return state;
 if(Array.isArray(all[el.id]))return {...state,fav:all[el.id]};
 if(Array.isArray(state.fav))saveStars({[el.id]:state.fav});
 return state};
const save=patch=>{if(unified&&Array.isArray(patch.fav)){
 const {fav,...other}=patch;saveStars({[el.id]:fav});
 if(Object.keys(other).length)saveLocal(other);
 }else saveLocal(patch)};
// 🌐: aria-labels and tooltips in one of eleven languages (data-t names a catalogue word, data-labels carries a tool's own words).
let lang='ja';const sel=el.querySelector('[data-lang]'),
 say=root=>sayIn(root,lang),
 around=n=>!n.closest('[data-ui-world]')?.querySelector('[data-lang]'),   // the page around the scenes (the switcher, the way back, the site's foot) and a scene without a 🌐 of its own
 setLang=to=>{if(!CHROME_LANGS.includes(to))return;lang=to;el.lang=to;if(sel)sel.value=to;say(el);sayIn(document.body,to,around);sayAround(to,around)};
sel?.addEventListener('change',()=>{setLang(sel.value);save({lang})});
// 🎒 items collected from spots (kept in localStorage beside fav, lang, names, alpha).
const spotRows=()=>[...el.querySelectorAll('.ui-world-spots a')],bagList=el.querySelector('.ui-world-bag'),bag=new Set(),takeBtns=()=>[...el.querySelectorAll('.ui-sheet-item .ui-world-take')],
 showBag=()=>{for(const b of takeBtns()){const on=bag.has(b.dataset.itemId);b.setAttribute('aria-pressed',String(on));b.querySelector('.ui-world-take-mark').textContent=on?'✓':'＋'}
  if(!bagList)return;
  bagList.replaceChildren(...takeBtns().filter(b=>bag.has(b.dataset.itemId)).map(b=>{
   const id=b.dataset.itemId,src=spotRows().find(a=>a.getAttribute('href')==='#'+id),li=document.createElement('li');
   const a=src?src.cloneNode(true):document.createElement('a');
   if(!src)a.href='#'+id;
   a.lastChild.textContent=b.dataset.itemEmoji+' '+b.dataset.itemLabel;
   const rm=document.createElement('button');rm.type='button';rm.className='ui-world-bag-rm ui-world-take';rm.dataset.itemId=id;rm.setAttribute('aria-pressed','true');rm.dataset.t='take';rm.textContent='✕';
   li.append(a,rm);return li}));say(bagList)};
if(bagList){for(const b of takeBtns())b.hidden=false;
 el.addEventListener("world-restore-bag",e=>{
  bag.clear();for(const id of e.detail)bag.add(id);showBag();save({bag:[...bag]});
 });
 el.addEventListener('click',e=>{const b=e.target.closest('.ui-world-take');if(!b)return;const id=b.dataset.itemId;if(bag.has(id))bag.delete(id);else bag.add(id);showBag();save({bag:[...bag]})})}
const kept=load();
bindFavs(el,say,kept,save);
if(bagList){for(const b of takeBtns())if(Array.isArray(kept.bag)&&kept.bag.includes(b.dataset.itemId))bag.add(b.dataset.itemId);if(bag.size)showBag()}
if(typeof kept.lang==='string'&&kept.lang!=='ja')setLang(kept.lang);
// 🏷️ the name layer (names / dots / off) switches without a reload and is kept with the language.
const namesPick=el.querySelector('[data-names-pick]'),setNames=to=>{if(!['names','dots','off'].includes(to))return;el.dataset.names=to;if(namesPick)namesPick.value=to};
if(typeof kept.names==='string')setNames(kept.names);
if(typeof kept.alpha==='number')setAlpha(kept.alpha);
namesPick?.addEventListener('change',()=>{setNames(namesPick.value);save({names:namesPick.value})});
goto?.addEventListener('change',()=>setFloor(goto.value,true));
// Emoji picker: shown first (JS only); the choice replaces every floor's player emoji. Dragging the map stops the camera following.
const pick=el.querySelector('.ui-world-pick'),showPick=on=>{pick.hidden=!on;el.toggleAttribute('data-pick',on)},choose=g=>{for(const s of el.querySelectorAll('.ui-player span'))s.textContent=g;showPick(false);follow=true;view.focus({preventScroll:true})};
if(pick){showPick(true);pick.addEventListener('click',e=>{const b=e.target.closest('[data-emoji]');if(b)choose(b.dataset.emoji)});pick.querySelector('form').addEventListener('submit',e=>{e.preventDefault();const box=e.target.elements.emoji,g=cleanAvatar(box.value);if(g)choose(g);else{box.setCustomValidity(chromeWord(lang,'invalid'));box.reportValidity()}});pick.querySelector('input').addEventListener('input',e=>e.target.setCustomValidity(''));el.querySelector('[data-pick-open]')?.addEventListener('click',()=>showPick(true))}
// ask(glyph,choices,t): the world's one dialog for choosing or confirming. Icons in, the picked value out (a promise; null = ✖️, Esc or a tap outside).
// A choice is {glyph,t,value} with t naming a catalogue word; el.ask lets the page that embeds the world call it too.
let asking=null;
const ask=(glyph,choices,t)=>new Promise(done=>{asking?.(null);const box=document.createElement('div'),card=document.createElement('div'),head=document.createElement('h3'),grid=document.createElement('div');
 box.className='ui-world-pick ui-world-ask';card.setAttribute('role','dialog');card.setAttribute('aria-modal','true');if(t)card.dataset.t=t;
 head.setAttribute('aria-hidden','true');head.textContent=glyph;grid.className='ui-world-pick-grid';
 const end=v=>{asking=null;box.remove();el.removeAttribute('data-ask');view.focus({preventScroll:true});done(v)};
 for(const c of[...choices,{glyph:'✖️',t:'close',value:null}]){const b=document.createElement('button');b.type='button';b.textContent=c.glyph;b.dataset.t=c.t;b.addEventListener('click',()=>end(c.value));grid.append(b)}
 box.addEventListener('click',e=>{if(e.target===box)end(null)});box.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();end(null)}});
 card.append(head,grid);box.append(card);(pick?pick.parentElement:view.parentElement).append(box);say(box);el.setAttribute('data-ask','');asking=end;grid.querySelector('button').focus()});
el.ask=ask;
// 🖼️📷 a floor marked real can show a photo you pick or your camera behind its props. It is only shown (an object URL or a camera stream on an element of this page):
// never drawn, read back, stored or sent. 🧹, leaving the floor (camera) or closing the page lets it go.
const realBtn=el.querySelector('[data-real]'),file=realBtn&&document.createElement('input');
let back=null,lastFloor=null;
const unback=()=>{if(!back)return;back.stop();back.node.remove();back.floor.removeAttribute('data-backdrop');back=null},
 backdrop=(node,stop,live)=>{unback();const f=floor();node.className='ui-real';node.setAttribute('aria-hidden','true');f.prepend(node);f.setAttribute('data-backdrop','');back={node,stop,live,floor:f}},
 syncReal=()=>{const f=floor();if(f===lastFloor)return;lastFloor=f;if(realBtn)realBtn.hidden=!f.hasAttribute('data-real');if(back&&back.live&&back.floor!==f)unback()},
 camera=async()=>{try{const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'environment'},audio:false}),v=document.createElement('video');v.muted=true;v.autoplay=true;v.playsInline=true;v.srcObject=stream;
  backdrop(v,()=>{for(const t of stream.getTracks())t.stop();v.srcObject=null},true);v.play?.().catch(()=>{})}catch(e){ask('⚠️',[],'unavailable')}};
if(file){file.type='file';file.accept='image/*';file.hidden=true;el.append(file);
 file.addEventListener('change',()=>{const f=file.files[0];file.value='';if(!f||!f.type.startsWith('image/'))return;const url=URL.createObjectURL(f),img=new Image();img.alt='';img.draggable=false;img.src=url;backdrop(img,()=>URL.revokeObjectURL(url),false)})}
realBtn?.addEventListener('click',()=>{shut();ask('🖼️📷',[{glyph:'📷',t:'camera',value:'camera'},{glyph:'🖼️',t:'photo',value:'photo'},...(back?[{glyph:'🧹',t:'clear',value:'clear'}]:[])],'backdrop').then(v=>{if(v==='camera')camera();else if(v==='photo')file.click();else if(v==='clear')unback()})});
addEventListener('pagehide',unback);onFloor=syncReal;syncReal();
el.querySelector('[data-me]')?.addEventListener('click',()=>{const p=walk.where?.();if(p){follow=true;lx=ly=undefined;go(p[0],p[1],Math.max(z,2))}});

// A world's board also takes the lines a visitor posts (kept in the page) and, opted in, the shared section.
const board=el.querySelector(".ui-board");if(board){const{tick,clockNow}=bindBoard(board);bindSharedBoard(board);const form=board.querySelector(".ui-board-post");if(form){
const run=board.querySelector(".ui-board-run"),items=[...run.querySelectorAll(".ui-board-item")],base=items.slice(0,items.length/2).map(n=>n.cloneNode(true)),baseChars=Number(board.dataset.chars),notes=[];
form.addEventListener("submit",e=>{e.preventDefault();const input=form.elements.message,text=cleanMessage(input.value);if(!text)return;input.value="";notes.unshift({text,at:clockNow().clock.slice(0,5)});notes.splice(5);run.replaceChildren();
for(const hidden of [false,true]){for(const note of notes){const span=document.createElement("span");span.className="ui-board-item ui-board-note";if(hidden)span.setAttribute("aria-hidden","true");const stamp=document.createElement("span");stamp.className="ui-board-stamp";stamp.textContent=note.at;span.append(stamp,document.createTextNode(" "+note.text));run.append(span)}for(const item of base){const copy=item.cloneNode(true);if(hidden)copy.setAttribute("aria-hidden","true");run.append(copy)}}
const chars=baseChars+notes.reduce((n,note)=>n+[...note.text].length+6,0);board.dataset.chars=chars;run.style.animationDuration=boardSeconds(chars)+"s";tick()})}}
// 🏠 asks first (the shared dialog: 🏠 goes, ✖️ stays): home resets the floor, the filter and the sheet.
const goHome=()=>{shut();close();follow=false;allCategories();setFloor(el.querySelector('input[name$="-floor"]')?.value,true);home()};
el.querySelector('[data-home]')?.addEventListener('click',e=>{e.preventDefault();shut();ask('🏠❓',[{glyph:'🏠',t:'home',value:true}],'home').then(v=>{if(v)goHome()})});
const close=()=>{open(null);apply();if([...el.querySelectorAll(".ui-sheet-item")].some(i=>"#"+i.id===location.hash))history.replaceState(null,"",location.pathname+location.search+(unified?.dataset.worldRoute?'#'+unified.dataset.worldRoute:''))};
const focusSpot=a=>{allCategories();setFloor(a.closest(".ui-floor").dataset.floor);const zoom=Math.max(z,2);go(Number(a.dataset.x),Number(a.dataset.y)+lift()*z/zoom,zoom)};
view.addEventListener("pointerdown",e=>{if(e.button!==0)return;pts.set(e.pointerId,[e.clientX,e.clientY]);if(pts.size===1)moved=0;else moved=9;el.dataset.drag=""});
view.addEventListener("pointermove",e=>{const p=pts.get(e.pointerId);if(!p)return;if(pts.size===1){const dx=e.clientX-p[0],dy=e.clientY-p[1];moved+=Math.abs(dx)+Math.abs(dy);if(moved>8){follow=false;if(!view.hasPointerCapture(e.pointerId))view.setPointerCapture(e.pointerId)}fx-=dx/z;fy-=dy/z;apply()}else if(pts.size===2){const q=[...pts].find(([id])=>id!==e.pointerId)[1],d0=Math.hypot(p[0]-q[0],p[1]-q[1]),d1=Math.hypot(e.clientX-q[0],e.clientY-q[1]);moved+=9;if(d0)z*=d1/d0;apply()}p[0]=e.clientX;p[1]=e.clientY});
const end=e=>{const tapping=pts.has(e.pointerId)&&pts.size===1&&moved<=8&&e.type==="pointerup"&&view.contains(e.target)&&!e.target.closest("a,button,input");pts.delete(e.pointerId);if(!pts.size)delete el.dataset.drag;if(tapping&&walk&&!confirmMove){const f=floor(),r=f.getBoundingClientRect();walk((e.clientX-r.left)*Number(f.dataset.w)/r.width,(e.clientY-r.top)*Number(f.dataset.h)/r.height)}};
addEventListener("pointerup",end);addEventListener("pointercancel",end);view.addEventListener("lostpointercapture",end);
view.addEventListener("wheel",e=>{e.preventDefault();z*=e.deltaY<0?1.1:1/1.1;apply()},{passive:false});
el.addEventListener("click",e=>{const g=e.target.closest(".ui-world-go");if(g){e.preventDefault();shut();close();setFloor(g.dataset.goFloor);follow=true;lx=ly=undefined;walk(Number(g.dataset.goX),Number(g.dataset.goY));return}const l=e.target.closest(".ui-world-rows a"),a=l?[...el.querySelectorAll(".ui-spot")].find(s=>s.getAttribute("href")===l.getAttribute("href")):e.target.closest(".ui-spot,.ui-actor");if(e.target.closest(".ui-world-rows a,[data-me],[data-pick-open]"))shut();if(a){e.preventDefault();if(l)moved=0;if(e.detail!==0&&moved>8){moved=0;return}const id=a.getAttribute("href").slice(1);if(!l){const sg=a.dataset.sign!==undefined,two=a.dataset.flip;if(sg||two!==undefined){if(a.dataset.own===undefined)a.dataset.own=a.textContent;const cur=a.dataset.show||(sg?"":"label"),next=sg?(cur===""?"label":cur==="label"&&two?"flip":""):(cur==="label"?"flip":"label");if(next)a.dataset.show=next;else delete a.dataset.show;a.textContent=next==="flip"?two:a.dataset.own}}open(id);history.replaceState(null,"","#"+id);if(unified)unified.dispatchEvent(new Event("world-location"));if(a.dataset.x!==undefined){focusSpot(a);if(!confirmMove)walk(Number(a.dataset.x),Number(a.dataset.y))}}else if(e.target.closest(".ui-sheet-close")){e.preventDefault();close()}});
const KEYS={ArrowUp:[0,-1],w:[0,-1],ArrowDown:[0,1],s:[0,1],ArrowLeft:[-1,0],a:[-1,0],ArrowRight:[1,0],d:[1,0]};
el.addEventListener("keydown",e=>{if(e.key==="Escape"){close();shut()}const k=KEYS[e.key.length>1?e.key:e.key.toLowerCase()];if(k&&walk.step&&!(e.altKey||e.ctrlKey||e.metaKey)&&!e.target.closest("input,textarea,select,button,a")&&!el.hasAttribute("data-pick")&&!el.hasAttribute("data-ask")&&walk.step(...k))e.preventDefault()});
el.addEventListener("change",e=>{if(e.target.name&&e.target.name.endsWith("-floor"))home()});
if(typeof ResizeObserver!=="undefined")new ResizeObserver(apply).observe(view);
const fromHash=()=>{const hash=location.hash.slice(1),a=hash&&el.querySelector(`.ui-spot[href="#${CSS.escape(hash)}"],.ui-actor[href="#${CSS.escape(hash)}"]`);if(a){open(hash);if(a.dataset.x!==undefined)focusSpot(a)}else open(null)};
addEventListener("hashchange",fromHash);home();fromHash();
return el}
export function bindWorlds(root=document){return[...root.querySelectorAll("[data-ui-world]")].map(el=>el.hasAttribute("data-js")?el:el.dataset.uiWorld==="shots"?bindShots(el):bindMap(el))}
globalThis.webUiWorld={fitZoom,clampFocus,travelSeconds,minutesUntil,boardClock,boardSeconds,bindBoard,gaugeState,gaugeCells,clockLabel,utcOffsetLabel,zoneOffset,cleanMessage,motionWalk,motionSample,motionRoute,routeSample,gridPath,gridRoute,direction,cleanAvatar,bindWorlds};
bindWorlds();
"""

EXPLORATION_SCROLL = {
    "id": "meadow-drop-scroll",
    "label": "探索の巻物",
    "reusable": True,
    "field": {"context": "移動中", "target": "未取得のどうぐ", "radius_tiles": 6, "duration_seconds": 3},
    "battle": {"context": "戦闘中", "target": "やくそう", "item_id": "meadow-drop-herb",
               "chance_percent": 30, "quantity": 1, "uses_turn": True},
}


def exploration_scroll_text() -> dict[str, str]:
    field, battle = EXPLORATION_SCROLL["field"], EXPLORATION_SCROLL["battle"]
    field_text = (f'{field["context"]}は同じ階の{field["radius_tiles"]}マス以内にある'
                  f'{field["target"]}が{field["duration_seconds"]}秒間光ります。')
    turn = "1ターン使い、" if battle["uses_turn"] else "ターンを使わず、"
    battle_text = (f'{battle["context"]}は{turn}{battle["chance_percent"]}%の確率で'
                   f'{battle["target"]}を{battle["quantity"]}個拾います。')
    return {"field": field_text, "battle": battle_text,
            "reuse": "何度でも使えます。" if EXPLORATION_SCROLL["reusable"] else "使うと巻物を消費します。"}


WORLD_RPG_JS = r"""
export const RPG_LEVEL_THRESHOLDS=[0,30,75,140,230,350,500,700,950,1250];
const DEFAULT_ORBS={attack:["🔥","💧","🌳","💡","🔮"],heal:["❤️","💚","✨"],max:6};
export function rpgRandomWord(seed){let x=(Number(seed)>>>0)||0x6D2B79F5;x^=(x<<13);x>>>=0;x^=(x>>>17);x^=(x<<5);return x>>>0}
export function rpgOrbEffect(amount,heal=false,orbs=DEFAULT_ORBS){
 const amt=Math.max(0,Math.floor(Number(amount)||0));
 if(amt===0)return{counter:0,amount:0,heal:false,idle:true,orbs:[],label:"Orbs ready…"};
 const pal=heal?(orbs?.heal||DEFAULT_ORBS.heal):(orbs?.attack||DEFAULT_ORBS.attack),max=Math.max(1,Math.floor(Number(orbs?.max)||6)),n=Math.min(Math.max(amt,1),max);
 return{counter:heal?-amt:amt,amount:amt,heal:Boolean(heal),idle:false,orbs:Array.from({length:n},(_,i)=>pal[i%pal.length]),label:heal?`💚 Heal ${amt}`:`💥 Damage ${amt}`};
}
export function rpgLevelForExp(exp){
 const xp=Math.max(0,Math.floor(Number(exp)||0));let lv=1;
 for(let i=0;i<RPG_LEVEL_THRESHOLDS.length;i++)if(xp>=RPG_LEVEL_THRESHOLDS[i])lv=i+1;
 const next=lv<RPG_LEVEL_THRESHOLDS.length?RPG_LEVEL_THRESHOLDS[lv]:RPG_LEVEL_THRESHOLDS[RPG_LEVEL_THRESHOLDS.length-1];
 return{level:lv,exp:xp,next_exp:next,bonus_hp:(lv-1)*6,bonus_mp:(lv-1)*3,bonus_atk:(lv-1)*2,bonus_def:(lv-1)*1};
}
export function rpgDamage(atk,defense,rollWord,{multPct=100,guarding=false,critPct=12}={}){
 const w=Number(rollWord)>>>0,crit=(w%100)<critPct,variance=((w>>>8)%3)-1;
 let raw=Math.max(1,Math.floor((atk*multPct)/100)-Math.floor(defense/2)+variance);
 if(crit)raw=Math.max(2,Math.floor((raw*3)/2));
 if(guarding)raw=Math.max(1,Math.floor(raw/2));
 return{damage:raw,crit,effect:rpgOrbEffect(raw)};
}
function rpgEl(tag,props={},...kids){
 const node=document.createElement(tag);
 for(const[k,v]of Object.entries(props)){
  if(v===undefined||v===null)continue;
  if(k==="className")node.className=v;
  else if(k==="hidden")node.hidden=Boolean(v);
  else if(k==="disabled")node.disabled=Boolean(v);
  else if(k.startsWith("data-"))node.setAttribute(k,String(v));
  else if(k.startsWith("aria-"))node.setAttribute(k,String(v));
  else node[k]=v;
 }
 node.append(...kids.filter(c=>c!==undefined&&c!==null));
 return node;
}
export function bindWorldRpg(el){
 if(el.hasAttribute("data-rpg-bound"))return el;
 const dataEl=el.querySelector(".ui-rpg-data");if(!dataEl)return el;
 let rpg=null;try{rpg=JSON.parse(dataEl.textContent)}catch{return el}
 el.setAttribute("data-rpg-bound","");
 const wid=el.id.replace(/-map$/,""),hud=el.querySelector(".ui-rpg-hud");
 if(hud)hud.hidden=false;
 const overlay=rpgEl("div",{className:"ui-rpg-overlay",hidden:true}),toast=rpgEl("div",{className:"ui-rpg-toast",hidden:true,"aria-live":"polite"});
 el.append(overlay,toast);
 let toastTimer=0;
 const showToast=msg=>{toast.textContent=msg;toast.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>{toast.hidden=true},3200)};
 const state={
  exp:0,hp:rpg.hero.hp,mp:rpg.hero.mp,gold:rpg.hero.gold,seed:rpg.seed>>>0||20261126,
  talked:new Set(),looted:new Set(),defeated:new Set(),quizSolved:new Set(),quizIdx:0,
  visitedFloors:new Set([el.querySelector("input[name$='-floor']:checked")?.value||"meadow"]),
  consumables:new Map(),equipment:new Set(),completedQuests:new Set(),badges:new Set(),
  boughtCount:0,healedCount:0,dragonExp:0,fireX:0,fireY:0,dragonHue:0,dragonFill:0,dragonScroll:0,topic1:0,topic2:0,topic3:0
 };
 const equipIds=()=>[...state.equipment];
 const equipBonus=()=>equipIds().reduce((acc,sid)=>{const it=rpg.loot[sid];if(!it)return acc;acc.hp+=it.hp;acc.mp+=it.mp;acc.atk+=it.atk;acc.def+=it.def;return acc},{hp:0,mp:0,atk:0,def:0});
 const stats=()=>{const lv=rpgLevelForExp(state.exp),eq=equipBonus();return{lv,maxHp:rpg.hero.hp+lv.bonus_hp+eq.hp,maxMp:rpg.hero.mp+lv.bonus_mp+eq.mp,atk:rpg.hero.atk+lv.bonus_atk+eq.atk,def:rpg.hero.def+lv.bonus_def+eq.def}};
 const clampVitals=()=>{const st=stats();state.hp=Math.min(Math.max(0,state.hp),st.maxHp);state.mp=Math.min(Math.max(0,state.mp),st.maxMp)};
 const nextRoll=()=>{state.seed=rpgRandomWord(state.seed);return state.seed};
 const spotNode=sid=>el.querySelector(`.ui-spot[href="#${CSS.escape(wid+"-spot-"+sid)}"],.ui-actor[href="#${CSS.escape(wid+"-spot-"+sid)}"]`);
 const spotMeta=sid=>{
  const node=spotNode(sid),art=document.getElementById(wid+"-spot-"+sid);
  const label=node?.textContent?.trim()||art?.querySelector("h3")?.textContent?.trim()||sid;
  const take=art?.querySelector(".ui-world-take");
  return{node,art,label,emoji:take?.dataset.itemEmoji||"🎒",itemLabel:take?.dataset.itemLabel||label,take};
 };
 // Both formats use the same v1 named fields. Zero flags are omitted from JSON.
 const scalarWidths={exp:24,gold:24,hp:12,mp:12,seed:32,quizIdx:8,boughtCount:16,healedCount:16};
 const bagButtons=[...el.querySelectorAll(".ui-sheet-item .ui-world-take")];
 const groups={
  talked:Object.keys(rpg.npcs),looted:Object.keys(rpg.loot),defeated:Object.keys(rpg.enemies),
  quizSolved:rpg.quizzes.map(q=>q.prompt),visitedFloors:[...el.querySelectorAll("input[name$='-floor']")].map(b=>b.value),
  completedQuests:rpg.quests.map(q=>q.id),badges:rpg.badges.map(b=>b.id),
  bag:bagButtons.map(b=>b.dataset.itemId)
 };
 const stock=new Map();
 for(const [id,it] of Object.entries(rpg.loot))if(it.consumable){
  const meta=spotMeta(id);
  stock.set("spot:"+id,{...it,spotId:id,emoji:meta.emoji,label:meta.itemLabel});
 }
 for(const it of rpg.shop)stock.set("shop:"+it.id,{...it,atk:0});
 const flags=Object.entries(groups).flatMap(([group,ids])=>[...new Set(ids)].sort().map(id=>[group,id,group+":"+id]));
 const layout=[["version",8],["catalogue",32],...Object.entries(scalarWidths),
  ...flags.map(([,,key])=>[key,1]),...[...stock.keys()].sort().map(key=>[key,key.startsWith("spot:")?1:12])];
 // Bind positional spells to this world and layout, even across same-length catalogue edits.
 const extraWidths={dragonExp:16,fireX:16,fireY:16};
 const extendedLayout=[...layout,...Object.entries(extraWidths)];
 const layouts=[null,layout,extendedLayout,[...extendedLayout,["dragonHue",2],["dragonFill",25]]];
 // Stored topic IDs are append-only. Slot 1 is the most recent exchange.
 const topics=["","昼ヶ丘","サツマイモ","ドラゴン","木の看板","リバースロンドン","癒しの水","火","パリ","MP","冒険手帳","復活の呪文","竜の巻物","探索の巻物","敵","未取得のどうぐ","やくそう"];
 const memoryKeys=["topic1","topic2","topic3"];
 const remember=name=>{
  state.topic3=state.topic2;state.topic2=state.topic1;state.topic1=Math.max(0,topics.indexOf(name));
 };
 layouts.push([...layouts[3],["dragonScroll",1],...memoryKeys.map(key=>[key,8])]);
 const scrollKey="spot:"+explorationScroll.id,herbKey="found:herb";
 const herb=stock.get("spot:"+explorationScroll.battle.item_id);
 if(herb)stock.set(herbKey,{...herb,spotId:null});
 layouts.push([...layouts[4],[herbKey,12]]);
 const optionalKeys=[...Object.keys(extraWidths),"dragonHue","dragonFill","dragonScroll",...memoryKeys];
 const catalogue=async(fields)=>new DataView(await crypto.subtle.digest("SHA-256",
  new TextEncoder().encode(JSON.stringify([wid,fields])))).getUint32(0);
 const snapshot=()=>{
  const data=Object.fromEntries(Object.keys(scalarWidths).map(k=>[k,state[k]]));
  const bag=new Set(bagButtons.filter(b=>b.getAttribute("aria-pressed")==="true").map(b=>b.dataset.itemId));
  for(const [group,id,key] of flags)if((group==="bag"?bag:state[group]).has(id))data[key]=1;
  for(const [key,it] of state.consumables)data[key]=it.count;
  for(const key of optionalKeys)if(state[key])data[key]=state[key];
  return data;
 };
 const restore=(data,version)=>{
  const invalid=()=>{throw new Error("invalid save")};
  if(!data||typeof data!=="object"||Array.isArray(data))invalid();
  const known=new Set(layouts[version].slice(2).map(([key])=>key));
  for(const [key,n] of Object.entries(data))if(!known.has(key)||!Number.isSafeInteger(n)||n<0)invalid();
  const next={consumables:new Map(),equipment:new Set()};
  for(const key of Object.keys(scalarWidths)){
   if(!Object.hasOwn(data,key))invalid();
   next[key]=data[key];
  }
  for(const key of optionalKeys)next[key]=data[key]??0;
  if(next.dragonScroll>1||memoryKeys.some(key=>next[key]>=topics.length))invalid();
  if(next.dragonHue>3||next.dragonFill>0x1000000)invalid();
  if(Boolean(next.fireX)!==Boolean(next.fireY)||next.fireX>65535||next.fireY>65535)invalid();
  if(next.fireX&&fires.length&&!fires.some(f=>atSavedFire(f,next)))invalid();
  if(next.seed>0xffffffff||next.quizIdx>=Math.max(1,rpg.quizzes.length))invalid();
  for(const group of Object.keys(groups))next[group]=new Set();
  for(const [group,id,key] of flags){
   if(data[key]>1)invalid();
   if(data[key])next[group].add(id);
  }
  for(const id of next.looted)if(!rpg.loot[id].consumable)next.equipment.add(id);
  for(const [key,item] of stock)if(data[key]){
   if(item.spotId&&(!next.looted.has(item.spotId)||data[key]!==1))invalid();
   next.consumables.set(key,{...item,key,count:data[key]});
  }
  if(explorationScroll.reusable&&stock.has(scrollKey)&&next.looted.has(explorationScroll.id)){
   const key=scrollKey,item=stock.get(key);
   next.consumables.set(key,{...item,key,count:1});
   next.bag.add(wid+"-spot-"+item.spotId);
  }
  const {bag,...adventure}=next;
  Object.assign(state,adventure);
  syncCityItems();syncDragon?.();
  el.dispatchEvent(new CustomEvent("world-restore-bag",{detail:bag}));
  renderHud();
 };
 const syncSpotMarks=()=>{
  for(const[sid,it]of Object.entries(rpg.loot)){
   const node=spotNode(sid);if(!node)continue;
   const got=state.looted.has(sid);
   if(it.kind==="chest"){node.toggleAttribute("data-rpg-opened",got);if(it.opened_mark){node.dataset.closedLabel??=node.textContent;node.textContent=got?node.dataset.closedLabel.replace("🎁",it.opened_mark):node.dataset.closedLabel}}
   else node.toggleAttribute("data-rpg-collected",got);
  }
  for(const[sid,foe]of Object.entries(rpg.enemies)){
   const node=spotNode(sid);if(!node)continue;
   node.toggleAttribute("data-rpg-boss",Boolean(foe.boss));
   node.toggleAttribute("data-rpg-defeated",state.defeated.has(sid));
  }
 };
 const renderHud=()=>{
  if(searchButton)searchButton.hidden=!state.consumables.has(scrollKey);
  clampVitals();if(!hud)return;
  const st=stats(),heroGlyph=el.querySelector(".ui-player span")?.textContent||"🧙";
  const qDone=state.completedQuests.size,qTotal=rpg.quests.length;
  hud.querySelector("[data-rpg-hero]").textContent=`${heroGlyph} Lv.${st.lv.level}`;
  hud.querySelector("[data-rpg-hp]").textContent=`❤️ ${state.hp}/${st.maxHp}`;
  hud.querySelector("[data-rpg-hp-bar]").style.width=`${Math.round(100*state.hp/Math.max(1,st.maxHp))}%`;
  hud.querySelector("[data-rpg-mp]").textContent=`💧 ${state.mp}/${st.maxMp}`;
  hud.querySelector("[data-rpg-mp-bar]").style.width=`${Math.round(100*state.mp/Math.max(1,st.maxMp))}%`;
  hud.querySelector("[data-rpg-exp]").textContent=`✨ ${state.exp}/${st.lv.next_exp}`;
  hud.querySelector("[data-rpg-gold]").textContent=`🪙 ${state.gold}G`;
  hud.querySelector("[data-rpg-gear]").textContent=`⚔️ ${st.atk} 🛡️ ${st.def}`;
  hud.querySelector("[data-rpg-qcount]").textContent=`${qDone}/${qTotal}`;
  syncSpotMarks();
 };
 const questProgress=q=>{
  if(q.kind==="talk")return q.target?(state.talked.has(q.target)?1:0):state.talked.size;
  if(q.kind==="drop")return q.target?(state.looted.has(q.target)?1:0):Object.entries(rpg.loot).filter(([id,v])=>v.kind==="drop"&&state.looted.has(id)).length;
  if(q.kind==="chest")return q.target?(state.looted.has(q.target)?1:0):Object.entries(rpg.loot).filter(([id,v])=>v.kind==="chest"&&state.looted.has(id)).length;
  if(q.kind==="battle"||q.kind==="boss")return q.target?(state.defeated.has(q.target)?1:0):state.defeated.size;
  if(q.kind==="item")return q.target?(state.looted.has(q.target)?1:0):(state.looted.size+state.boughtCount);
  if(q.kind==="quiz")return state.quizSolved.size;
  if(q.kind==="floor")return q.target?(state.visitedFloors.has(q.target)?1:0):state.visitedFloors.size;
  return 0;
 };
 const evalBadges=()=>{
  const checks={
   "first-talk":state.talked.size>=1,
   "villager-friends":Object.keys(rpg.npcs).filter(id=>id.startsWith("meadow-npc")).every(id=>state.talked.has(id))||state.talked.size>=4,
   "item-finder":state.looted.size>=1,
   "treasure-hunter":Object.entries(rpg.loot).filter(([id,v])=>v.kind==="chest"&&state.looted.has(id)).length>=3,
   "first-win":state.defeated.size>=1,
   "boss-slayer":Object.entries(rpg.enemies).some(([id,e])=>e.boss&&state.defeated.has(id)),
   "quiz-ace":state.quizSolved.size>=2,
   "world-walker":state.visitedFloors.size>=3,
   "level-up":rpgLevelForExp(state.exp).level>=2,
   shopper:state.boughtCount>=1
  };
  for(const b of rpg.badges){
   if(!state.badges.has(b.id)&&checks[b.id]){state.badges.add(b.id);showToast(`🏅 実績解除: ${b.emoji} ${b.label}`)}
  }
 };
 const gainExp=amount=>{
  if(!amount)return false;
  const before=rpgLevelForExp(state.exp).level;
  state.exp+=amount;
  const after=rpgLevelForExp(state.exp);
  if(after.level>before){const st=stats();state.hp=st.maxHp;state.mp=st.maxMp;return after.level}
  return false;
 };
 const checkQuests=()=>{
  for(const q of rpg.quests){
   if(state.completedQuests.has(q.id))continue;
   if(questProgress(q)>=q.count){
    state.completedQuests.add(q.id);
    const lvUp=gainExp(q.reward_exp);state.gold+=q.reward_gold;
    showToast(`📜 クエスト達成「${q.title}」 +${q.reward_exp}EXP +${q.reward_gold}G${lvUp?` 🎉Lv.${lvUp}!`:""}`);
   }
  }
  evalBadges();renderHud();
 };
 const addLoot=sid=>{
  const entry=rpg.loot[sid];if(!entry||state.looted.has(sid))return false;
  state.looted.add(sid);
  const meta=spotMeta(sid);
  if(meta.take&&meta.take.getAttribute("aria-pressed")!=="true")meta.take.click();
  if(entry.consumable){
   const key="spot:"+sid,cur=state.consumables.get(key)||{key,spotId:sid,emoji:meta.emoji,label:meta.itemLabel,item_type:entry.item_type,hp:entry.hp,mp:entry.mp,atk:entry.atk,count:0};
   cur.count+=1;state.consumables.set(key,cur);
  }else{
   state.equipment.add(sid);
   const st=stats();state.hp=Math.min(st.maxHp,state.hp+entry.hp);state.mp=Math.min(st.maxMp,state.mp+entry.mp);
  }
  state.gold+=entry.gold;
  const lvUp=gainExp(entry.exp);
  checkQuests();
  return{lvUp,meta,entry};
 };
 const consume=key=>{
  const item=state.consumables.get(key);if(!item||item.count<=0)return null;
  item.count-=1;
  if(item.count===0){
   state.consumables.delete(key);
   if(item.spotId){const meta=spotMeta(item.spotId);if(meta.take&&meta.take.getAttribute("aria-pressed")==="true")meta.take.click()}
  }
  return item;
 };
 const shell=el.closest("[data-world-shell]");
 let clearScan=0,searchButton;
 const scanItems=()=>{
  const scene=shell?.querySelector("[data-world-space]:not([hidden])")||el;
  const floorId=scene.querySelector("input[name$='-floor']:checked")?.value;
  const floor=floorId&&scene.querySelector(`.ui-floor[data-floor="${CSS.escape(floorId)}"]`),player=floor?.querySelector(".ui-player");
  const root=shell||el;
  const clear=()=>root.querySelectorAll("[data-scroll-found]").forEach(n=>n.removeAttribute("data-scroll-found"));
  clearTimeout(clearScan);clear();
  const names=[];
  if(player){
   const x=parseFloat(player.style.getPropertyValue("--px")),y=parseFloat(player.style.getPropertyValue("--py")),radius=explorationScroll.field.radius_tiles*(Number(floor.dataset.tile)||32);
   for(const spot of floor.querySelectorAll(".ui-spot[data-x]")){
    if(Math.hypot(Number(spot.dataset.x)-x,Number(spot.dataset.y)-y)>radius)continue;
    const id=spot.getAttribute("href").slice(1),take=document.getElementById(id)?.querySelector(".ui-world-take");
    if(!take||take.getAttribute("aria-pressed")==="true"||(el.contains(spot)&&state.looted.has(id.slice((wid+"-spot-").length))))continue;
    spot.setAttribute("data-scroll-found","");names.push(take.dataset.itemLabel);
   }
  }
  clearScan=setTimeout(clear,explorationScroll.field.duration_seconds*1000);
  return names.length?"✨ 近くのどうぐ："+names.join("、"):"近くに未取得のどうぐはありません";
 };
 const useExplorationScroll=()=>{
  if(!state.consumables.has(scrollKey))return false;
  if(!explorationScroll.reusable)consume(scrollKey);
  return true;
 };
 const foodExp=20;
 const useConsumable=key=>{
  if(key===scrollKey)return useExplorationScroll()?{text:scanItems(),scan:true}:null;
  const item=consume(key);if(!item)return null;
  if(item.item_type==="food"){
   gainExp(foodExp);renderHud();
   return{text:`${item.label}を食べた！ EXP+${foodExp}`,effect:rpgOrbEffect(foodExp,true,rpg.orbs)};
  }
  const beforeHp=state.hp,beforeMp=state.mp,st=stats();
  if(item.hp)state.hp=Math.min(st.maxHp,state.hp+item.hp);
  if(item.mp)state.mp=Math.min(st.maxMp,state.mp+item.mp);
  const dhp=state.hp-beforeHp,dmp=state.mp-beforeMp;
  renderHud();
  return{kind:"heal",amount:Math.max(1,dhp+dmp),text:`${item.emoji} ${item.label}を使った！ HP+${dhp} MP+${dmp}`,effect:rpgOrbEffect(Math.max(1,dhp||dmp),true,rpg.orbs)};
 };
 // City tools draw from the village inventory. Fire coordinates are one-based tile indices.
 const cities=el.closest("[data-world-shell]")?.querySelector("#cities-map");
 const paris=cities?.querySelector('.ui-floor[data-floor="paris"]'),tile=Number(paris?.dataset.tile);
 const fires=[...(paris?.querySelectorAll('.ui-prop[data-kind="fire"]')||[])];
 const atSavedFire=(fire,save)=>Math.floor(parseFloat(fire.style.left)/tile)+1===save.fireX&&Math.floor(parseFloat(fire.style.top)/tile)+1===save.fireY;
 let syncDragon;
 const syncCityItems=()=>{for(const fire of fires)fire.hidden=atSavedFire(fire,state)};
 if(cities){
  const cityTools=cities.querySelector(".ui-world-tools"),note=rpgEl("output",{"aria-live":"polite"});
  const cityButton=(route,label,act)=>{
   const button=rpgEl("button",{type:"button",className:"ui-rpg-btn","data-city-item":route,textContent:label,onclick:()=>{note.textContent=act()}});
   cityTools.append(button);
  };
  cityButton("paris","💧 目の前の火を消す",()=>{
   const player=paris.querySelector(".ui-player");
   const [dx,dy]=({north:[0,-1],south:[0,1],west:[-1,0],east:[1,0]})[player.dataset.facing||"south"];
   const front={fireX:Math.floor(parseFloat(player.style.getPropertyValue("--px"))/tile)+dx+1,
                fireY:Math.floor(parseFloat(player.style.getPropertyValue("--py"))/tile)+dy+1};
   if(!fires.some(f=>!f.hidden&&atSavedFire(f,front)))return "目の前に火がありません";
   if(!consume("spot:meadow-drop-mana"))return "癒しの水がありません";
   Object.assign(state,front);syncCityItems();return "火を一つ消しました";
  });
  const sign=cities.querySelector('.ui-spot[href="#cities-spot-london-nogard"]');
  const sheet=cities.querySelector("#cities-spot-london-nogard");
  const art=cities.closest("[data-world-shell]").querySelector("#dragon-art").content;
  const portrait=art.querySelector("img").cloneNode(true);
  cities.style.setProperty("--dragon-sprite",`url("${portrait.src}")`);
  const mood=rpgEl("output",{"aria-live":"polite"});
  let pats=0,restTimer;
  const react=(emoji,words)=>{
   clearTimeout(restTimer);sign.dataset.reaction=emoji;mood.textContent=emoji+" "+words;
   restTimer=setTimeout(()=>{delete sign.dataset.reaction;mood.textContent=""},4500);
  };
  const pet=rpgEl("button",{type:"button","aria-label":"ドラゴンをなでる",onclick:()=>{
   const moods=[["💕","すり寄ってきた"],["🎵","のどを鳴らした"],["💤","安心してうとうとしている"]];
   const first=!state.dragonScroll;
   state.dragonScroll=1;syncDragon();
   react(...moods[pats++%moods.length]);
   if(first)mood.textContent+=" 📜 竜の巻物をくれた！";
  }},portrait,"なでる");
  const hue=rpgEl("select",{"aria-label":"ドラゴンの体色"},...["元の色","青系","紫系","桃色系"].map((label,i)=>rpgEl("option",{value:i,textContent:label})));
  const fill=rpgEl("input",{type:"color","aria-label":"背景の塗りつぶし"});
  const summon=rpgEl("button",{type:"button",textContent:"📜 竜の巻物",hidden:true});
  cities.closest("[data-world-shell]").querySelector("#world-switcher nav").append(summon);
  syncDragon=()=>{
   summon.hidden=!state.dragonScroll;
   hue.value=String(state.dragonHue);fill.value=state.dragonFill?"#"+(state.dragonFill-1).toString(16).padStart(6,"0"):"#ffffff";
   portrait.style.filter=["none","hue-rotate(120deg)","hue-rotate(180deg)","hue-rotate(225deg)"][state.dragonHue];
   pet.style.backgroundColor=state.dragonFill?fill.value:"";
   cities.style.setProperty("--dragon-hue",portrait.style.filter);
   if(state.dragonFill)cities.style.setProperty("--dragon-fill",fill.value);else cities.style.removeProperty("--dragon-fill");
  };
  hue.onchange=()=>{state.dragonHue=Number(hue.value);syncDragon()};
  fill.oninput=()=>{state.dragonFill=parseInt(fill.value.slice(1),16)+1;syncDragon()};
  const reset=rpgEl("button",{type:"button",textContent:"元の色に戻す",onclick:()=>{state.dragonHue=0;state.dragonFill=0;syncDragon()}});
  const care=rpgEl("div",{className:"dragon-care"},pet,mood,rpgEl("label",{},"体色 ",hue),rpgEl("label",{},"背景 ",fill),reset,art.querySelector("a").cloneNode(true));
  const chat=talkMore("リバースロンドンのドラゴン",()=>`今いる場所：${cities.closest("[data-world-shell]").querySelector("#world-space-name").textContent}。今の様子：${mood.textContent||"こちらを見ている"}。ドラゴン経験値：${state.dragonExp}`);
  if(chat)care.append(chat);
  sheet.querySelector(".ui-sheet-close").before(care);syncDragon();
  const feedDragon=()=>{
   if(!consume("spot:meadow-hirugaoka"))return `サツマイモがありません（ドラゴン経験値 ${state.dragonExp}）`;
   state.dragonExp+=foodExp;react("😋","ほくほくのサツマイモをぺろり！");return `🐉 ドラゴン経験値 +${foodExp}（累計 ${state.dragonExp}）`;
  };
  cityButton("london","🍠 ドラゴンにあげる",()=>sign.dataset.show==="flip"?feedDragon():"nogardの看板のドラゴンを探してください");
  const result=rpgEl("output",{"aria-live":"polite"});
  const scroll=rpgEl("dialog",{className:"dragon-scroll-dialog","aria-label":"竜の巻物"},
   rpgEl("button",{type:"button",textContent:"閉じる",onclick:()=>scroll.close()}),
   rpgEl("button",{type:"button",textContent:"🍠 サツマイモを渡す",onclick:()=>{result.textContent=feedDragon()}}),result);
  cities.closest("[data-world-shell]").append(scroll);
  summon.onclick=()=>{
   const battle=overlay.querySelector(".ui-rpg-battle");
   if(!overlay.hidden&&battle&&!el.closest("[data-world-space]")?.hidden){battle.querySelector("[data-dragon-attack]")?.click();return}
   result.textContent="";scroll.prepend(care);scroll.showModal();
  };
  const searchNote=rpgEl("output",{"aria-live":"polite"});
  let noteTimer;
  searchButton=rpgEl("button",{type:"button",textContent:"📜 "+explorationScroll.label,hidden:true,onclick:()=>{
   const battle=overlay.querySelector(".ui-rpg-battle");
   if(!overlay.hidden&&battle&&!el.closest("[data-world-space]")?.hidden){battle.querySelector("[data-battle-search]")?.click();return}
   const result=useConsumable(scrollKey);if(!result)return;
   searchNote.textContent=result.text;renderHud();clearTimeout(noteTimer);
   noteTimer=setTimeout(()=>{searchNote.textContent=""},explorationScroll.field.duration_seconds*1000);
  }});
  summon.after(searchButton,searchNote);
  scroll.addEventListener("close",()=>sheet.querySelector(".ui-sheet-close").before(care));
  cityTools.append(note);cities.addEventListener("change",()=>{note.textContent=""});
 }
 function queryTopics(question){
  const normalize=text=>text.normalize("NFKC").toLowerCase();
  const words=normalize(question);
  const matches=Object.entries(worldKnowledge.terms).map(([name,aliases])=>{
   const lengths=aliases.map(normalize).filter(alias=>words.includes(alias)).map(alias=>alias.length);
   return [name,Math.max(0,...lengths)];
  });
  return matches.filter(([,length])=>length).sort((a,b)=>b[1]-a[1]).map(([name])=>name);
 }
 function relatedFacts(seeds,question){
  const paths=seeds.flatMap(name=>worldKnowledge.paths[name]).sort((a,b)=>a.length-b.length);
  const selected=new Set();
  for(const path of paths){
   if(new Set([...selected,...path]).size<=5)for(const id of path)selected.add(id);
  }
  const facts=[...selected].map(id=>worldKnowledge.facts[id]);
  const contextual=facts.filter(f=>f.context?.some(term=>question.includes(term)));
  const field=contextual.some(f=>f.mode==="field");
  const battle=contextual.some(f=>f.mode==="battle")&&!question.includes("非戦闘");
  if(field===battle)return facts;
  return facts.filter(f=>!f.mode||f.mode===(field?"field":"battle"));
 }
 function talkMore(speaker,context){
  if(typeof worldAnswer!=="function")return null;
  const form=rpgEl("form"),input=rpgEl("input",{maxLength:160,required:true,"aria-label":"話しかける",placeholder:"何を聞いてみる？"});
  const send=rpgEl("button",{type:"submit",textContent:"送る"}),reply=rpgEl("p",{"aria-live":"polite"});
  const evidence=rpgEl("details",{hidden:true}),sources=rpgEl("ul");
  evidence.append(rpgEl("summary",{textContent:"GitHubの根拠"}),sources);
  form.append(input,send,reply,evidence);
  form.onsubmit=async e=>{
   e.preventDefault();const question=input.value.trim();if(!question||send.disabled)return;
   send.disabled=true;
   try{
    const seeds=queryTopics(question);
    if(!seeds.length){
     const previous=/[3３三]回前/.test(question)?3:/[2２二]回前/.test(question)?2:/さっき|先ほど|前の話|[1１一]回前|それについて/.test(question)?1:0;
     const topic=previous&&topics[state[memoryKeys[previous-1]]];
     if(topic)seeds.push(topic);
    }
    const facts=relatedFacts(seeds,question);
    sources.replaceChildren(...facts.map(f=>rpgEl("li",{},f.edge+" ",...f.urls.map(url=>rpgEl("a",{href:url,target:"_blank",rel:"noopener",textContent:url.split("/")[4]+" "})))));
    evidence.hidden=!facts.length;
    const grounding=facts.map(f=>f.edge+"："+f.text).join("\n")||"この質問に対応する関係は台帳にない。";
    const messages=[{role:"system",content:`あなたは${speaker}。次の台詞と今の様子をもとに、日本語で短くひと言返して。未知の事実は知らないと答えて。噂は噂として話し、アイテムや報酬を与えたことにはしない。\n${context()}\n質問からたどった根拠：\n${grounding}`},{role:"user",content:question}];
    const result=await worldAnswer(messages,s=>{reply.textContent=s},96);
    if(!result.output.trim())throw new Error("empty answer");
    remember(seeds[0]);
   }catch{reply.textContent="今はうまくおしゃべりできないみたい。"}
   finally{send.disabled=false}
  };
  return rpgEl("details",{},rpgEl("summary",{textContent:"もっと話す"}),rpgEl("small",{textContent:"入力を始めると、初回だけ約560 MBのモデルを読み込みます。"}),form);
 }
 const closeModal=()=>{overlay.hidden=true;overlay.replaceChildren();el.querySelector(".ui-world-view")?.focus({preventScroll:true})};
 const showCard=(card)=>{overlay.replaceChildren(card);overlay.hidden=false;const focusable=card.querySelector("[data-primary],button");focusable?.focus({preventScroll:true})};
 const renderOrbs=effect=>{
  const wrap=rpgEl("div",{className:"ui-rpg-orbs"});
  if(!effect||effect.idle){wrap.append(rpgEl("span",{textContent:"✨ オーブ待機中…"}));return wrap}
  for(const orb of effect.orbs)wrap.append(rpgEl("span",{className:"ui-rpg-orb",textContent:orb}));
  wrap.append(rpgEl("span",{textContent:` ${effect.label}`}));
  return wrap;
 };
 const openQuizView=(npc,spotId)=>{
  const qz=rpg.quizzes[state.quizIdx%rpg.quizzes.length];
  state.quizIdx=(state.quizIdx+1)%rpg.quizzes.length;
  const resultBox=rpgEl("div",{className:"ui-rpg-subpanel",hidden:true});
  const choiceBtns=[];
  const card=rpgEl("div",{className:"ui-rpg-card",role:"dialog","aria-modal":"true","aria-label":"ポートフォリオ・クイズ"},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:`${npc.emoji} ${npc.speaker}のポートフォリオクイズ`}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
   qz.repo?rpgEl("p",{className:"ui-rpg-subnote",textContent:`📦 関連リポジトリ: ${qz.repo}`}):null,
   rpgEl("p",{className:"ui-rpg-text",textContent:qz.prompt}),
   rpgEl("div",{className:"ui-rpg-actions"},...qz.choices.map((c,idx)=>{
    const btn=rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:`${idx+1}. ${c}`,onclick:()=>{
     for(const b of choiceBtns)b.disabled=true;
     const ok=idx===qz.correct;
     resultBox.hidden=false;
     const qKey=qz.prompt;let rewardNote="";
     if(ok&&!state.quizSolved.has(qKey)){state.quizSolved.add(qKey);gainExp(20);state.gold+=25;rewardNote=" (+20 EXP / +25G)";checkQuests()}
     resultBox.replaceChildren(
      rpgEl("p",{className:"ui-rpg-text",textContent:(ok?"⭕ せいかい！":"❌ おしい！")+rewardNote}),
      rpgEl("p",{className:"ui-rpg-subnote",textContent:qz.explanation}),
      rpgEl("div",{className:"ui-rpg-actions"},
       rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"つぎの問題 ▶",onclick:()=>openQuizView(npc,spotId)}),
       rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"会話にもどる",onclick:()=>openNpcDialog(spotId)})));
    }});
    choiceBtns.push(btn);return btn;
   })),
   resultBox);
  showCard(card);
 };
 const openShopView=(npc,spotId)=>{
  const list=rpgEl("div",{className:"ui-rpg-list"});
  const goldTag=rpgEl("p",{className:"ui-rpg-subnote",textContent:`所持金: 🪙 ${state.gold}G`});
  const rebuildShop=()=>{
   goldTag.textContent=`所持金: 🪙 ${state.gold}G`;
   list.replaceChildren(...rpg.shop.map(sh=>rpgEl("div",{className:"ui-rpg-row"},
    rpgEl("div",{className:"ui-rpg-row-top"},rpgEl("span",{textContent:`${sh.emoji} ${sh.label}`}),rpgEl("span",{textContent:`🪙 ${sh.cost}G`})),
    rpgEl("p",{className:"ui-rpg-subnote",textContent:sh.desc}),
    rpgEl("div",{className:"ui-rpg-actions"},rpgEl("button",{type:"button",className:"ui-rpg-btn",disabled:state.gold<sh.cost,textContent:state.gold<sh.cost?"ゴールド不足":"かう",onclick:()=>{
     if(state.gold<sh.cost)return;
     state.gold-=sh.cost;state.boughtCount+=1;
     const key="shop:"+sh.id,cur=state.consumables.get(key)||{key,emoji:sh.emoji,label:sh.label,item_type:sh.item_type,hp:sh.hp,mp:sh.mp,atk:0,count:0};
     cur.count+=1;state.consumables.set(key,cur);
     showToast(`${sh.emoji} ${sh.label} を購入した！`);
     checkQuests();rebuildShop();
    }})))));
  };
  rebuildShop();
  const card=rpgEl("div",{className:"ui-rpg-card",role:"dialog","aria-modal":"true","aria-label":`${npc.speaker}のお店`},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:`🛒 ${npc.speaker}の道具屋`}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
   goldTag,list,
   rpgEl("div",{className:"ui-rpg-actions"},rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"会話にもどる",onclick:()=>openNpcDialog(spotId)})));
  showCard(card);
 };
 const openNpcDialog=(spotId,pageIdx=-1)=>{
  const npc=rpg.npcs[spotId];if(!npc)return;
  state.talked.add(spotId);checkQuests();
  const pages=[npc.greeting,...npc.lines,...(npc.topic?[npc.topic.answer]:[])];
  let idx=pageIdx>=0?Math.min(pageIdx,pages.length-1):0;
  const textEl=rpgEl("p",{className:"ui-rpg-text"}),orbsWrap=rpgEl("div"),actionsEl=rpgEl("div",{className:"ui-rpg-actions"});
  const renderPage=()=>{
   textEl.textContent=`[${idx+1}/${pages.length}] ${pages[idx]}`;
   actionsEl.replaceChildren();
   if(idx>0)actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"◀ もどる",onclick:()=>{idx-=1;renderPage()}}));
   if(idx<pages.length-1)actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"つぎへ ▶",onclick:()=>{idx+=1;renderPage()}}));
   if(npc.heal)actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"💚 いやす（全回復）",onclick:()=>{
    const st=stats(),dhp=Math.max(1,st.maxHp-state.hp);state.hp=st.maxHp;state.mp=st.maxMp;state.healedCount+=1;
    orbsWrap.replaceChildren(renderOrbs(rpgOrbEffect(dhp,true,rpg.orbs)));
    textEl.textContent="✨ やさしい光に包まれ、HPとMPが全回復した！";renderHud();
   }}));
   if(npc.shop)actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"🛒 おみせ",onclick:()=>openShopView(npc,spotId)}));
   if(npc.quiz)actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"🎓 クイズに挑戦",onclick:()=>openQuizView(npc,spotId)}));
   actionsEl.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",...(idx===pages.length-1?{"data-primary":""}:{}),textContent:"とじる",onclick:closeModal}));
  };
  const card=rpgEl("div",{className:"ui-rpg-card",role:"dialog","aria-modal":"true","aria-label":npc.speaker},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:`${npc.emoji} ${npc.speaker}`}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
   textEl,orbsWrap,actionsEl,
   npc.topic?rpgEl("button",{type:"button",textContent:npc.topic.question,onclick:()=>{idx=pages.length-1;renderPage();if(typeof worldKnowledge!=="undefined")remember(queryTopics(npc.topic.question)[0])}}):null,
   talkMore(npc.speaker,()=>[npc.greeting,...npc.lines].join(" ")));
  renderPage();showCard(card);
 };
 const openLootDialog=spotId=>{
  const entry=rpg.loot[spotId];if(!entry)return;
  const meta=spotMeta(spotId);
  if(entry.requires_enemy&&!state.defeated.has(entry.requires_enemy)){
   const guard=rpg.enemies[entry.requires_enemy];
   const card=rpgEl("div",{className:"ui-rpg-card",role:"dialog","aria-modal":"true","aria-label":"封印された宝箱"},
    rpgEl("div",{className:"ui-rpg-card-head"},rpgEl("h3",{className:"ui-rpg-card-title",textContent:`🔒 ${meta.label}`}),rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
    rpgEl("p",{className:"ui-rpg-text",textContent:`強力な気配が宝箱を守っている！ まずは ${guard?guard.emoji+" "+guard.name:"番人"} をたおそう。`}),
    rpgEl("div",{className:"ui-rpg-actions"},
     rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"⚔️ いどむ",onclick:()=>startBattle(entry.requires_enemy)}),
     rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"とじる",onclick:closeModal})));
   showCard(card);return;
  }
  const already=state.looted.has(spotId),res=already?null:addLoot(spotId);
  const bonuses=[];
  if(entry.atk)bonuses.push(`⚔️ ATK +${entry.atk}`);
  if(entry.def)bonuses.push(`🛡️ DEF +${entry.def}`);
  if(entry.hp)bonuses.push(`❤️ HP +${entry.hp}`);
  if(entry.mp)bonuses.push(`💧 MP +${entry.mp}`);
  if(entry.gold)bonuses.push(`🪙 +${entry.gold}G`);
  if(entry.exp)bonuses.push(`✨ +${entry.exp}EXP`);
  const card=rpgEl("div",{className:"ui-rpg-card",role:"dialog","aria-modal":"true","aria-label":meta.label},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:`${meta.emoji} ${meta.itemLabel}`}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
   rpgEl("p",{className:"ui-rpg-text",textContent:already?`${meta.label} はすでに入手済みだ！（🎒 バッグで確認できる）`:(entry.kind==="chest"?`宝箱をあけた！ ${meta.emoji} ${meta.itemLabel} を手に入れた！`:`${meta.emoji} ${meta.itemLabel} をひろった！ 🎒 バッグにしまった。`)}),
   bonuses.length?rpgEl("p",{className:"ui-rpg-subnote",textContent:(entry.consumable?"どうぐ効果: ":"装備ボーナス: ")+bonuses.join(" / ")+(res?.lvUp?` 🎉 Lv.${res.lvUp}に上がった！`:"")}):null,
   rpgEl("div",{className:"ui-rpg-actions"},rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"やったね！",onclick:closeModal})));
  showCard(card);
 };
 const startBattle=spotId=>{
  const foeTpl=rpg.enemies[spotId];if(!foeTpl)return;
  const foe={...foeTpl,spotId,maxHp:foeTpl.hp,turn:0};
  const nextAttackIsHeavy=()=>(foe.turn+1)%3===0;
  const forage=explorationScroll.battle;
  const logLines=[foe.taunt||`${foe.emoji} ${foe.name} があらわれた！`];
  let orbState=rpgOrbEffect(0,false,rpg.orbs),subMode="",ended=false;
  const foeHpText=rpgEl("span"),foeHpFill=rpgEl("i"),intentBadge=rpgEl("span",{className:"ui-rpg-intent"}),orbBox=rpgEl("div"),logBox=rpgEl("p",{className:"ui-rpg-log"}),subPanel=rpgEl("div",{className:"ui-rpg-subpanel",hidden:true}),cmdBox=rpgEl("div",{className:"ui-rpg-cmd-grid"});
  const syncBattle=()=>{
   foeHpText.textContent=`HP ${foe.hp}/${foe.maxHp}`;
   foeHpFill.style.width=`${Math.round(100*foe.hp/Math.max(1,foe.maxHp))}%`;
   const heavy=nextAttackIsHeavy();
   intentBadge.textContent=heavy?"⚠️ 次ターン強攻撃！ぼうぎょ推奨":"🗡️ 通常こうげき構え";
   orbBox.replaceChildren(renderOrbs(orbState));
   logBox.textContent=logLines.slice(-4).join("\n");
   renderHud();
  };
  const finishVictory=()=>{
   ended=true;state.defeated.add(spotId);state.gold+=foe.gold;
   const lvUp=gainExp(foe.exp);
   logLines.push(`🎉 ${foe.name} をたおした！ +${foe.exp} EXP / +${foe.gold} G`+(lvUp?` 🌟 Lv.${lvUp}にアップ！`:""));
   if(foe.drop_spot&&!state.looted.has(foe.drop_spot))logLines.push(`🔓 宝箱の封印がとけた！`);
   subPanel.hidden=true;
   cmdBox.replaceChildren(rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"🏆 勝利！マップにもどる",onclick:closeModal}));
   checkQuests();syncBattle();
  };
  const finishDefeat=()=>{
   ended=true;const st=stats();state.hp=Math.max(1,Math.floor(st.maxHp/2));state.mp=Math.max(0,Math.floor(st.maxMp/2));
   logLines.push("💫 力尽きた… 村のいずみで介抱され、体力が半分もどった。");
   subPanel.hidden=true;
   cmdBox.replaceChildren(rpgEl("button",{type:"button",className:"ui-rpg-btn","data-primary":"",textContent:"🏘️ 村へもどる",onclick:closeModal}));
   syncBattle();
  };
  const enemyTurn=(guarding=false)=>{
   if(foe.hp<=0){finishVictory();return}
   const st=stats(),heavy=nextAttackIsHeavy(),hit=rpgDamage(foe.atk,st.def,nextRoll(),{multPct:heavy?155:100,guarding,critPct:heavy?20:8});
   state.hp=Math.max(0,state.hp-hit.damage);
   foe.turn+=1;
   logLines.push(`${foe.emoji} ${foe.name}の${heavy?"強烈な一撃":"攻撃"}！${guarding?" (🛡️軽減)":""}${hit.crit?" 💥痛恨！":""} ${hit.damage} のダメージ！`);
   if(state.hp<=0){finishDefeat();return}
   syncBattle();
  };
  const rebuildSub=()=>{
   if(!subMode||ended){subPanel.hidden=true;subPanel.replaceChildren();return}
   subPanel.hidden=false;
   if(subMode==="skill"){
    subPanel.replaceChildren(...rpg.skills.map(sk=>rpgEl("button",{type:"button",className:"ui-rpg-btn",disabled:state.mp<sk.mp,textContent:`${sk.emoji} ${sk.label} (💧${sk.mp}) - ${sk.desc}`,onclick:()=>{
     if(ended||state.mp<sk.mp)return;
     state.mp-=sk.mp;subMode="";rebuildSub();
     const st=stats();
     if(sk.kind==="heal"){
      const gain=Math.max(8,sk.power+Math.floor(st.maxHp/4)),before=state.hp;
      state.hp=Math.min(st.maxHp,state.hp+gain);const actual=state.hp-before;
      orbState=rpgOrbEffect(Math.max(1,actual),true,rpg.orbs);
      logLines.push(`${sk.emoji} ${sk.label}！ HPが ${actual} かいふく！`);
      enemyTurn(false);
     }else if(sk.kind==="guard"){
      const res=rpgDamage(st.atk,foe.def,nextRoll(),{multPct:sk.mult_pct,critPct:15});
      foe.hp=Math.max(0,foe.hp-res.damage);orbState=res.effect;
      logLines.push(`${sk.emoji} ${sk.label}！ 身を守りつつ ${res.damage} ダメージ！`);
      enemyTurn(true);
     }else{
      const weak=foe.weakness&&sk.desc.includes(foe.weakness),mult=weak?sk.mult_pct+25:sk.mult_pct;
      const res=rpgDamage(st.atk,foe.def,nextRoll(),{multPct:mult,critPct:20});
      foe.hp=Math.max(0,foe.hp-res.damage);orbState=res.effect;
      logLines.push(`${sk.emoji} ${sk.label}！${weak?" ✨弱点！":""}${res.crit?" 💥会心！":""} ${res.damage} ダメージ！`);
      enemyTurn(false);
     }
    }})));
   }else if(subMode==="item"){
    const items=[...state.consumables.values()].filter(it=>it.item_type!=="scroll");
    if(!items.length){subPanel.replaceChildren(rpgEl("p",{className:"ui-rpg-subnote",textContent:"つかえる どうぐがない！（村の落とし物やお店で手に入るよ）"}));return}
    subPanel.replaceChildren(...items.map(it=>rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:`${it.emoji} ${it.label} ×${it.count}`,onclick:()=>{
     if(ended)return;
     const res=useConsumable(it.key);if(!res)return;
     subMode="";rebuildSub();orbState=res.effect;logLines.push(res.text);enemyTurn(false);
    }})));
   }
  };
  const cmds=[
   ["⚔️ こうげき",()=>{if(ended)return;subMode="";rebuildSub();const st=stats(),res=rpgDamage(st.atk,foe.def,nextRoll(),{multPct:100,critPct:14});foe.hp=Math.max(0,foe.hp-res.damage);orbState=res.effect;logLines.push(`⚔️ こうげき！${res.crit?" 💥会心の一撃！":""} ${foe.name}に ${res.damage} のダメージ！`);enemyTurn(false)},true],
   ["💡 ヒント",()=>{
    const statsNow=stats(),heavy=nextAttackIsHeavy();
    const heal=[...state.consumables.values()].find(it=>it.hp>0);
    const skill=rpg.skills.find(sk=>sk.mp<=state.mp&&sk.kind==="attack"&&foe.weakness&&sk.desc.includes(foe.weakness));
    let hint="こうげきならMPを使わずに攻められます。";
    if(state.hp*2<=statsNow.maxHp&&heal)hint="HPが半分以下です。どうぐの「"+heal.label+"」で回復できます。";
    else if(heavy)hint="次は強攻撃です。ぼうぎょでダメージを半減できます。";
    else if(skill)hint="弱点は「"+foe.weakness+"」。とくぎの「"+skill.label+"」が効きます。";
    else if(state.mp<2)hint="ぼうぎょするとMPが2回復します。";
    const maxNormalHit=Math.floor((foe.atk+1)*1.5); // Worst normal critical hit before defense.
    const canForage=herb&&state.consumables.has(scrollKey)&&forage.chance_percent>0;
    const needsHerb=!state.consumables.has("spot:"+forage.item_id)&&!state.consumables.has(herbKey);
    if(canForage&&needsHerb&&!heavy&&state.hp>Math.max(statsNow.maxHp/2,maxNormalHit)){
     hint+=` ${forage.target}を補充するなら、${explorationScroll.label}で探せます（${forage.chance_percent}%）。`;
    }
    logLines.push("💡 "+hint);syncBattle();
   },false],
   ["✨ とくぎ",()=>{subMode=subMode==="skill"?"":"skill";rebuildSub()},false],
   ["🎒 どうぐ",()=>{subMode=subMode==="item"?"":"item";rebuildSub()},false],
   ["🛡️ ぼうぎょ",()=>{if(ended)return;subMode="";rebuildSub();const st=stats();state.mp=Math.min(st.maxMp,state.mp+2);orbState=rpgOrbEffect(2,true,rpg.orbs);logLines.push("🛡️ ぼうぎょの構え！ ダメージ半減＋💧MP+2！");enemyTurn(true)},false],
   ["💨 にげる",()=>{if(ended)return;showToast("💨 うまく にげきった！");closeModal()},false]
  ];
  for(const[lbl,fn,prim]of cmds)cmdBox.append(rpgEl("button",{type:"button",className:"ui-rpg-btn",...(prim?{"data-primary":""}:{}),textContent:lbl,onclick:fn}));
  if(herb&&state.consumables.has(scrollKey))cmdBox.append(rpgEl("button",{type:"button",className:"ui-rpg-btn","data-battle-search":"",
   textContent:`📜 ${explorationScroll.label}（${forage.target}${forage.chance_percent}%）`,onclick:()=>{
   if(ended||!useExplorationScroll())return;
   if(!state.consumables.has(scrollKey))cmdBox.querySelector("[data-battle-search]").remove();
   if(nextRoll()/0x100000000<forage.chance_percent/100){
    const item=state.consumables.get(herbKey)||{...stock.get(herbKey),key:herbKey,count:0};
    item.count+=forage.quantity;state.consumables.set(herbKey,item);
    logLines.push(`🌿 ${forage.target}を${forage.quantity}個拾った！`);
   }else logLines.push(`📜 ${forage.target}は見つからなかった。`);
   subMode="";rebuildSub();
   if(forage.uses_turn)enemyTurn(false);else syncBattle();
  }}));
  if(state.dragonScroll)cmdBox.append(rpgEl("button",{type:"button",className:"ui-rpg-btn","data-dragon-attack":"",textContent:"📜 竜の巻物",onclick:()=>{
   if(ended)return;
   const damage=rpgDamage(stats().atk+Math.floor(state.dragonExp/20),foe.def,nextRoll(),{multPct:125});
   foe.hp=Math.max(0,foe.hp-damage.damage);orbState=damage.effect;
   logLines.push(`🐉 ドラゴンの加勢！ ${damage.damage} ダメージ！`);subMode="";rebuildSub();enemyTurn(false);
  }}));
  const card=rpgEl("div",{className:"ui-rpg-card ui-rpg-battle",role:"dialog","aria-modal":"true","aria-label":`${foe.name}との戦闘`},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:`⚔️ バトル ${foe.boss?"【BOSS】":""}`}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"にげてとじる",textContent:"✖️",onclick:closeModal})),
   rpgEl("div",{className:"ui-rpg-foe-box"},
    rpgEl("div",{className:"ui-rpg-foe-sprite",textContent:foe.emoji}),
    rpgEl("div",{className:"ui-rpg-foe-info"},
     rpgEl("div",{className:"ui-rpg-foe-meta"},rpgEl("strong",{textContent:`${foe.name} Lv.${foe.level}`}),foe.weakness?rpgEl("span",{className:"ui-rpg-subnote",textContent:`弱点:${foe.weakness}`}):null),
     rpgEl("div",{className:"ui-rpg-foe-meta"},rpgEl("span",{className:"ui-rpg-meter ui-rpg-meter-foe"},foeHpFill),foeHpText),
     intentBadge)),
   orbBox,logBox,subPanel,cmdBox);
  syncBattle();showCard(card);
 };
 const openJournal=(activeTab="quests")=>{
  const tabs=[["quests","📋 クエスト"],["badges","🏅 実績"],["status","🧙 ステータス"],["bestiary","👾 図鑑"],["save","💾 セーブ"]];
  const body=rpgEl("div"),tabBtns=[];
  const drawBody=()=>{
   if(activeTab==="save"){
    const saveVersion=()=>state.consumables.has(herbKey)?5:state.dragonScroll||memoryKeys.some(k=>state[k])?4:state.dragonHue||state.dragonFill?3:Object.keys(extraWidths).some(k=>state[k])?2:1;
    const box=rpgEl("textarea",{"aria-label":"冒険データ",rows:5}),message=rpgEl("p",{role:"status"});
    const button=(label,run)=>rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:label,onclick:run});
    body.replaceChildren(box,rpgEl("div",{className:"ui-rpg-actions"},
     button("セーブ文字列を作る",()=>{const data=snapshot();box.value=saveText({version:saveVersion(),world:wid,data});box.select();message.textContent="別の端末にコピーできます"}),
     button("復活の呪文を作る",async()=>{
      try{const version=saveVersion(),fields=layouts[version];box.value=spellText(bitsPack(fields,{version,catalogue:await catalogue(fields),...snapshot()}));box.select();message.textContent="空白・改行を含めてコピーできます"}
      catch{message.textContent="呪文を作れません。セーブ文字列を使ってください"}
     }),
     button("読み込む",async()=>{
      try{
       const text=box.value.trim();
       if(/[ぁ-ヶ]/u.test(text)){
        const bytes=spellBytes(text),fields=layouts[bytes[0]];
        const {version,catalogue:tag,...data}=bitsUnpack(fields,bytes);
        if(![1,2,3,4,5].includes(version)||tag!==await catalogue(fields))throw new Error("incompatible spell");
        restore(data,version);
       }else{
        const save=saveState(text);
        if(![1,2,3,4,5].includes(save.version)||save.world!==wid)throw new Error("incompatible save");
        restore(save.data,save.version);
       }
       message.textContent="冒険データを復元しました";
      }catch{message.textContent="読み込めません。文字列とバージョンを確認してください"}
     })),message);
   }else if(activeTab==="quests"){
    body.replaceChildren(rpgEl("ul",{className:"ui-rpg-list"},...rpg.quests.map(q=>{
     const p=Math.min(q.count,questProgress(q)),done=state.completedQuests.has(q.id);
     return rpgEl("li",{className:"ui-rpg-row"},
      rpgEl("div",{className:"ui-rpg-row-top"},rpgEl("span",{textContent:`${done?"✅":"◻️"} ${q.title}`}),rpgEl("span",{textContent:`${p}/${q.count}`})),
      rpgEl("p",{className:"ui-rpg-subnote",textContent:`${q.desc} ｜ 報酬: +${q.reward_exp}EXP / +${q.reward_gold}G`}));
    })));
   }else if(activeTab==="badges"){
    body.replaceChildren(rpgEl("div",{className:"ui-rpg-badges"},...rpg.badges.map(b=>{
     const on=state.badges.has(b.id);
     return rpgEl("div",{className:"ui-rpg-badge","data-unlocked":String(on)},
      rpgEl("strong",{textContent:`${on?b.emoji:"❔"} ${b.label}`}),
      rpgEl("span",{className:"ui-rpg-subnote",textContent:b.desc}));
    })));
   }else if(activeTab==="status"){
    const st=stats(),eqList=equipIds().map(id=>{const m=spotMeta(id);return `${m.emoji} ${m.itemLabel}`});
    const bagItems=[...state.consumables.values()];
    body.replaceChildren(
     rpgEl("div",{className:"ui-rpg-row"},
      rpgEl("div",{className:"ui-rpg-row-top"},rpgEl("span",{textContent:`Lv.${st.lv.level} 冒険者`}),rpgEl("span",{textContent:`🪙 ${state.gold}G`})),
      rpgEl("p",{className:"ui-rpg-text",textContent:`❤️ HP ${state.hp}/${st.maxHp}  💧 MP ${state.mp}/${st.maxMp}  ⚔️ ATK ${st.atk}  🛡️ DEF ${st.def}`}),
      rpgEl("p",{className:"ui-rpg-subnote",textContent:`✨ 累計EXP ${state.exp} (次Lvまで ${Math.max(0,st.lv.next_exp-state.exp)})`}),
      rpgEl("p",{className:"ui-rpg-subnote",textContent:`🛡️ そうび品: ${eqList.length?eqList.join("・"):"なし（村の宝箱を探そう！）"}`})),
     rpgEl("div",{className:"ui-rpg-row"},
      rpgEl("strong",{textContent:"🎒 つかえるどうぐ"}),
      bagItems.length?rpgEl("div",{className:"ui-rpg-actions"},...bagItems.map(it=>rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:`${it.emoji} ${it.label} ×${it.count}`,onclick:()=>{const result=useConsumable(it.key);if(result?.scan)closeModal();else drawBody();if(result)showToast(result.text)}}))):rpgEl("p",{className:"ui-rpg-subnote",textContent:"まだ消費アイテムがないよ"})));
   }else{
    body.replaceChildren(rpgEl("ul",{className:"ui-rpg-list"},...Object.entries(rpg.enemies).map(([id,f])=>{
     const seen=state.defeated.has(id);
     return rpgEl("li",{className:"ui-rpg-row"},
      rpgEl("div",{className:"ui-rpg-row-top"},rpgEl("span",{textContent:`${f.emoji} ${f.name} Lv.${f.level}`}),rpgEl("span",{textContent:seen?"✓ 討伐済み":"未討伐"})),
      rpgEl("p",{className:"ui-rpg-subnote",textContent:`HP ${f.hp} / ATK ${f.atk} / DEF ${f.def} / +${f.exp}EXP +${f.gold}G`+(f.weakness?` / 弱点:${f.weakness}`:"")}),
      rpgEl("div",{className:"ui-rpg-actions"},rpgEl("button",{type:"button",className:"ui-rpg-btn",textContent:"⚔️ 戦ってみる",onclick:()=>startBattle(id)})));
    })));
   }
  };
  const card=rpgEl("div",{className:"ui-rpg-card ui-rpg-journal-card",role:"dialog","aria-modal":"true","aria-label":"冒険手帳"},
   rpgEl("div",{className:"ui-rpg-card-head"},
    rpgEl("h3",{className:"ui-rpg-card-title",textContent:"📜 冒険手帳（クエスト・実績・図鑑）"}),
    rpgEl("button",{type:"button",className:"ui-rpg-close","aria-label":"とじる",textContent:"✖️",onclick:closeModal})),
   rpgEl("div",{className:"ui-rpg-tabs"},...tabs.map(([k,lbl])=>{
    const b=rpgEl("button",{type:"button",className:"ui-rpg-btn","aria-selected":String(k===activeTab),textContent:lbl,onclick:()=>{
     activeTab=k;for(const[tk,tb]of tabBtns)tb.setAttribute("aria-selected",String(tk===k));drawBody();
    }});
    tabBtns.push([k,b]);return b;
   })),
   body);
  drawBody();showCard(card);
 };
 const interactSpot=sid=>{
  if(rpg.npcs[sid])return openNpcDialog(sid);
  if(rpg.loot[sid])return openLootDialog(sid);
  if(rpg.enemies[sid])return startBattle(sid);
 };
 for(const[sid,entry]of[...Object.entries(rpg.npcs),...Object.entries(rpg.loot),...Object.entries(rpg.enemies)]){
  const art=document.getElementById(wid+"-spot-"+sid);
  if(!art||art.querySelector(".ui-rpg-sheet-btn"))continue;
  const label=rpg.npcs[sid]?"💬 はなす":rpg.enemies[sid]?"⚔️ たたかう":(entry.kind==="chest"?"🗝️ 宝箱を見る":"✨ ひろう");
  const btn=rpgEl("button",{type:"button",className:"ui-rpg-btn ui-rpg-sheet-btn","data-rpg-spot":sid,textContent:label,onclick:()=>{
   art.querySelector(".ui-sheet-close")?.click();interactSpot(sid);
  }});
  const anchor=art.querySelector(".ui-world-go")||art.querySelector(".ui-sheet-close");
  art.insertBefore(btn,anchor);
 }
 el.addEventListener("click",e=>{
  const takeBtn=e.target.closest(".ui-sheet-item .ui-world-take");
  if(!takeBtn)return;
  const id=takeBtn.dataset.itemId,prefix=wid+"-spot-";
  if(!id?.startsWith(prefix))return;
  const sid=id.slice(prefix.length);
  if(takeBtn.getAttribute("aria-pressed")==="true"&&rpg.loot[sid]&&!state.looted.has(sid))addLoot(sid);
 });
 hud?.querySelector("[data-rpg-journal-btn]")?.addEventListener("click",()=>openJournal("quests"));
 hud?.querySelector("[data-rpg-explore]")?.addEventListener("click",()=>{
  const curFloor=el.querySelector("input[name$='-floor']:checked")?.value||"meadow";
  const floorEnemies=[...el.querySelectorAll(`.ui-floor[data-floor="${CSS.escape(curFloor)}"] .ui-spot[data-rpg-kind="enemy"]`)].map(n=>n.getAttribute("href").slice(1+(wid+"-spot-").length)).filter(id=>rpg.enemies[id]);
  const nextId=floorEnemies.find(id=>!state.defeated.has(id))||floorEnemies[0];
  if(!nextId){showToast("🕊️ この空間には 魔物の気配はないようだ。");return}
  startBattle(nextId);
 });
 for(const b of el.querySelectorAll(".ui-world-take[aria-pressed='true']")){
  const p=wid+"-spot-";if(b.dataset.itemId?.startsWith(p)){const sid=b.dataset.itemId.slice(p.length);if(rpg.loot[sid])addLoot(sid)}
 }
 let goTarget=null,lastContactId="",prevPx=null,prevPy=null,movedSteps=0;
 el.addEventListener("click",e=>{
  const g=e.target.closest(".ui-world-go");
  if(g)goTarget={floor:g.dataset.goFloor,x:Number(g.dataset.goX),y:Number(g.dataset.goY)};
 },true);
 el.addEventListener("keydown",e=>{
  if(!overlay.hidden){
   if(e.key==="Escape"){e.preventDefault();e.stopPropagation();closeModal();return}
   if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight","w","a","s","d"].includes(e.key.length>1?e.key:e.key.toLowerCase()))e.stopPropagation();
   return;
  }
  if(["ArrowUp","ArrowDown","ArrowLeft","ArrowRight","w","a","s","d"].includes(e.key.length>1?e.key:e.key.toLowerCase()))goTarget=null;
 },true);
 el.addEventListener("pointerdown",e=>{if(e.target.closest("[data-step]"))goTarget=null},true);
 el.addEventListener("change",e=>{
  if(e.target.name&&e.target.name.endsWith("-floor")){state.visitedFloors.add(e.target.value);lastContactId="";checkQuests()}
 });
 const actorPos=a=>{
  const m=getComputedStyle(a).transform;
  if(!m||m==="none")return null;
  const parts=m.match(/matrix\(([^)]+)\)/);
  if(!parts)return null;
  const nums=parts[1].split(",").map(Number);
  return nums.length===6?[nums[4],nums[5]]:null;
 };
 const watch=()=>{
  if(!el.isConnected)return;
  const curFloor=el.querySelector("input[name$='-floor']:checked")?.value||"meadow";
  const f=el.querySelector(`.ui-floor[data-floor="${CSS.escape(curFloor)}"]`)||el.querySelector(".ui-floor");
  const pl=f?.querySelector(".ui-player");
  if(pl){
   const px=parseFloat(pl.style.getPropertyValue("--px"))||Number(pl.dataset.x);
   const py=parseFloat(pl.style.getPropertyValue("--py"))||Number(pl.dataset.y);
   const stepDist=prevPx===null?0:Math.hypot(px-prevPx,py-prevPy);
   if(stepDist>0.5)movedSteps+=stepDist;
   prevPx=px;prevPy=py;
   const tile=Number(f.dataset.tile)||32,range=tile*1.15;
   let hit=null,hitD=Infinity;
   for(const node of f.querySelectorAll("[data-rpg-kind]")){
    const sid=node.getAttribute("href")?.slice(1+(wid+"-spot-").length);
    if(!sid)continue;
    const pos=node.classList.contains("ui-actor")?actorPos(node):[Number(node.dataset.x),Number(node.dataset.y)];
    if(!pos)continue;
    const d=Math.hypot(pos[0]-px,pos[1]-py);
    if(d<=range&&d<hitD){hit=sid;hitD=d}
   }
   if(goTarget&&curFloor===goTarget.floor&&Math.hypot(px-goTarget.x,py-goTarget.y)<=2){
    goTarget=null;if(hit)lastContactId=hit;
   }
   const blocked=Boolean(goTarget)||!overlay.hidden||el.hasAttribute("data-pick")||el.hasAttribute("data-ask")||el.querySelector(".ui-sheet-item[data-open]");
   if(!blocked){
    if(hit){
     if(hit!==lastContactId&&(movedSteps>8||rpg.npcs[hit]?.on_contact||rpg.enemies[hit]?.on_contact||rpg.loot[hit])){
      lastContactId=hit;
      if(rpg.npcs[hit]?.on_contact)openNpcDialog(hit);
      else if(rpg.loot[hit]&&!state.looted.has(hit))openLootDialog(hit);
      else if(rpg.enemies[hit]?.on_contact&&!state.defeated.has(hit))startBattle(hit);
     }
    }else if(lastContactId){
     const prevNode=spotNode(lastContactId);
     const pPos=prevNode?(prevNode.classList.contains("ui-actor")?actorPos(prevNode):[Number(prevNode.dataset.x),Number(prevNode.dataset.y)]):null;
     if(!pPos||Math.hypot(pPos[0]-px,pPos[1]-py)>tile*1.55)lastContactId="";
    }
   }
  }
  setTimeout(()=>requestAnimationFrame(watch),110);
 };
 checkQuests();renderHud();requestAnimationFrame(watch);
 return el;
}
export function bindRpgWorlds(root=document){return[...root.querySelectorAll("[data-ui-world][data-rpg]")].map(el=>bindWorldRpg(el))}
globalThis.webUiWorld={...globalThis.webUiWorld,rpgRandomWord,rpgOrbEffect,rpgLevelForExp,rpgDamage,bindWorldRpg,bindRpgWorlds};
bindRpgWorlds();
"""


def rpg_module(records_url: str) -> str:
    return (f'import {{saveText,saveState,spellText,spellBytes,bitsPack,bitsUnpack}} from {json.dumps(records_url)};\n'
            + f'const explorationScroll = {json.dumps(EXPLORATION_SCROLL, ensure_ascii=False)};\n'
            + WORLD_RPG_JS)


def world_document(spec: Any, *, theme: str = "modern") -> str:
    """A single-file page: bundled CSS, the world's CSS, the world's HTML and one inline module."""
    world = world_validate(spec)
    js = WORLD_JS
    if world.get("rpg"):
        js += "\n" + rpg_module("data:text/javascript," + quote(js_source("records.js"), safe=""))
    # 🌍 world.js lives here now (WORLD_JS), not in PySaiyanWeBoo: the same inline module, after the body.
    return render_document(trusted_html=world_html(world) + module_script(js), title=world["title"], theme=theme,
                           css=bundled_css() + world_css(world))


def catalogue_world(items: Any, *, id: str = "catalogue", title: str = "Catalogue", columns: int = 8,
                    cell: tuple[int, int] = (160, 64), margin: int = 64, shell: bool = False,
                    tools: dict[str, Any] | None = None) -> dict[str, Any]:
    """A ``web-ui-world/1`` map from a flat catalogue, one floor per ``group`` (more than 64 in a group continue on another floor).

    Each item is ``{"id", "label", "group"}`` plus optional ``"emoji"``, ``"category"`` (a filter chip) and ``"body"`` (the info sheet).
    The page never changes: tap a spot, read its sheet. ``shell=True`` gives it the header / side / footer layout (🏠 ⭐ ⚙️, ☰ the places, a
    floor pulldown) so a long catalogue needs no scrolling and no page change; ``tools`` adds emoji of your own (see ``web-ui-world/1``). Spots sit on a grid whose sizes default to multiples of 8. For a list of screens like
    flutter_navigation_basic's ``screens.json`` map the fields first, e.g. ``{"id": s["name"], "label": s["title"], "emoji": s["emoji"],
    "group": s["category"], "category": s["domainKey"], "body": s["description"]}``; the data itself stays with its owner."""
    if not isinstance(items, list) or not 1 <= len(items) <= 512:
        raise ValueError("a catalogue lists 1..512 items")
    if any(type(v) is not int or v <= 0 for v in (columns, margin, *cell)):
        raise ValueError("columns, cell and margin are positive integers")
    slug = lambda text: re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:28] or "x"
    groups: dict[str, list[dict[str, Any]]] = {}
    taken: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {"id", "label", "group", "emoji", "category", "body"}:
            raise ValueError("an item has id, label, group, emoji, category and body")
        base = slug(item.get("id"))
        unique, n = base, 2
        while unique in taken:                                   # the same slug twice: Screen1 and screen-1 become screen1 and screen1-2
            unique, n = f"{base}-{n}", n + 1
        taken.add(unique)
        label = (f"{item.get('emoji')} " if item.get("emoji") else "") + _world_text(item.get("label"), "label", 80)
        category = slug(item["category"]) if item.get("category") not in (None, "") else ""
        groups.setdefault(_world_text(item.get("group"), "group", 80), []).append(
            {"id": unique, "label": label if len(label) <= 40 else label[:39] + "…", "category": category, "body": item.get("body", "")})
    floors = []
    for group, spots in groups.items():
        for part, start in enumerate(range(0, len(spots), 64)):
            chunk = spots[start:start + 64]
            rows = -(-len(chunk) // columns)
            floors.append({"id": f"f{len(floors) + 1}", "label": (group if part == 0 else f"{group} {part + 1}")[:40],
                           "width": 2 * margin + min(columns, len(chunk)) * cell[0], "height": 2 * margin + rows * cell[1],
                           "spots": [{"id": spot["id"], "label": spot["label"], "category": spot["category"], "body": spot["body"],
                                      "x": margin + (i % columns) * cell[0] + cell[0] // 2, "y": margin + (i // columns) * cell[1] + cell[1] // 2}
                                     for i, spot in enumerate(chunk)]})
    if len(floors) > 8:
        raise ValueError("a world has at most 8 floors: fewer groups, or fewer than 64 items in each")
    spec = {"schema": WORLD_SCHEMA, "id": id, "title": title, "floors": floors, **({"shell": True} if shell else {}), **({"tools": tools} if tools else {})}
    return world_validate(spec)


EXAMPLES: dict[str, Any] = {
    'world': {'schema': 'web-ui-world/1',
           'id': 'demo',
           'title': 'web-ui world (prototype)',
           'zoom_max': 4,
           'shots': [{'id': 'gate',
                      'label': 'SHOT 01',
                      'title': 'Arrive',
                      'body': 'One page, no page changes. Scroll to move the camera through the shots.',
                      'bg': '#0d1f3a'},
                     {'id': 'hall',
                      'label': 'SHOT 02',
                      'title': 'Look around',
                      'body': 'Each shot is data: a label, a title, a text and a color. Python writes the HTML and '
                              'CSS.',
                      'bg': '#164a41'},
                     {'id': 'deck',
                      'label': 'SHOT 03',
                      'title': 'Zoom in',
                      'body': 'The only JavaScript marks what is on screen; CSS reacts to that mark.',
                      'bg': '#5a2a1a'},
                     {'id': 'exit',
                      'label': 'SHOT 04',
                      'title': 'Find it',
                      'body': 'Scrolling reaches the information you came for.',
                      'bg': '#2a2a5a'}],
           'floors': [{'id': '1f',
                       'label': '1F',
                       'width': 960,
                       'height': 640,
                       'spots': [{'id': 'gate',
                                  'x': 120,
                                  'y': 320,
                                  'label': 'Gate',
                                  'category': 'info',
                                  'body': 'Entrance and help desk.'},
                                 {'id': 'hall',
                                  'x': 480,
                                  'y': 320,
                                  'label': 'Hall',
                                  'category': 'info',
                                  'body': 'The central hall connects every area.'},
                                 {'id': 'cafe',
                                  'x': 800,
                                  'y': 160,
                                  'label': 'Cafe',
                                  'category': 'food',
                                  'body': 'Drinks and light meals.'},
                                 {'id': 'shop',
                                  'x': 800,
                                  'y': 480,
                                  'label': 'Shop',
                                  'category': 'food',
                                  'body': 'Snacks and souvenirs.'}],
                       'actors': [{'id': 'farmer',
                                   'emoji': '🧑\u200d🌾',
                                   'label': 'Farmer',
                                   'body': 'Walks at a steady pace and stops to look around. Tap to ask.'},
                                  {'id': 'cat',
                                   'emoji': '🐈',
                                   'label': 'Cat',
                                   'body': 'Wanders; no destination.',
                                   'speed': 64},
                                  {'id': 'duck',
                                   'emoji': '🦆',
                                   'label': 'Duck',
                                   'body': 'Slow and sure.',
                                   'speed': 32},
                                  {'id': 'robot',
                                   'emoji': '🤖',
                                   'label': 'Robot',
                                   'body': 'Moves in straight lines at constant speed.',
                                   'speed': 56}],
                       'player': {'emoji': '🧙', 'x': 120, 'y': 320}},
                      {'id': '2f',
                       'label': '2F',
                       'width': 960,
                       'height': 640,
                       'spots': [{'id': 'deck',
                                  'x': 240,
                                  'y': 160,
                                  'label': 'Deck',
                                  'category': 'info',
                                  'body': 'Open-air deck with a view of the hall.'},
                                 {'id': 'lab',
                                  'x': 720,
                                  'y': 400,
                                  'label': 'Lab',
                                  'category': 'info',
                                  'body': 'Hands-on corner for the curious.'}],
                       'actors': [{'id': 'owl',
                                   'emoji': '🦉',
                                   'label': 'Owl',
                                   'body': 'Keeps the deck company.',
                                   'speed': 40}]}],
           'board': {'title': 'INFO',
                     'items': [{'text': 'Gate: wait about 10 min'},
                               {'text': 'Show starts', 'at': '10:30'},
                               {'text': 'Guided walk', 'at': '14:00'},
                               {'text': 'Last entry', 'at': '17:30'},
                               {'text': 'London lunch', 'at': '12:00', 'zone': 'london'},
                               {'text': 'Open hours', 'gauge': {'from': '09:00', 'to': '18:00', 'cells': 10, 'glyphs': 'hourglass'}},
                               {'text': 'Daylight', 'gauge': {'from': '06:00', 'to': '22:00', 'cells': 8, 'glyphs': 'moon'}}],
                     'shared_issue': 'myon-bioinformatics/PySaiyanWeBoo/110',
                     'post': True,
                     'offset_label': True,
                     'zones': [{'id': 'tokyo', 'label': 'Tokyo', 'tz': 'Asia/Tokyo'},
                               {'id': 'london', 'label': 'London', 'tz': 'Europe/London'},
                               {'id': 'ny', 'label': 'New York', 'tz': 'America/New_York'}]}},
}

# Real places in miniature (the `place` floor): latitude and longitude in, tiles out. The coordinates are approximate (about 100 m, read off public
# maps), which is all a miniature needs; the point is where things stand relative to each other, so nothing here is a facility's exact position.
_CITY_MARKS = {"exit": "🎫", "station": "🚉", "terminus": "🚆"}   # the mark drawn instead of the dot, by category: the cities are their transport (🛗 is the footer's)


def _pt(id: str, label: str, lat: float, lon: float, category: str, body: str = "", flip: str = "", sign: str = "") -> dict[str, Any]:
    return {"id": id, "label": label, "lat": lat, "lon": lon, "category": category, "body": body, **({"flip": flip} if flip else {}),
            **({"sign": sign} if sign else {})}


_TOKYO_POINTS = [
    _pt("marunouchi-c", "丸の内中央口", 35.68134, 139.7665, "exit", "東京駅の丸の内側、ちょうど真ん中の出入口です。"),
    _pt("marunouchi-n", "丸の内北口", 35.6824, 139.7664, "exit", "東京駅の丸の内側、北の出入口です。"),
    _pt("marunouchi-s", "丸の内南口", 35.68025, 139.76625, "exit", "東京駅の丸の内側、南の出入口です。"),
    _pt("yaesu-c", "八重洲中央口", 35.6813, 139.7686, "exit", "東京駅の八重洲側、ちょうど真ん中の出入口です。"),
    _pt("yaesu-n", "八重洲北口", 35.6825, 139.7685, "exit", "東京駅の八重洲側、北の出入口です。"),
    _pt("yaesu-s", "八重洲南口", 35.6801, 139.7684, "exit", "東京駅の八重洲側、南の出入口です。"),
    _pt("otemachi", "大手町", 35.6867, 139.7631, "station", "東京駅の北西、歩いて行ける駅です。"),
    _pt("nijubashimae", "二重橋前", 35.6804, 139.7612, "station", "東京駅の西、丸の内の駅です。"),
    _pt("yurakucho", "有楽町", 35.6751, 139.7631, "station", "東京駅の南、ひと駅となりです。"),
    _pt("hibiya", "日比谷", 35.674, 139.7598, "station", "有楽町の西にある駅です。"),
    _pt("ginza", "銀座", 35.6719, 139.7639, "station", "有楽町の南にある駅です。"),
    _pt("ginza-itchome", "銀座一丁目", 35.6745, 139.7672, "station", "銀座の北東にある駅です。"),
    _pt("kyobashi", "京橋", 35.6768, 139.7702, "station", "東京駅の南東、八重洲のむこうの駅です。"),
    _pt("nihombashi", "日本橋", 35.682, 139.7743, "station", "東京駅の東、八重洲のむこうの駅です。"),
    _pt("mitsukoshimae", "三越前", 35.6868, 139.7737, "station", "日本橋の北にある駅です。"),
    _pt("shin-nihombashi", "新日本橋", 35.6898, 139.7741, "station", "三越前の北にある駅です。"),
    _pt("kanda", "神田", 35.6918, 139.7709, "station", "東京駅の北、ひと駅となりです。"),
    _pt("takebashi", "竹橋", 35.6906, 139.7586, "station", "大手町の北西にある駅です。"),
    _pt("shimbashi", "新橋", 35.6663, 139.7583, "station", "有楽町の南、ふた駅となりです。"),
    _pt("concourse", "◀ 丸の内 | 八重洲 ▶", 35.68075, 139.76755, "sign", "東京駅の、丸の内口と八重洲口のあいだです。", "", "led"),
    _pt("north-south", "▲ 神田 | 有楽町 ▼", 35.6838, 139.7676, "sign", "東京駅の北と南、となりの駅の方向です。", "", "led"),
]
_TOKYO_LINKS = [["marunouchi-n", "marunouchi-c"], ["marunouchi-c", "marunouchi-s"], ["yaesu-n", "yaesu-c"], ["yaesu-c", "yaesu-s"], ["marunouchi-c", "yaesu-c"],
    ["otemachi", "marunouchi-n"], ["takebashi", "otemachi"], ["nijubashimae", "marunouchi-s"], ["yurakucho", "marunouchi-s"], ["hibiya", "yurakucho"],
    ["ginza", "yurakucho"], ["shimbashi", "ginza"], ["ginza-itchome", "yaesu-s"], ["kyobashi", "yaesu-s"], ["nihombashi", "yaesu-c"],
    ["mitsukoshimae", "nihombashi"], ["shin-nihombashi", "mitsukoshimae"], ["kanda", "shin-nihombashi"]]
_LONDON_POINTS = [
    _pt("kings-cross", "キングス・クロス", 51.5309, -0.1233, "terminus", "北へ向かう列車が出る大きな駅です。"),
    _pt("st-pancras", "セント・パンクラス", 51.5322, -0.1269, "terminus", "海をわたる列車も出る、赤れんがの駅です。"),
    _pt("euston", "ユーストン", 51.5282, -0.1337, "terminus", "北西へ向かう列車の駅です。"),
    _pt("paddington", "パディントン", 51.5154, -0.1755, "terminus", "西へ向かう列車の駅です。"),
    _pt("marylebone", "マリルボーン", 51.5225, -0.1631, "terminus", "こぢんまりとした北西の駅です。"),
    _pt("liverpool-street", "リバプール・ストリート", 51.5178, -0.0823, "terminus", "東へ向かう列車の駅です。"),
    _pt("fenchurch-street", "フェンチャーチ・ストリート", 51.5115, -0.0789, "terminus", "東の海辺へ向かう列車の駅です。"),
    _pt("cannon-street", "キャノン・ストリート", 51.5113, -0.0904, "terminus", "川の北岸にある、南東へ向かう駅です。"),
    _pt("london-bridge", "ロンドン・ブリッジ", 51.5052, -0.0864, "terminus", "川の南岸にある、南へ向かう駅です。"),
    _pt("blackfriars", "ブラックフライアーズ", 51.512, -0.103, "terminus", "橋の上に駅がある、川をまたぐ駅です。"),
    _pt("waterloo", "ウォータールー", 51.5031, -0.1132, "terminus", "川の南岸にある、いちばん大きな駅です。"),
    _pt("charing-cross", "チャリング・クロス", 51.508, -0.1247, "terminus", "川の北岸にある、南東へ向かう駅です。"),
    _pt("victoria", "ヴィクトリア", 51.4952, -0.1441, "terminus", "南へ向かう列車の駅です。"),
    _pt("edgware-road", "エッジウェア・ロード", 51.5199, -0.1679, "station", "パディントンとマリルボーンの間の駅です。"),
    _pt("baker-street", "ベイカー・ストリート", 51.5226, -0.1571, "station", "マリルボーンのとなりの駅です。"),
    _pt("warren-street", "ウォーレン・ストリート", 51.5247, -0.1384, "station", "ユーストンのとなりの駅です。"),
    _pt("angel", "エンジェル", 51.5322, -0.1058, "station", "キングス・クロスの東のとなりの駅です。"),
    _pt("russell-square", "ラッセル・スクエア", 51.523, -0.1244, "station", "キングス・クロスの南のとなりの駅です。"),
    _pt("farringdon", "ファリンドン", 51.5203, -0.1053, "station", "キングス・クロスの南東のとなりの駅です。"),
    _pt("moorgate", "ムーアゲート", 51.5186, -0.0886, "station", "リバプール・ストリートの西のとなりの駅です。"),
    _pt("aldgate", "オールドゲート", 51.5143, -0.0755, "station", "リバプール・ストリートの南東のとなりの駅です。"),
    _pt("tower-hill", "タワー・ヒル", 51.5098, -0.0766, "station", "フェンチャーチ・ストリートのとなりの駅です。"),
    _pt("bank", "バンク", 51.5133, -0.0886, "station", "キャノン・ストリートのとなりの駅です。"),
    _pt("monument", "モニュメント", 51.5108, -0.0863, "station", "キャノン・ストリートの東のとなりの駅です。"),
    _pt("borough", "ボロー", 51.5011, -0.0943, "station", "ロンドン・ブリッジの南西のとなりの駅です。"),
    _pt("st-pauls", "セント・ポールズ", 51.5146, -0.0973, "station", "ブラックフライアーズの北東のとなりの駅です。"),
    _pt("temple", "テンプル", 51.5111, -0.1141, "station", "ブラックフライアーズの西のとなりの駅です。"),
    _pt("southwark", "サザーク", 51.504, -0.1052, "station", "川の南、ウォータールーの東のとなりの駅です。"),
    _pt("lambeth-north", "ランベス・ノース", 51.4991, -0.1115, "station", "ウォータールーの南のとなりの駅です。"),
    _pt("embankment", "エンバンクメント", 51.5074, -0.1223, "station", "チャリング・クロスのとなりの駅です。"),
    _pt("westminster", "ウェストミンスター", 51.501, -0.1254, "station", "チャリング・クロスの南のとなりの駅です。"),
    _pt("green-park", "グリーン・パーク", 51.5067, -0.1428, "station", "ヴィクトリアの北のとなりの駅です。"),
    _pt("pimlico", "ピムリコ", 51.4893, -0.1334, "station", "ヴィクトリアの南東のとなりの駅です。"),
    _pt("nogard", "nogard", 51.5024, -0.1118, "sign", "うしろから読んでみて。", "🐉", "wood"),
    _pt("mind-the-gap", "mind the gap", 51.4958, -0.1445, "sign", "駅のホームでよく聞く言葉です。", "", "led"),
    _pt("platform", "◀ 北 | 南 ▶", 51.5290, -0.1270, "sign", "キングス・クロスとセント・パンクラスの前です。", "", "led"),
]
_LONDON_LINKS = [["paddington", "edgware-road"], ["marylebone", "edgware-road"], ["marylebone", "baker-street"], ["euston", "warren-street"], ["kings-cross",
    "euston"], ["kings-cross", "st-pancras"], ["kings-cross", "russell-square"], ["kings-cross", "angel"], ["farringdon", "kings-cross"],
    ["liverpool-street", "moorgate"], ["liverpool-street", "aldgate"], ["fenchurch-street", "tower-hill"], ["fenchurch-street", "aldgate"],
    ["cannon-street", "bank"], ["cannon-street", "monument"], ["london-bridge", "borough"], ["london-bridge", "monument"], ["blackfriars", "temple"],
    ["blackfriars", "st-pauls"], ["blackfriars", "southwark"], ["waterloo", "lambeth-north"], ["waterloo", "southwark"], ["waterloo",
    "charing-cross"], ["charing-cross", "embankment"], ["charing-cross", "westminster"], ["victoria", "green-park"], ["victoria", "pimlico"],
    ["moorgate", "bank"]]
_THAMES = {"line": [[51.4852, -0.1495], [51.4875, -0.127], [51.4945, -0.123], [51.5008, -0.1219], [51.5062, -0.1198], [51.5086, -0.1169], [51.5099, -0.1043], [51.5095, -0.0985], [51.5088, -0.0937], [51.5079, -0.0877], [51.5055, -0.0754], [51.504, -0.06]], "width": 2}

_PARIS_POINTS = [
    _pt("gare-du-nord", "パリ北駅", 48.8809, 2.3553, "terminus", "北へ向かう列車の大きな駅です。"),
    _pt("gare-de-lest", "パリ東駅", 48.8768, 2.3592, "terminus", "東へ向かう列車の駅です。"),
    _pt("saint-lazare", "サン・ラザール駅", 48.8763, 2.3258, "terminus", "西へ向かう列車の駅です。"),
    _pt("gare-de-lyon", "リヨン駅", 48.8443, 2.3736, "terminus", "南東へ向かう列車の駅です。"),
    _pt("austerlitz", "オステルリッツ駅", 48.8421, 2.3652, "terminus", "川の南岸にある、南西へ向かう駅です。"),
    _pt("montparnasse", "モンパルナス駅", 48.8412, 2.3203, "terminus", "川の南にある、西へ向かう駅です。"),
    _pt("poissonniere", "ポワソニエール", 48.8772, 2.3492, "station", "北駅の西のとなりの駅です。"),
    _pt("barbes", "バルベス・ロシュシュアール", 48.8838, 2.3498, "station", "北駅の北西のとなりの駅です。"),
    _pt("chateau-deau", "シャトー・ドー", 48.8737, 2.3552, "station", "東駅の南のとなりの駅です。"),
    _pt("louis-blanc", "ルイ・ブラン", 48.8812, 2.3649, "station", "東駅の北東のとなりの駅です。"),
    _pt("havre-caumartin", "アーヴル・コーマルタン", 48.8737, 2.3282, "station", "サン・ラザール駅の南のとなりの駅です。"),
    _pt("europe", "ヨーロッパ", 48.8788, 2.3225, "station", "サン・ラザール駅の北西のとなりの駅です。"),
    _pt("bastille", "バスティーユ", 48.8531, 2.3692, "station", "リヨン駅の北西のとなりの駅です。"),
    _pt("quai-de-la-rapee", "ケ・ド・ラ・ラペ", 48.8465, 2.366, "station", "リヨン駅とオステルリッツ駅のあいだの駅です。"),
    _pt("saint-marcel", "サン・マルセル", 48.8383, 2.3603, "station", "オステルリッツ駅の南のとなりの駅です。"),
    _pt("jussieu", "ジュシュー", 48.8463, 2.3548, "station", "オステルリッツ駅の北西のとなりの駅です。"),
    _pt("edgar-quinet", "エドガー・キネ", 48.8409, 2.3252, "station", "モンパルナス駅の東のとなりの駅です。"),
    _pt("vavin", "ヴァヴァン", 48.8421, 2.3282, "station", "モンパルナス駅の北東のとなりの駅です。"),
    _pt("falguiere", "ファルギエール", 48.8444, 2.3098, "station", "モンパルナス駅の西のとなりの駅です。"),
    _pt("to-lyon", "▶ Lyon", 48.8449, 2.3728, "sign", "リヨン駅から、リヨンへ向かう列車が出ます。", "", "led"),
    _pt("rive-gauche", "rive gauche ▼", 48.8530, 2.3440, "sign", "川の南がわ、左岸という意味です。", "", "wood"),
]
_PARIS_LINKS = [["gare-du-nord", "poissonniere"], ["gare-du-nord", "barbes"], ["gare-de-lest", "chateau-deau"], ["gare-de-lest", "louis-blanc"], ["gare-du-nord",
    "gare-de-lest"], ["saint-lazare", "havre-caumartin"], ["saint-lazare", "europe"], ["gare-de-lyon", "bastille"], ["gare-de-lyon",
    "quai-de-la-rapee"], ["quai-de-la-rapee", "austerlitz"], ["austerlitz", "saint-marcel"], ["austerlitz", "jussieu"], ["montparnasse",
    "edgar-quinet"], ["montparnasse", "vavin"], ["montparnasse", "falguiere"]]
_SEINE = {"line": [[48.833, 2.38], [48.8372, 2.3737], [48.845, 2.3668], [48.8506, 2.3622], [48.8545, 2.354], [48.856, 2.349], [48.8573, 2.3413], [48.8585, 2.3377], [48.8609, 2.3306], [48.8637, 2.3203], [48.864, 2.3135], [48.8638, 2.3012], [48.8613, 2.2935], [48.855, 2.2877], [48.848, 2.276]], "width": 1}


POTATO_RUMOR = "昼ヶ丘のいもを焼くと、リバースロンドンの木の看板の陰から鼻先がのぞくんだって。ドラゴンもあの甘い匂いが好きみたいだよ。"


def _overworld_spec() -> dict[str, Any]:
    """Overworld prototype centered on はじまりの村 (``meadow``) with contact dialogue, drops/chests, turn-based RPG battle and gamification."""
    def spot(sid: str, tx: int, ty: int, label: str, category: str, body: str, *, item: dict[str, Any] | None = None,
             always_named: bool | str = False, mark: str | None = None) -> dict[str, Any]:
        out: dict[str, Any] = {"id": sid, "x": tx * 32 + 16, "y": ty * 32 + 16, "label": label, "category": category, "body": body}
        if item:
            out["item"] = item
        if always_named:
            out["always_named"] = always_named
        if mark:
            out["mark"] = mark
        return out

    def land_spots(theme: str, seed: int, extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [*land_floor(theme, seed=seed, id=theme)["spots"], *extra]

    meadow_spots = land_spots("meadow", 1, [
        spot("meadow-hirugaoka", 18, 5, "🍠 昼ヶ丘（ヒルガオカ）", "landmark",
             "ヒルガオ科のサツマイモを育てている、日当たりのよい丘です。",
             item={"emoji": "🍠", "label": "サツマイモ", "body": "昼ヶ丘で育てたヒルガオ科のいも。食べると経験値が20増えます。誰におすそ分けするか、村の道具屋に聞いてみよう。"}),
        spot("meadow-npc-cat", 13, 13, "🐱 案内猫ミョン", "npc",
             "はじまりの村の入口にいる案内猫。近づくと操作と冒険の基本を教えてくれます。", mark="🐱"),
        spot("meadow-npc-elder", 11, 8, "👴 村長", "npc",
             "はじまりの村を見守る長老。ポートフォリオと冒険の目的を語ってくれます。", mark="👴"),
        spot("meadow-npc-smith", 9, 8, "⚒️ 道具屋の店主", "npc",
             "冒険に役立つ回復アイテムやだんごをゴールドで販売しています。", mark="⚒️"),
        spot("meadow-npc-researcher", 15, 8, "🔬 研究員", "npc",
             "バイオインフォマティクスと個人開発リポジトリのクイズを出題します。", mark="🔬"),
        spot("meadow-npc-fountain", 15, 9, "⛲ 回復の泉", "npc",
             "清らかな水が湧く泉。触れると傷ついた体と魔力をやさしく癒してくれます。", mark="⛲"),
        spot("meadow-npc-monument", 13, 7, "🗿 PSWB石碑", "npc",
             "PySaiyanWeBoo（PSWB）と共通UI設計の歴史が刻まれた村の記念碑。", mark="🗿"),
        spot("meadow-drop-herb", 11, 11, "🌿 やくそう", "item",
             "道ばたに落ちている香り高い薬草。戦闘中や冒険手帳から使えます。",
             item={"emoji": "🌿", "label": "やくそう", "body": "HPを15回復するみずみずしい薬草。"}, mark="🌿"),
        spot("meadow-drop-mana", 6, 7, "💧 癒しの水", "item",
             "人に使うとMPを10回復。パリでは目の前の火を一つ消せます。",
             item={"emoji": "💧", "label": "癒しの水", "body": "MP回復か消火に一度だけ使える水。"}, mark="💧"),
        spot(EXPLORATION_SCROLL["id"], 20, 12, "📜 " + EXPLORATION_SCROLL["label"], "item",
             "近くのどうぐの在りかを照らす古い巻物。" + exploration_scroll_text()["reuse"],
             item={"emoji": "📜", "label": EXPLORATION_SCROLL["label"],
                   "body": "".join(exploration_scroll_text().values())}, mark="📜"),
        spot("meadow-chest-sword", 9, 9, "🎁 はじまりの剣", "item",
             "村の片隅に置かれた宝箱。装備すると攻撃力（ATK）が上がります。",
             item={"emoji": "🗡️", "label": "はじまりの剣", "body": "PySaiyanWeBooの剣。持っているだけで ATK +4。"}, mark="🎁"),
        spot("meadow-chest-shield", 20, 3, "🎁 守りの盾", "item",
             "北東の木立に隠された宝箱。防御力（DEF）と最大HPが上がります。",
             item={"emoji": "🛡️", "label": "守りの盾", "body": "堅牢なテストの盾。DEF +3、最大HP +6。"}, mark="🎁"),
        spot("meadow-chest-charm", 3, 12, "🎁 PSWBの護符", "item",
             "ボス魔物が守る特別な宝箱。全ステータスを底上げします。",
             item={"emoji": "🔮", "label": "PSWBの護符", "body": "ATK +2、DEF +2、最大MP +5。ボス討伐で開く。"}, mark="🎁"),
        spot("meadow-enemy-slime", 8, 12, "🟢 バグスライム", "battle",
             "仕様のスキマから生まれたぷるぷるのスライム。『バグ』属性の技に弱い。", mark="🟢"),
        spot("meadow-enemy-bat", 17, 10, "🦇 タイポコウモリ", "battle",
             "夜な夜な識別子を綴り間違えるコウモリ。『パイプライン』技が効果的。", mark="🦇"),
        spot("meadow-enemy-golem", 12, 3, "👾 スパゲッティゴーレム", "battle",
             "北の空地に棲むこの地域のボス。3ターンごとの強攻撃は『ぼうぎょ』で防ごう。", mark="👾"),
    ])

    return {
        "schema": WORLD_SCHEMA, "id": "overworld", "title": "Overworld (prototype)", "zoom_max": 4, "move": "confirm",
        "avatars": ["🙂", "🧙", "🧝", "🦸", "🐱", "🐶", "🦊", "🐉", "🦄", "⚔️", "🛡️", "🚀"],
        "tools": {
            "🧭": {"label": "町", "label_en": "Towns", "labels": {"fr": "Villes", "es": "Pueblos", "de": "Orte", "zh": "城镇"},
                   "spots": ["meadow-town", "forest-town", "desert-town", "coast-town", "castle-town"]},
            "🗺️": {"label": "冒険ガイド", "label_en": "RPG Guide", "labels": {"fr": "Guide RPG", "es": "Guía RPG", "de": "RPG-Führer", "zh": "冒险指南"},
                   "spots": ["meadow-npc-cat", "meadow-npc-fountain", "meadow-npc-researcher", "meadow-npc-smith", "meadow-enemy-golem"]},
        },
        "board": {"title": "TRAVEL", "items": [
            {"text": "ようこそ はじまりの村へ！"},
            {"text": "🐱・🌿・🎁・👾に近づくとイベント発生"},
            {"text": "📜冒険手帳と⚔️戦闘で強くなろう"},
            {"text": "🛗で6つの土地をわたろう"},
        ]},
        "floors": [
            {"id": "meadow", "land": {"theme": "meadow", "seed": 1}, "spots": meadow_spots,
             "actors": [
                 {"id": "meadow-cat", "emoji": "🐱", "label": "散歩猫", "body": "気まぐれに村をパトロールしている黒ぶち猫。", "speed": 28, "seed": 101},
                 {"id": "meadow-dog", "emoji": "🐕", "label": "村の番犬", "body": "北側のバグ魔物を見張っている頼れる番犬。", "speed": 34, "seed": 202},
                 {"id": "meadow-bird", "emoji": "🐦", "label": "伝令バト", "body": "各リポジトリの更新を運ぶ小さな鳥。", "speed": 42, "seed": 303},
             ]},
            {"id": "forest", "land": {"theme": "forest", "seed": 2},
             "spots": land_spots("forest", 2, [
                 spot("forest-chest-cloak", 1, 5, "🎁 森のマント", "item", "森の奥の木陰に置かれた宝箱。",
                      item={"emoji": "🧥", "label": "森のマント", "body": "自然の加護。DEF +3、最大HP +8。"}, mark="🎁"),
                 spot("forest-enemy-ent", 22, 10, "🌳 古樹トレント", "battle", "古い依存関係が絡み合った森の番人。", mark="🌳"),
             ])},
            {"id": "mountain", "land": {"theme": "mountain", "seed": 3},
             "spots": land_spots("mountain", 3, [
                 spot("mountain-chest-pick", 1, 4, "🎁 岩砕きのツルハシ", "item", "岩壁のそばに残された頑丈な道具。",
                      item={"emoji": "⛏️", "label": "岩砕きのツルハシ", "body": "重い岩も一撃。ATK +5。"}, mark="🎁"),
                 spot("mountain-enemy-gargoyle", 22, 12, "🪨 岩ゴーレム", "battle", "固いロックファイルのように手ごわい山の巨人。", mark="🪨"),
             ])},
            {"id": "desert", "land": {"theme": "desert", "seed": 4},
             "spots": land_spots("desert", 4, [
                 spot("desert-drop-elixir", 1, 4, "🏺 砂漠の秘薬", "item", "オアシスの旅人が落とした霊薬。",
                      item={"emoji": "🏺", "label": "砂漠の秘薬", "body": "HPを30・MPを10回復する秘薬。"}, mark="🏺"),
                 spot("desert-enemy-scorpion", 22, 11, "🦂 大サソリ", "battle", "乾いたログから現れる素早い大サソリ。", mark="🦂"),
             ])},
            {"id": "coast", "land": {"theme": "coast", "seed": 5},
             "spots": land_spots("coast", 5, [
                 spot("coast-chest-compass", 1, 7, "🎁 航海の羅針盤", "item", "潮風が運んできた正確な羅針盤。",
                      item={"emoji": "🧭", "label": "航海の羅針盤", "body": "迷わず進む指針。ATK +3、DEF +2。"}, mark="🎁"),
                 spot("coast-enemy-kraken", 22, 11, "🦑 潮風クラーケン", "battle", "海辺のタイムアウトを巻き起こす大イカ。", mark="🦑"),
             ])},
            {"id": "castle", "land": {"theme": "castle", "seed": 6},
             "spots": land_spots("castle", 6, [
                 spot("castle-chest-crown", 1, 4, "🎁 王冠バッジ", "item", "城の一角に眠る開発者の勲章。",
                      item={"emoji": "👑", "label": "王冠バッジ", "body": "ATK +5、DEF +4、最大HP +12。"}, mark="🎁"),
                 spot("castle-enemy-daemon", 22, 12, "🐲 幻影ドラゴン", "battle", "最終テストを守る伝説の竜。", mark="🐲"),
             ])},
            {"id": "real", "label": "実空間×仮想", "width": 384, "height": 384, "tile": 32, "real": True,
             "spots": [{"id": "real-gate", "label": "入口", "x": 192, "y": 96,
                        "body": "⋯ の 🖼️📷 で、写真かカメラをうしろに映せます（ページの中だけ。保存も送信もしません）。"}],
             "player": {"emoji": "🙂", "x": 192, "y": 288, "speed": 96}},
        ],
        "rpg": {
            "seed": 20261126,
            "hero": {"hp": 32, "mp": 14, "atk": 6, "def": 2, "gold": 25},
            "npcs": {
                "meadow-npc-cat": {
                    "speaker": "案内猫ミョン", "emoji": "🐱", "on_contact": True,
                    "greeting": "にゃーん！ ようこそ『はじまりの村』へ！ まずは基本の歩き方をお伝えしますにゃ。",
                    "lines": [
                        "矢印キー / WASD / 画面下の十字ボタンで歩けます。村人(🐱👴🔬)や落ちもの(🌿💧)、宝箱(🎁)、魔物(🟢🦇👾)に近づくとイベントが始まるにゃ！",
                        "上の『📜』ボタンでクエスト・実績・図鑑・装備を確認できますにゃ。まずは道ばたの🌿やくそうや🎁はじまりの剣を探してみよう！",
                    ],
                },
                "meadow-npc-elder": {
                    "speaker": "村長", "emoji": "👴", "on_contact": True,
                    "greeting": "ほう、旅のエンジニアか！ この村は『myon-bioinformatics』の学びと実験が集うはじまりの場所じゃ。",
                    "lines": [
                        "PythonやFlutterの共通UI（PySaiyanWeBoo）から生まれ、バイオインフォマティクスやCLIツールへと枝分かれしていったのだ。",
                        "まずは研究員(🔬)のクイズで知識を試し、北にいる『👾 スパゲッティゴーレム』を鎮めてくれぬか？",
                    ],
                },
                "meadow-npc-smith": {
                    "speaker": "道具屋の店主", "emoji": "⚒️", "on_contact": True, "shop": True,
                    "greeting": "いらっしゃい！ 旅の支度はばっちりかい？ 魔物から得たゴールドで回復どうぐを買えるぞ。",
                    "lines": ["『おみせ』ボタンを押せば、昼ヶ丘名物のサツマイモだんごも並べてあるよ！"],
                    "topic": {"question": "サツマイモは誰にあげるといい？", "answer": POTATO_RUMOR},
                },
                "meadow-npc-researcher": {
                    "speaker": "研究員", "emoji": "🔬", "on_contact": True, "quiz": True,
                    "greeting": "こんにちは！ ここでは GitHub リポジトリとポートフォリオにまつわるミニクイズを出しています。",
                    "lines": ["1問正解するごとに経験値(+20 EXP)と研究費(+25 G)を進呈！ 全8問、ぜひ挑戦してみてください。"],
                },
                "meadow-npc-fountain": {
                    "speaker": "回復の泉", "emoji": "⛲", "on_contact": True, "heal": True,
                    "greeting": "澄みわたる泉の水面がきらきらと光っている……。『いやす』で何度でも全回復できます。",
                    "lines": ["ピンチのときはいつでもこの泉にもどってきてくださいね。"],
                },
                "meadow-npc-monument": {
                    "speaker": "PSWB石碑", "emoji": "🗿", "on_contact": True,
                    "greeting": "【碑文】PySaiyanWeBoo（PSWB）：1ファイル完結の設計と決定的RNG・オーブ演出がここに息づく。",
                    "lines": [
                        "Ironmateの『見かけも中身も同じ』検証原則や、Aoiの軽量モジュール連携もこの世界と同じ思想で組み立てられています。",
                        "すべての計算はページ内のピュア関数だけで完結し、外部へ勝手に送信することはありません。",
                    ],
                },
                "meadow-cat": {
                    "speaker": "散歩猫", "emoji": "🐱",
                    "greeting": "ぐるる… 今日も昼ヶ丘のサツマイモが豊作だにゃ。",
                    "lines": ["北の方にはスパゲッティコードから生まれたゴーレムがいるから、🎁はじまりの剣を取ってから向かうのにゃ！"],
                },
                "meadow-dog": {
                    "speaker": "村の番犬", "emoji": "🐕",
                    "greeting": "ワン！ 村の西に🟢バグスライム、東に🦇タイポコウモリが出没しているぞ。",
                    "lines": ["戦闘の『✨ とくぎ』で弱点を突けば一気にカタがつくワン！"],
                },
                "meadow-bird": {
                    "speaker": "伝令バト", "emoji": "🐦",
                    "greeting": "クルックー！ フッターの🛗から森・山・砂漠・海辺・お城へも旅立てますよ！",
                    "lines": ["それぞれの土地にも、宝箱と守護モンスターが1つずつ隠れています！"],
                },
            },
            "loot": {
                "meadow-drop-herb": {"kind": "drop", "item_type": "heal", "hp": 15, "exp": 5},
                "meadow-drop-mana": {"kind": "drop", "item_type": "mana", "mp": 10, "exp": 5},
                EXPLORATION_SCROLL["id"]: {"kind": "drop", "item_type": "scroll", "exp": 8},
                "meadow-chest-sword": {"kind": "chest", "item_type": "weapon", "atk": 4, "exp": 10, "gold": 15, "opened_mark": "📭"},
                "meadow-chest-shield": {"kind": "chest", "item_type": "armor", "def": 3, "hp": 6, "exp": 10, "gold": 15, "opened_mark": "📭"},
                "meadow-chest-charm": {"kind": "chest", "item_type": "charm", "atk": 2, "def": 2, "mp": 5, "exp": 25, "gold": 40,
                                       "opened_mark": "📭", "requires_enemy": "meadow-enemy-golem"},
                "meadow-hirugaoka": {"kind": "drop", "item_type": "food", "exp": 5},
                "forest-chest-cloak": {"kind": "chest", "item_type": "armor", "def": 3, "hp": 8, "exp": 15, "gold": 25, "opened_mark": "📭"},
                "mountain-chest-pick": {"kind": "chest", "item_type": "weapon", "atk": 5, "exp": 20, "gold": 30, "opened_mark": "📭"},
                "desert-drop-elixir": {"kind": "drop", "item_type": "heal", "hp": 30, "mp": 10, "exp": 15},
                "coast-chest-compass": {"kind": "chest", "item_type": "charm", "atk": 3, "def": 2, "exp": 20, "gold": 35, "opened_mark": "📭"},
                "castle-chest-crown": {"kind": "chest", "item_type": "trophy", "atk": 5, "def": 4, "hp": 12, "exp": 40, "gold": 80, "opened_mark": "📭"},
            },
            "enemies": {
                "meadow-enemy-slime": {"name": "バグスライム", "emoji": "🟢", "level": 1, "hp": 18, "atk": 6, "def": 1,
                                       "exp": 18, "gold": 20, "weakness": "バグ", "on_contact": True,
                                       "taunt": "ぬるぬるしたバグスライムが飛び出してきた！"},
                "meadow-enemy-bat": {"name": "タイポコウモリ", "emoji": "🦇", "level": 2, "hp": 24, "atk": 8, "def": 2,
                                     "exp": 25, "gold": 28, "weakness": "パイプライン", "on_contact": True,
                                     "taunt": "識別子をかじるタイポコウモリが襲いかかってきた！"},
                "meadow-enemy-golem": {"name": "スパゲッティゴーレム", "emoji": "👾", "level": 4, "hp": 44, "atk": 11, "def": 3,
                                       "exp": 60, "gold": 80, "weakness": "パイプライン", "drop_spot": "meadow-chest-charm",
                                       "boss": True, "on_contact": True, "taunt": "巨大ボス『スパゲッティゴーレム』が立ちはだかる！"},
                "forest-enemy-ent": {"name": "古樹トレント", "emoji": "🌳", "level": 3, "hp": 34, "atk": 9, "def": 3,
                                     "exp": 35, "gold": 40, "weakness": "バグ", "on_contact": True,
                                     "taunt": "絡みつく枝の古樹トレントが現れた！"},
                "mountain-enemy-gargoyle": {"name": "岩ゴーレム", "emoji": "🪨", "level": 4, "hp": 42, "atk": 11, "def": 4,
                                            "exp": 45, "gold": 55, "weakness": "パイプライン", "on_contact": True,
                                            "taunt": "ロックファイルを背負った岩ゴーレムが目を覚ました！"},
                "desert-enemy-scorpion": {"name": "大サソリ", "emoji": "🦂", "level": 4, "hp": 40, "atk": 12, "def": 3,
                                          "exp": 48, "gold": 58, "weakness": "バグ", "on_contact": True,
                                          "taunt": "砂塵の中から大サソリがハサミを鳴らした！"},
                "coast-enemy-kraken": {"name": "潮風クラーケン", "emoji": "🦑", "level": 5, "hp": 52, "atk": 13, "def": 4,
                                       "exp": 62, "gold": 75, "weakness": "パイプライン", "on_contact": True,
                                       "taunt": "波しぶきと共に潮風クラーケンが現れた！"},
                "castle-enemy-daemon": {"name": "幻影ドラゴン", "emoji": "🐲", "level": 6, "hp": 68, "atk": 15, "def": 5,
                                        "exp": 100, "gold": 150, "weakness": "パイプライン", "boss": True, "on_contact": True,
                                        "taunt": "最終試験を守る幻影ドラゴンが咆哮した！"},
            },
            "quests": [
                {"id": "talk-cat", "title": "村の案内を聞こう", "desc": "案内猫ミョン（または村人）に話しかける", "kind": "talk", "count": 1, "reward_exp": 15, "reward_gold": 20},
                {"id": "find-drops", "title": "道ばたの落とし物", "desc": "村に落ちているどうぐを2つひろう", "kind": "drop", "count": 2, "reward_exp": 20, "reward_gold": 25},
                {"id": "open-chests", "title": "宝箱トレジャー", "desc": "宝箱(🎁)を2つ見つけて開ける", "kind": "chest", "count": 2, "reward_exp": 30, "reward_gold": 40},
                {"id": "first-battle", "title": "バグ退治の一歩", "desc": "バグスライムを1体たおす", "kind": "battle", "target": "meadow-enemy-slime", "count": 1, "reward_exp": 25, "reward_gold": 30},
                {"id": "pass-quizzes", "title": "ポートフォリオ博士", "desc": "研究員のクイズに2問正解する", "kind": "quiz", "count": 2, "reward_exp": 30, "reward_gold": 50},
                {"id": "defeat-golem", "title": "村の守護者討伐", "desc": "ボス『スパゲッティゴーレム』をたおす", "kind": "boss", "target": "meadow-enemy-golem", "count": 1, "reward_exp": 80, "reward_gold": 100},
                {"id": "visit-lands", "title": "扉をわたる旅人", "desc": "🛗から3つの土地をおとずれる", "kind": "floor", "count": 3, "reward_exp": 40, "reward_gold": 60},
            ],
            "badges": [
                {"id": "first-talk", "emoji": "💬", "label": "はじめの挨拶", "desc": "村人に初めて話しかけた"},
                {"id": "villager-friends", "emoji": "🤝", "label": "村の人気者", "desc": "村の人々4人以上と話した"},
                {"id": "item-finder", "emoji": "🌿", "label": "アイテム発見", "desc": "落とし物か宝箱を手に入れた"},
                {"id": "treasure-hunter", "emoji": "💎", "label": "トレジャーハンター", "desc": "宝箱を3つ以上開けた"},
                {"id": "first-win", "emoji": "⚔️", "label": "初勝利", "desc": "バトルで初めて勝利した"},
                {"id": "boss-slayer", "emoji": "🏆", "label": "コード浄化者", "desc": "地域のボス魔物を撃破した"},
                {"id": "quiz-ace", "emoji": "🎓", "label": "知識の探究者", "desc": "ポートフォリオクイズに2問以上正解"},
                {"id": "world-walker", "emoji": "🧭", "label": "世界を巡る旅人", "desc": "3つ以上の土地を訪れた"},
                {"id": "level-up", "emoji": "🌟", "label": "成長のあかし", "desc": "レベル2以上に到達した"},
                {"id": "shopper", "emoji": "🛒", "label": "賢い買い物客", "desc": "道具屋でアイテムを購入した"},
            ],
            "quizzes": [
                {"repo": "PySaiyanWeBoo",
                 "prompt": "PySaiyanWeBoo（PSWB）が戦闘や回復ゲージ表現に採用している最大6個のモチーフは何？",
                 "choices": ["Puzzle & Dragons風の属性・回復オーブ", "サイコロ6面の数値表", "トランプのスート絵柄"],
                 "correct": 0,
                 "explanation": "PySaiyanWeBooの counter_effect は 🔥💧🌳💡🔮 や ❤️💚✨ のオーブ最大6個でダメージと回復を可視化します。"},
                {"repo": "Ironmate",
                 "prompt": "Ironmate（テスト・検査系プロジェクト）が大切にする設計原則として正しいものは？",
                 "choices": ["表示用UIと計算結果が常に一致（見かけも中身も同じ）", "常にクラウドへ自動アップロード", "乱数で毎回UIレイアウトを変える"],
                 "correct": 0,
                 "explanation": "画面に見えている数値・文字とバックエンドや検証オラクルの計算がズレない設計を重視しています。"},
                {"repo": "search_seq_including_spaces",
                 "prompt": "バイオインフォマティクスツール search_seq_including_spaces が解決する課題は？",
                 "choices": ["空白や改行を含む塩基配列テキストの検索", "PNG画像の圧縮率向上", "音声ファイルのノイズ除去"],
                 "correct": 0,
                 "explanation": "論文やコピー＆ペースト由来の空白入り配列文字列から、柔軟に部分配列を検索できるよう設計されたツールです。"},
                {"repo": "Aoi",
                 "prompt": "ポートフォリオやツール群における Aoi / myon-bioinformatics の連携方針は？",
                 "choices": ["共通部品を明確にピン留めして各成果物を単体完結させる", "1つの巨大モノリスに全て混ぜる", "依存をバージョン未指定にする"],
                 "correct": 0,
                 "explanation": "PySaiyanWeBoo などの共通基盤は commit SHA でピン留めし、ビルド後は自己完結した単一HTML/静的ページを生成します。"},
                {"repo": "xprobe",
                 "prompt": "xprobe が対象とする開発・解析ワークフローのテーマは？",
                 "choices": ["軽量な探索・診断プローブとデータ確認", "3Dゲームエンジンの物理演算", "決済ゲートウェイの暗号化"],
                 "correct": 0,
                 "explanation": "xprobe は対象の状態や出力を素早く調べ・検証できるプローブ指向のツールとして作られています。"},
                {"repo": "gh_identity / cli_args",
                 "prompt": "gh_identity や cli_args が支えている開発基盤の特徴は？",
                 "choices": ["再利用可能な認証・CLI引数パーサの安全で明快な扱い", "ブラウザ拡張の広告ブロック", "OSカーネルのスケジューラ改造"],
                 "correct": 0,
                 "explanation": "CLIツール間で共通する引数検証やGitHubアイデンティティ判定を小さな責務で安全に共有しています。"},
                {"repo": "mcp-toolcall-lab",
                 "prompt": "mcp-toolcall-lab で検証・実験されている技術領域はどれ？",
                 "choices": ["Model Context Protocol（MCP）のツール呼び出し設計と検証", "WebGLのシェーダー最適化", "ブロックチェーンのマイニング"],
                 "correct": 0,
                 "explanation": "エージェントやLLMからのツール呼び出し契約・挙動を体系的に試すための実験ラボです。"},
                {"repo": "FluidFullSpeedSimulation",
                 "prompt": "ポートフォリオ内の『流れの実験室』（FluidFullSpeedSimulation / DRAgoWing）の可視化テーマは？",
                 "choices": ["連続的な流れ・遅延（🌊動く像）と内訳フロー図（📊静止図）", "株式チャートのローソク足", "星座の年周視差"],
                 "correct": 0,
                 "explanation": "水回り・血流・エネルギーなどの『流れと遅れ』を動的シミュレーションとサンキー風静止図の両面で学べます。"},
            ],
            "shop": [
                {"id": "pot", "spot_id": "meadow-npc-smith", "emoji": "🧪", "label": "村特製ポーション", "cost": 15, "item_type": "heal", "hp": 22, "mp": 0,
                 "desc": "HPを22回復する定番の薬"},
                {"id": "ether", "spot_id": "meadow-npc-smith", "emoji": "🔷", "label": "MPエーテル", "cost": 20, "item_type": "mana", "hp": 0, "mp": 12,
                 "desc": "とくぎ用のMPを12回復する結晶"},
                {"id": "dango", "spot_id": "meadow-npc-smith", "emoji": "🍡", "label": "昼ヶ丘いもだんご", "cost": 28, "item_type": "heal", "hp": 30, "mp": 6,
                 "desc": "甘くてほくほく！HP30・MP6を同時に回復"},
            ],
            "skills": [
                {"id": "bug-buster", "emoji": "⚡", "label": "バグバスター", "mp": 4, "kind": "attack", "mult_pct": 160, "power": 0,
                 "desc": "バグ系の敵に大ダメージ(160%)"},
                {"id": "pipeline-slash", "emoji": "🔬", "label": "パイプライン斬り", "mp": 6, "kind": "attack", "mult_pct": 210, "power": 0,
                 "desc": "パイプライン解析の一閃(210%)"},
                {"id": "pswb-heal", "emoji": "💚", "label": "PSWBヒーリング", "mp": 5, "kind": "heal", "mult_pct": 100, "power": 14,
                 "desc": "回復オーブでHPを大きく回復"},
                {"id": "guard-counter", "emoji": "🛡️", "label": "堅牢カウンター", "mp": 3, "kind": "guard", "mult_pct": 125, "power": 0,
                 "desc": "敵の攻撃を半減しつつ反撃(125%)"},
            ],
        },
    }


EXAMPLES.update({
    "school": {
        "schema": WORLD_SCHEMA, "id": "school", "title": "School (prototype)", "zoom_max": 4,
        "avatars": ["🙂", "😎", "🤓", "🐱", "🐶", "🐰", "🦊", "🐼", "🐸", "🦄", "🐙", "🌸", "⭐", "🍎", "⚽", "🚀", "先生", "A"],
        "tools": {"🗺️": {"label": "見どころ", "label_en": "Highlights", "spots": ["classroom-board", "flowers"]},
                  "🏫": {"label": "学校", "label_en": "School", "body": "教室と校庭があります。フッターの🛗で行き来できます。"}},
        "board": {"title": "INFO", "items": [
            {"text": "朝の会", "at": "08:40"}, {"text": "1時間目", "at": "09:00"}, {"text": "給食", "at": "12:20"},
            {"text": "下校", "at": "15:30"}, {"text": "今日の授業", "gauge": {"from": "09:00", "to": "15:30"}}]},
        "floors": [
            classroom_floor(),
            {"id": "yard", "label": "校庭", "width": 640, "height": 448,
             "spots": [{"id": "bar", "x": 160, "y": 128, "label": "鉄棒", "body": "ここで体を動かします。"},
                       {"id": "flowers", "x": 480, "y": 96, "label": "花だん", "body": "季節の花が咲いています。"}],
             "actors": [{"id": "kid", "emoji": "🧒", "label": "こども", "body": "走り回っています。", "speed": 48},
                        {"id": "dog", "emoji": "🐕", "label": "いぬ", "body": "迷い込んだようです。", "speed": 64},
                        {"id": "bird", "emoji": "🐦", "label": "とり", "body": "屋根にとまっています。", "speed": 32}],
             "player": {"emoji": "🙂", "x": 320, "y": 320, "speed": 96}}],
    },
    "overworld": _overworld_spec(),
    "cities": {
        "schema": WORLD_SCHEMA, "id": "cities", "title": "Parallel cities", "zoom_max": 4, "names": "dots", "mark_scale": [1.5, 1.5],
        "avatars": ["🙂", "🧳", "🚶", "🎒", "🐱", "🐶", "🦊", "🐼", "🚃", "☂️", "🎩", "🗼"],
        "tools": {"🗼": {"label": "パラレル東京", "label_en": "Parallel Tokyo", "floor": "tokyo"},
                  "🎡": {"label": "リバースロンドン", "label_en": "Reverse London", "floor": "london"},
                  "🥖": {"label": "フェイクパリ", "label_en": "Fake Paris", "floor": "paris"},
                  "🚉": {"label": "東京駅", "label_en": "Tokyo Station",
                         "spots": ["tokyo-marunouchi-n", "tokyo-marunouchi-c", "tokyo-marunouchi-s", "tokyo-yaesu-n", "tokyo-yaesu-c", "tokyo-yaesu-s"]}},
        "board": {"title": "PARALLEL", "items": [{"text": "実在の街の、もうひとつの姿"}, {"text": "🛗で3つの街を行き来"}, {"text": "歩いて駅から駅へ"}]},
        "floors": [{"id": "tokyo", "label": "Parallel Tokyo", "place": {"points": _TOKYO_POINTS, "meters": 32, "links": _TOKYO_LINKS, "marks": _CITY_MARKS, "always_named": ["exit"]}},
                   {"id": "london", "label": "Reverse London",
                    "place": {"points": _LONDON_POINTS, "meters": 150, "links": _LONDON_LINKS, "rivers": [_THAMES], "marks": _CITY_MARKS}},
                   {"id": "paris", "label": "Fake Paris",
                    "place": {"points": _PARIS_POINTS, "meters": 150, "links": _PARIS_LINKS, "rivers": [_SEINE],
                              "scatter": {"kind": "fire", "every": 8, "seed": 5}, "marks": _CITY_MARKS}}],
    },
})


def example_data(name: str) -> Any:
    """A deep copy of a named world spec (world, school, overworld, cities)."""
    try:
        return json.loads(json.dumps(EXAMPLES[name]))
    except KeyError:
        raise ValueError(f"unknown example: {name} (one of {', '.join(EXAMPLES)})") from None

# --- 🎞 Demo GIFs: the world's operations from real Chrome (was PySaiyanWeBoo's tools/record_demo.py) ----------------------------------------
# Record the school world's (and the overworld's) operations as demo GIFs (for the README).
#
#     python tools/record_demo.py docs/demo [--only pick keys ...] [--chrome PATH] [--width 480] [--force]
#     python tools/record_demo.py runs --prefix ci- --suffix=-chrome --timestamp --git-commit   # runs/ci-school-pick-chrome-20261108T113412Z-288cbed.gif
#
# Playwright drives a real Chrome through each scene. The ``Camera`` keeps a screenshot with its real timestamp whenever a scene waits,
# so a GIF plays at the speed the page really moved. Encoding follows Ironmate's ``png_zoom_gif.py``: one shared palette (no dither,
# so frames never flicker), delays in 10 ms units (never below 20 ms, which browsers stretch), the animation loops, and an existing
# output is refused unless ``--force``. File names are ``<prefix><world>-<scene><suffix>`` (the suffix right after the base name), then
# the run's details in the order their options were given, left to right: ``--timestamp`` adds when the run started (UTC, ISO 8601 basic:
# ``-20261108T113412Z``), ``--git-commit`` the git commit the pages came from (``-288cbed``, ``-288cbed-dirty`` with uncommitted changes),
# so ``--git-commit --timestamp`` writes ``…-288cbed-20261108T113412Z.gif``. Repeated runs, by hand or by an agent, keep every GIF without
# ``--force`` and each name says when and from which code it was recorded. ``add_gif_arguments``, ``gif_targets`` and ``gif_targets_from``
# are those rules as functions, so the browser tests name their GIFs the same way from
# ``PSWB_GIFS="DIR [--prefix P] [--suffix S] [--timestamp] [--git-commit] [--force]"``. Unlike that zoom (every pixel changes), a walking player changes few pixels, so frames are
# written as deltas (``optimize=True``): about a third of the size, decoding to exactly the same pictures. The zoom step
# (``cam.zoom``) is Ironmate's smooth zoom-in, kept to what the demos need and run through this same encoder, not a second copy of
# that tool; this repository is the canonical home of both. Needs Playwright and Pillow, like the browser tests. Scenes are ordinary functions, so a new
# operation is one ``@scene`` below; ``tests/integration/worlds_browser.py`` records every scene to keep them from rotting.

ROOT = Path(__file__).resolve().parents[1]
FRAME_MS = 80                                   # at most one screenshot per 80 ms while a scene waits
MIN_MS, MAX_MS, TAIL_MS = 20, 2000, 1500        # delay limits, and how long the last frame stays
SPEC = example_data("school")
FLOOR = world_validate(SPEC)["floors"][0]
W, H, T = FLOOR["width"], FLOOR["height"], FLOOR["tile"]
CLASSROOM = f'.ui-floor[data-floor="{FLOOR["id"]}"]'
PICKED = "() => !document.querySelector('.ui-world').hasAttribute('data-pick')"
SETTLED = ("() => { const f = [...document.querySelectorAll('.ui-floor')].find(f => getComputedStyle(f).display !== 'none'), p = f.querySelector('.ui-player'), s = p.style;"
           "return Math.abs(parseFloat(s.getPropertyValue('--px')) - +p.dataset.targetX) < .01 && Math.abs(parseFloat(s.getPropertyValue('--py')) - +p.dataset.targetY) < .01 }")   # the shown floor's player has arrived
PLAYER = (0.48, 0.69)                           # where a character standing at the door is on screen: a zoom target
WORLDS = {"school": SPEC, "overworld": example_data("overworld"), "cities": example_data("cities")}   # the specs a scene can open; a GIF is <world>-<scene>.gif


class Scene(NamedTuple):
    width: int
    height: int
    touch: bool
    crop: str | None
    fn: Callable
    world: str


SCENES: dict[str, Scene] = {}


class Camera:
    """Screenshots with their real times; scenes call hold/until where the GIF should show time passing."""

    def __init__(self, page, crop=None):
        self.page, self.crop, self.shots = page, crop, []

    def png(self):
        """One screenshot; with ``crop`` (a selector) only that element's box, so the GIF is the world and not the empty page around it."""
        if not self.crop:
            return self.page.screenshot(type="png")
        box = self.page.eval_on_selector(self.crop, "e => { const r = e.getBoundingClientRect(); return {x: r.x, y: r.y, width: r.width, height: r.height} }")
        return self.page.screenshot(type="png", clip={k: round(v) for k, v in box.items()})

    def snap(self):
        self.shots.append((time.monotonic(), self.png()))

    def hold(self, ms):
        end = time.monotonic() + ms / 1000
        while time.monotonic() < end:
            began = time.monotonic()
            self.snap()
            self.page.wait_for_timeout(max(0, FRAME_MS - (time.monotonic() - began) * 1000))

    def zoom(self, anchor=(0.5, 0.5), factor=2.5, steps=6, hold_ms=1500):
        """Zoom into what is on screen toward ``anchor`` and stay there: the demos are shown small in the README.
        ``anchor`` is (x, y) from 0 to 1, an anchor name (``"bottom-right"``) or an arrow emoji (``↘️``, ``⬅``, ``🎯`` for the centre), the
        same table pysaiyanweboo uses for directions. Every pixel changes in a zoom, so it costs a few frames of GIF size; it does not zoom back."""
        from PIL import Image
        if isinstance(anchor, str):
            anchor = WORLD_ANCHORS[anchor if anchor in WORLD_ANCHORS else world_arrow_anchor(anchor)]
        source = Image.open(io.BytesIO(self.png())).convert("RGB")
        width, height = source.size
        forward = []
        for i in range(1, steps + 1):
            t = i / steps
            scale = 1 + (factor - 1) * t * t * (3 - 2 * t)          # smoothstep, as in png_zoom_gif
            w, h = max(1, round(width / scale)), max(1, round(height / scale))
            left, top = round((width - w) * anchor[0]), round((height - h) * anchor[1])
            forward.append(source.crop((left, top, left + w, top + h)).resize(source.size, Image.Resampling.LANCZOS))
        path = [(f, 60) for f in forward[:-1]] + [(forward[-1], hold_ms)]
        t = time.monotonic()
        for frame, ms in path:
            png = io.BytesIO()
            frame.save(png, format="PNG")
            self.shots.append((t, png.getvalue()))
            t += ms / 1000
        time.sleep(max(0, t - time.monotonic()))                  # the clock catches up with the frames just added

    def until(self, script, ms=20000):
        end = time.monotonic() + ms / 1000
        while not self.page.evaluate(script):
            if time.monotonic() > end:
                raise TimeoutError(script)
            self.hold(FRAME_MS)
        self.snap()


def encode(shots, *, width=None, tail_ms=TAIL_MS):
    """One GIF from (time, png) shots: shared palette, 10 ms delays, looping forever."""
    from PIL import Image
    frames = [Image.open(io.BytesIO(png)).convert("RGB") for _, png in shots]
    if width and width != frames[0].width:
        frames = [f.resize((width, round(f.height * width / f.width)), Image.Resampling.LANCZOS) for f in frames]
    sample = frames[::max(1, len(frames) // 16)]                # the palette comes from frames across the whole scene
    sheet = Image.new("RGB", (sample[0].width, sample[0].height * len(sample)))
    for i, frame in enumerate(sample):
        sheet.paste(frame, (0, i * frame.height))
    palette = sheet.quantize(colors=255)                        # one slot stays free for Pillow's "unchanged pixel" transparency
    encoded = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
    times = [t for t, _ in shots]
    delays = [min(MAX_MS, max(MIN_MS, round((b - a) * 100) * 10)) for a, b in zip(times, times[1:])] + [tail_ms]
    out = io.BytesIO()
    # optimize=True writes each frame as a delta: unchanged pixels become transparent, so a walking player costs a few KiB, not a screenful
    encoded[0].save(out, format="GIF", save_all=True, append_images=encoded[1:], duration=delays, loop=0, optimize=True)
    return out.getvalue()


def scene(name, width=560, height=720, touch=False, crop=".ui-world", world="school"):
    def add(fn):
        SCENES[name] = Scene(width, height, touch, crop, fn, world)
        return fn
    return add


def choose(page, emoji):
    page.click(f'[data-emoji="{emoji}"]')
    page.wait_for_function(PICKED)
    page.wait_for_timeout(500)                  # the camera finishes its short glide


def at(page, x, y):
    """Page coordinates of the middle of tile (x, y) of the classroom, wherever the camera has put it."""
    left, top, width, height = page.eval_on_selector(CLASSROOM, "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height] }")
    return left + (x * T + T / 2) * width / W, top + (y * T + T / 2) * height / H


def tap(page, cam, x, y):
    page.mouse.click(*at(page, x, y))
    cam.until(SETTLED)
    cam.hold(500)


def key(page, cam, name, repeat_ms=0):
    """A key press; with repeat_ms the key is held and the browser repeats it."""
    end = time.monotonic() + repeat_ms / 1000
    page.keyboard.down(name)
    while time.monotonic() < end:
        cam.hold(FRAME_MS)
        page.keyboard.down(name)                # a repeating keydown
    page.keyboard.up(name)
    cam.hold(300)


def pad(page, cam, step, ms):
    """The on-screen pad: press and hold one arrow button."""
    page.dispatch_event(f'[data-step="{step}"]', "pointerdown")
    cam.hold(ms)
    page.dispatch_event(f'[data-step="{step}"]', "pointerup")
    cam.hold(300)


def more(page, cam, name="more", ms=700):
    """Open a menu: ``settings`` is the header's ⚙️ (pause, change emoji, language), ``favorites`` the header's ⭐, ``spots`` the side's ☰
    list of places and ``more`` the side's ⋯ (walk to X/Y, find myself)."""
    page.click(f'.ui-world-menu[data-menu="{name}"] summary')
    cam.hold(ms)


@scene("pick")
def _pick(page, cam, tmp):
    """The picker comes first; choosing a character puts it in the room."""
    cam.hold(1200)
    page.click('[data-emoji="🦊"]')
    cam.until(PICKED)
    cam.hold(600)
    cam.zoom(PLAYER)


@scene("avatar-text")
def _avatar_text(page, cam, tmp):
    """Change the character later: type any text, an emoji or both."""
    choose(page, "🙂")
    cam.hold(600)
    more(page, cam, "settings")
    page.click("[data-pick-open]")
    cam.hold(900)
    page.click(".ui-world-pick-form input")
    for char in "先生🍎":                          # typed one character at a time so the GIF shows it
        page.keyboard.type(char)
        cam.hold(400)
    page.keyboard.press("Enter")
    cam.until(PICKED)
    cam.hold(600)
    cam.zoom(PLAYER)


@scene("keys")
def _keys(page, cam, tmp):
    """Arrow keys and WASD, one tile per press, held keys repeat; desks stop the walk."""
    choose(page, "🐱")
    cam.hold(600)
    key(page, cam, "ArrowUp", 1400)            # straight into a desk row: the cat stops
    key(page, cam, "ArrowLeft")                 # sideways into the aisle
    key(page, cam, "ArrowUp", 3200)             # along the aisle to the teacher's desk
    for name in "ddd":
        key(page, cam, name)
    for name in "sss":
        key(page, cam, name)
    key(page, cam, "a")
    cam.hold(900)


@scene("tap")
def _tap(page, cam, tmp):
    """Tap a chair and the player walks around the desks to it; a desk itself ends on the nearest free tile."""
    choose(page, "😎")
    cam.hold(600)
    tap(page, cam, 2, 8)
    tap(page, cam, 9, 6)
    tap(page, cam, 5, 11)                       # a desk: the nearest free tile
    cam.hold(600)


@scene("phone", width=360, height=640, touch=True)
def _phone(page, cam, tmp):
    """A phone: tap a character, walk with the on-screen pad, drag the map away and come back with 自分の場所."""
    cam.hold(900)
    page.tap('[data-emoji="🐶"]')
    cam.until(PICKED)
    cam.hold(700)
    pad(page, cam, "0,-1", 1400)
    pad(page, cam, "-1,0", 400)
    pad(page, cam, "0,-1", 2400)
    pad(page, cam, "1,0", 700)
    left, top, width, height = page.eval_on_selector(".ui-world-view", "e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height] }")
    page.mouse.move(left + width / 2, top + height / 2)
    page.mouse.down()
    for i in range(1, 9):                       # drag: the camera stops following
        page.mouse.move(left + width / 2 - 12 * i, top + height / 2 + 24 * i)
        cam.hold(FRAME_MS)
    page.mouse.up()
    cam.hold(700)
    more(page, cam)
    page.click("[data-me]")
    cam.hold(1400)


@scene("menu")
def _menu(page, cam, tmp):
    """The side menu: the ☰ list shows an arrow from you to each place; tap one and the arrow turns to 📍 as you arrive."""
    choose(page, "🐱")
    cam.hold(500)
    pad(page, cam, "0,-1", 900)
    more(page, cam, "spots", 1800)
    page.click('.ui-world-spots a[href="#school-spot-classroom-board"]')
    cam.until(SETTLED)
    cam.hold(800)
    page.click(".ui-sheet-close:visible")
    cam.hold(600)
    more(page, cam, "spots", 1600)


@scene("header")
def _header(page, cam, tmp):
    """The header: ⭐ star two places (one on another floor), see them in the ⭐ list, 🗺️ an emoji tool, 🌐 the language, 🏠 back home."""
    choose(page, "🦊")
    cam.hold(500)
    more(page, cam, "spots", 900)
    page.click('.ui-world-spots[data-floor="classroom"] li:nth-child(1) .ui-world-star')
    cam.hold(700)
    page.keyboard.press("Escape")
    page.select_option(".ui-world-goto", "yard")
    cam.hold(700)
    more(page, cam, "spots", 600)
    page.click('.ui-world-spots[data-floor="yard"] li:nth-child(2) .ui-world-star')
    cam.hold(700)
    page.keyboard.press("Escape")
    page.click('.ui-world-head .ui-world-menu[data-menu="favorites"] summary')
    cam.hold(1500)
    page.click('.ui-world-head .ui-world-menu[data-menu="tool"]:has(summary:text("🗺️")) summary')
    cam.hold(1500)
    more(page, cam, "settings", 800)
    page.select_option(".ui-world-head [data-lang]", "fr")
    cam.hold(900)
    page.select_option(".ui-world-head [data-lang]", "ja")
    cam.hold(600)
    page.keyboard.press("Escape")
    page.click(".ui-world-head .ui-world-home")
    cam.hold(700)
    page.click('.ui-world-ask button[data-t="home"]')
    cam.hold(1000)


@scene("floors")
def _floors(page, cam, tmp):
    """Floors and spots: go to the schoolyard, tap a spot, read it, come back to the classroom."""
    choose(page, "🐸")
    cam.hold(500)
    page.select_option(".ui-world-goto", "yard")
    cam.hold(1200)
    page.click('a.ui-spot[href="#school-spot-flowers"]')
    cam.hold(1600)
    page.click(".ui-sheet-close:visible")
    cam.hold(600)
    page.select_option(".ui-world-goto", "classroom")
    cam.hold(900)
    page.click('a.ui-spot[href="#school-spot-classroom-board"]')
    cam.hold(1600)
    page.click(".ui-sheet-close:visible")
    cam.hold(600)


@scene("lands", world="overworld")
def _lands(page, cam, tmp):
    """Lands side by side: the 🛗 pulldown travels from land to land (swapped objects, nothing else), then walk to the castle town by its ☰ row."""
    choose(page, "🧙")
    cam.hold(900)
    for land in ("forest", "mountain", "desert", "coast", "castle"):
        page.select_option(".ui-world-goto", land)
        cam.hold(1000)
    more(page, cam, "spots", 900)
    page.click('.ui-world-spots[data-floor="castle"] a[href="#overworld-spot-castle-town"]')
    page.click("#overworld-spot-castle-town .ui-world-go")
    cam.until(SETTLED)
    cam.hold(900)


@scene("real", world="overworld")
def _real(page, cam, tmp):
    """Real x virtual: choose a photo (a camera feed is chosen the same way) and it sits behind the floor; walk over it, then 🧹. The photo is drawn here."""
    from PIL import Image, ImageDraw
    room = Image.new("RGB", (640, 480), (214, 226, 232))
    draw = ImageDraw.Draw(room)
    draw.rectangle((0, 336, 640, 480), fill=(176, 132, 96))
    draw.rectangle((88, 64, 296, 232), fill=(150, 200, 240), outline=(96, 96, 104), width=8)
    draw.rectangle((408, 144, 552, 336), fill=(120, 92, 72))
    room.save(tmp / "room.png")
    choose(page, "🧙")
    page.select_option(".ui-world-goto", "real")
    cam.hold(1000)
    more(page, cam, "more", 800)
    page.click("[data-real]")
    cam.hold(1000)
    with page.expect_file_chooser() as chooser:
        page.click('.ui-world-ask button[data-t="photo"]')
    chooser.value.set_files(str(tmp / "room.png"))
    page.wait_for_function("() => document.querySelector('.ui-real')?.complete")
    cam.hold(1000)
    more(page, cam, "spots", 700)
    page.click('.ui-world-spots[data-floor="real"] a[href="#overworld-spot-real-gate"]')
    page.click("#overworld-spot-real-gate .ui-world-go")
    cam.until(SETTLED)
    cam.hold(800)
    more(page, cam, "more", 600)
    page.click("[data-real]")
    cam.hold(700)
    page.click('.ui-world-ask button[data-t="clear"]')
    cam.hold(900)


TERMINAL = ('<meta charset="utf-8"><body style="margin:0;background:#0d1117;color:#d1f7c4;font:20px/1.6 Meiryo,メイリオ,monospace">'
            '<pre style="margin:0;padding:24px;white-space:pre-wrap;word-break:break-all"></pre>')


def spot(page, cam, floor, spot_id, hold_ms=700):
    """Walk to a spot of a city from its ☰ row: its sheet opens at once (read it, close it), then the walk is watched to the end."""
    more(page, cam, "spots", 600)
    page.click(f'.ui-world-spots[data-floor="{floor}"] a[href="#cities-spot-{spot_id}"]')
    cam.hold(hold_ms)
    page.click(".ui-sheet-close:visible")
    cam.until(SETTLED, 40000)
    cam.hold(500)


def sign(page, cam, floor, spot_id, faces):
    """Touch a sign board: the dot, its text, a second face if it has one, the dot again."""
    marker = f'.ui-floor[data-floor="{floor}"] .ui-spot[href="#cities-spot-{spot_id}"]'
    for _ in range(faces):
        page.eval_on_selector(marker, "e => e.click()")
        cam.hold(700)
        page.click(".ui-sheet-close:visible")
        cam.hold(500)


@scene("tokyo", world="cities", width=560, height=720)
def _tokyo(page, cam, tmp):
    """Parallel Tokyo: 🚉 lists the six exits of Tokyo Station; walk from Marunouchi to Yaesu through the concourse, then on to Kanda by ☰; the electronic board lights up when touched."""
    choose(page, "🧳")
    cam.hold(800)
    page.click('.ui-world-head .ui-world-menu[data-menu="tool"] > summary')
    cam.hold(1200)
    page.click('.ui-world-head .ui-world-menu[data-menu="tool"] a[href="#cities-spot-tokyo-yaesu-c"]')
    cam.until(SETTLED, 40000)
    cam.hold(700)
    page.click(".ui-sheet-close:visible")
    cam.hold(300)
    sign(page, cam, "tokyo", "tokyo-concourse", 2)
    spot(page, cam, "tokyo", "tokyo-kanda")
    cam.zoom(PLAYER, factor=1.6, hold_ms=1200)


@scene("london", world="cities", width=560, height=720)
def _london(page, cam, tmp):
    """Reverse London: 🎡 opens it; walk from King's Cross to Waterloo over the Thames bridge, then the wooden nogard board: dot, text, 🐉, dot."""
    choose(page, "🧳")
    cam.hold(600)
    page.click('.ui-world-tools label[for="cities-floor-london"]')
    cam.hold(1000)
    spot(page, cam, "london", "london-waterloo")
    sign(page, cam, "london", "london-nogard", 3)
    cam.zoom(PLAYER, factor=1.8, hold_ms=1200)


@scene("paris", world="cities", width=560, height=720)
def _paris(page, cam, tmp):
    """Fake Paris: 🥖 opens it; a fire burns in each block; walk west from Gare du Nord to Saint-Lazare, terminus to terminus (one walk keeps the GIF under its 3 MiB bar)."""
    choose(page, "🧳")
    cam.hold(600)
    page.click('.ui-world-tools label[for="cities-floor-paris"]')
    cam.hold(1000)
    spot(page, cam, "paris", "paris-saint-lazare")
    cam.zoom(PLAYER, factor=1.6, hold_ms=1200)


@scene("oneliner", crop=None)
def _oneliner(page, cam, tmp):
    """From another repository: one command writes the school page. The output shown is the real output of that run."""
    spec = '{"schema":"web-ui-world/1","avatars":["🙂","先生"],"floors":[{"classroom":{"rows":5,"groups":3}}]}'
    command = f"echo '{spec}' | python scripts/world.py page - > school.html"
    began = time.monotonic()
    done = subprocess.run([sys.executable, str(ROOT / "scripts/world.py"), "page", "-"], input=spec, text=True, capture_output=True,
                          check=True, encoding="utf-8")
    seconds = time.monotonic() - began
    (tmp / "oneliner.html").write_text(done.stdout, encoding="utf-8")
    page.set_content(TERMINAL)
    show = lambda text: page.evaluate("t => { document.querySelector('pre').textContent = t }", text)  # noqa: E731
    shell = "$ "
    show(shell)
    cam.hold(600)
    for end in range(8, len(command) + 8, 8):
        show(shell + command[:end])
        cam.snap()
        page.wait_for_timeout(FRAME_MS)
    shell = f"$ {command}\n$ wc -c school.html\n"
    show(shell)
    cam.hold(500)
    show(f"{shell}{len(done.stdout.encode('utf-8'))} school.html   ({seconds:.2f} s)\n$ open school.html")
    cam.hold(1600)
    page.goto((tmp / "oneliner.html").as_uri())
    cam.hold(900)
    choose(page, "先生")
    cam.hold(1400)


def launch(pw, chrome=None, extra=()):
    """Chromium for the recorder and the browser tests: ``WEB_UI_CHROME`` (or ``chrome``) names an installed Chrome (then run without its sandbox); ``extra`` are more flags."""
    chrome = chrome or os.environ.get("WEB_UI_CHROME")
    args = ["--no-sandbox", *extra] if chrome else list(extra)
    return pw.chromium.launch(executable_path=chrome, args=args) if chrome else pw.chromium.launch(args=args)


# The output-name rules (``--prefix`` / ``--suffix`` / ``--timestamp`` / ``--git-commit`` / ``--force``) are PySaiyanWeBoo's: every recorder shares them.
from pysaiyanweboo import PATTERN_MAX_INPUT, add_gif_arguments, gif_targets  # noqa: E402


def record(out, names=None, *, chrome=None, width=None, force=False, browser=None, prefix="", suffix="", run_details=()):
    """Record the named scenes (all by default) into out/<prefix><world>-<name><suffix>[-<run detail>...].gif (school-keys.gif,
    overworld-lands.gif); returns the written paths. ``prefix``, ``suffix`` and ``run_details`` are ``gif_targets``' name parts.

    ``browser`` is an already running Playwright Chromium (the browser tests share theirs); otherwise one is launched and closed here.
    """
    names = list(names or SCENES)
    unknown = [n for n in names if n not in SCENES]
    if unknown:
        raise ValueError("unknown scene: " + ", ".join(unknown) + " (have " + ", ".join(SCENES) + ")")
    out = Path(out)
    stems = {n: f"{SCENES[n].world}-{n}" for n in names}
    paths = gif_targets(out, stems.values(), prefix=prefix, suffix=suffix, run_details=run_details, force=force, root=ROOT)
    targets = {n: paths[stems[n]] for n in names}
    with tempfile.TemporaryDirectory() as tmp_name, contextlib.ExitStack() as stack:
        tmp = Path(tmp_name)
        for world in {SCENES[n].world for n in names}:
            (tmp / f"{world}.html").write_text(world_document(WORLDS[world]), encoding="utf-8")
        if browser is None:
            from playwright.sync_api import sync_playwright
            browser = launch(stack.enter_context(sync_playwright()), chrome)
            stack.callback(browser.close)
        for name in names:
            sc = SCENES[name]
            context = browser.new_context(viewport={"width": sc.width, "height": sc.height}, has_touch=sc.touch, is_mobile=sc.touch)
            try:
                page = context.new_page()
                page.goto((tmp / f"{sc.world}.html").as_uri())
                cam = Camera(page, sc.crop)
                sc.fn(page, cam, tmp)
                targets[name].write_bytes(encode(cam.shots, width=width))
            finally:
                context.close()
    return list(targets.values())


def main(argv=None):
    """🌍 ``page SPEC|-`` prints a world page · ``example NAME`` prints a spec as JSON · 🎞 ``record OUT`` records the demo GIFs."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    page = commands.add_parser("page", help="🌍 print a single-file page for a web-ui-world/1 JSON spec (`-` reads stdin)")
    page.add_argument("spec", metavar="SPEC", help="a JSON file, or - for stdin")
    page.add_argument("--theme", default="modern", help="PySaiyanWeBoo theme (default %(default)s)")
    example = commands.add_parser("example", help="📄 print a world spec as JSON")
    example.add_argument("name", choices=tuple(EXAMPLES))
    rec = add_gif_arguments(commands.add_parser("record", help="🎞 record the demo GIFs from real Chrome"))
    rec.add_argument("--only", nargs="+", metavar="SCENE", choices=tuple(SCENES), help="scenes to record: " + ", ".join(SCENES))
    rec.add_argument("--chrome", help="Chrome/Chromium executable (default: WEB_UI_CHROME or Playwright's)")
    rec.add_argument("--width", type=int, help="shrink every GIF to this width in pixels")
    args = parser.parse_args(argv)
    if args.command == "example":
        print(json.dumps(example_data(args.name), ensure_ascii=False, indent=2))
        return 0
    if args.command == "page":
        try:
            if args.spec == "-":
                raw = sys.stdin.buffer.read(PATTERN_MAX_INPUT + 1)
                if len(raw) > PATTERN_MAX_INPUT:
                    raise ValueError(f"spec is larger than {PATTERN_MAX_INPUT} bytes")
                text = raw.decode("utf-8")
            else:
                text = Path(args.spec).read_text(encoding="utf-8")
            sys.stdout.write(world_document(json.loads(text), theme=args.theme))
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        return 0
    try:
        for path in record(args.out, args.only, chrome=args.chrome, width=args.width, force=args.force,
                           prefix=args.prefix, suffix=args.suffix, run_details=args.run_details):
            print(f"🎞️ {path}  📦 {path.stat().st_size // 1024} KiB")
    except (ValueError, OSError, ImportError, TimeoutError) as exc:
        parser.exit(1, f"⛔ {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
