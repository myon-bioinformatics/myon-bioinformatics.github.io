"""Generate the Osaka field guide from the same validated spec as the city map.

python scripts/osaka_guide.py OUTPUT_DIR [--observations counts.json]
Observations are current nonnegative integer counts keyed by metric (talk:npc-heita,
clue, chest, medals, stamina, ...). Omitted observations stay unknown.
"""
import argparse
import json
from pathlib import Path

from markdown import heading
from ontautology import check
from world import detective_clue_profile, detective_garden, detective_garden_step, example_data, world_validate


METRICS = {"clue": "解明した現場", "boss_clue": "解明した黒幕", "chest": "開けた宝箱",
           "drop": "拾った落とし物", "talk": "話した人数", "quiz": "矛盾を特定した証言",
           "refill": "休憩回数", "garden": "緑化マス", "medals": "所持メダル", "stamina": "現在のスタミナ"}


def build(spec, observations=None):
    city = world_validate(spec)
    d = city["detective"]
    floor = next(f for f in city["floors"] if f["id"] == d["floor"])
    props = [p for p in floor["props"] if p["kind"] == "shadow"]
    profiles = [detective_clue_profile(i, p["x"] // floor["tile"], p["y"] // floor["tile"],
                d["seed"], boss_cell=d["boss_cell"], start_cell=d["start_cell"]) for i, p in enumerate(props)]
    counts = {} if observations is None else observations
    if not isinstance(counts, dict) or any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError("observations must map metric names to nonnegative integer counts")
    nodes, edges, diagnostics = {}, [], []

    def node(uid, kind, name, **attrs):
        nodes[uid] = dict(id=uid, type=kind, name=name, **attrs)
        return uid

    def edge(source, kind, target):
        edges.append(dict(source=source, kind=kind, target=target))

    guide = node("guide", "Guide", "せやかて大阪 捜査手帳")
    actor = node("actor", "Actor", "浪速の調査探偵", initial=d["hero"])
    goal = node("all", "Goal", f"大阪の全{len(props)}現場を解明する")
    edge(guide, "explains", goal)
    steps, value = [], 0
    for profile in profiles:
        step = detective_garden_step(value, profile["garden_step"])
        steps.append(step)
        value += step
    limits = {"clue": len(props), "boss_clue": sum(p["boss"] for p in profiles),
              "quiz": len({q["prompt"] for q in d["quizzes"]}) if any(n.get("quiz") for n in d["nodes"]) else 0,
              "garden": len(detective_garden(d["seed"], steps)["cells"])}
    for kind in ("drop", "chest", "npc"):
        limits["talk" if kind == "npc" else kind] = sum(n["kind"] == kind for n in d["nodes"])
    if not any(n["kind"] == "stand" or n.get("refill") for n in d["nodes"]):
        limits["refill"] = 0
    names = dict(METRICS)
    for n in d["nodes"]:
        if n["kind"] == "npc":
            metric = "talk:" + n["id"]
            limits[metric], names[metric] = 1, n["label"] + "との会話"

    def condition(metric, minimum):
        uid = f"condition/{metric}/{minimum}"
        if uid in nodes:
            return uid
        label = f"{names.get(metric, metric)} ≥ {minimum}"
        known = metric in names and minimum is not None
        observed = counts.get(metric) if known else None
        if observed is not None and metric in limits and observed > limits[metric]:
            raise ValueError(f"impossible observation {metric}={observed}, maximum {limits[metric]}")
        verdict = None if observed is None else observed >= minimum
        node(uid, "Condition", label, metric=metric, minimum=minimum)
        state = node("state/"+metric, "State", names.get(metric, metric))
        claim = node("claim/"+uid, "Claim", label, value=verdict)
        edge(claim, "about", state)
        edge(uid, "evaluated_by", claim)
        if observed is not None:
            evidence = node("observed/"+metric, "Evidence", names[metric], value=observed)
            edge(claim, "supported_by", evidence)
        if not known:
            diagnostics.append(f"不明な条件 {label}")
        elif metric in limits and minimum > limits[metric]:
            diagnostics.append(f"到達不能 {label}（上限 {limits[metric]}）")
        return uid

    def task(uid, label, section, detail):
        tid = node("task/"+uid, "Task", label, section=section, detail=detail)
        edge(actor, "performs", tid)
        return tid

    edge(goal, "completed_when", condition("clue", len(props)))
    for q in [*d["quests"], *d["badges"]]:
        metric = q.get("kind", "未定義")
        if "target" in q:
            metric += ":" + q["target"]
        gid = node(q["id"], "Goal", q.get("title") or q["label"])
        edge(guide, "explains", gid)
        table = "quests" if "title" in q else "badges"
        source = node("spec/"+gid, "Evidence", f"detective.{table}[id={gid}]")
        edge(gid, "defined_by", source)
        tid = task(q["id"], nodes[gid]["name"], "事件・バッジ", q["desc"])
        edge(gid, "achieved_by", tid)
        edge(gid, "completed_when", condition(metric, q.get("count")))
        edge(tid, "produces", "state/"+metric)

    walk = task("walk", "足元の痕跡を調べる", "現場での手順", "Lv.1の影のマスへ歩くと自動で解明する。")
    edge(walk, "guarded_by", condition("stamina", d["walk_cost"]))
    for p in profiles:
        tid = task(p["id"], p["name"], "現場一覧",
                   f'({p["tx"]}, {p["ty"]}) · Lv.{p["tier"]} · トリック {p["trick"]}')
        edge(goal, "achieved_by", tid)
        edge(tid, "produces", "state/clue")
        if p["tier"] == 1:
            edge(tid, "can_use", walk)
        if p["boss"]:
            edge(tid, "produces", "state/boss_clue")

    for i, case in enumerate(d["quizzes"]):
        tid = task(f"testimony-{i}", "証言の照合", "現場での手順", case["prompt"])
        if "witness" in case:
            edge(tid, "guarded_by", condition("talk:" + case["witness"], 1))
        edge(tid, "produces", node("state/quiz", "State", names["quiz"]))

    for t in d["tactics"]:
        tid = task(t["id"], t["label"], "現場での手順", t["desc"])
        edge(tid, "guarded_by", condition("stamina", t["stamina"]))
    for n in [*d["nodes"], *d["shop"]]:
        kind = n.get("kind", "shop")
        location = (f'({n["tx"]}, {n["ty"]})' if kind != "shop" else
                    "・".join(s["label"] for s in d["nodes"] if s.get("shop")))
        if kind == "shop" and not location:
            diagnostics.append(f'到達不能 {n["id"]}（販売員なし）')
        if "usage" not in n:
            task(n["id"], n["label"], "聞き込みと休憩", location + " " + n["greeting"])
            continue
        label = n.get("item_label", n["label"])
        mode = ("常備・取得時から有効" if n["usage"] == "equipment" else
                "消費・現場専用" if n["logic"] else "消費・移動中／現場")
        resource = node("resource/"+n["id"], "Resource", label, usage=n["usage"])
        tid = task(n["id"], label, "持ち物と入手場所", f'{location} · {mode} · {n["desc"]} {n["effect"]}')
        edge(tid, "provides", resource)
        if kind == "shop":
            edge(tid, "guarded_by", condition("medals", n["cost"]))
        if n.get("requires_clues"):
            edge(tid, "guarded_by", condition("clue", n["requires_clues"]))
        use = node("use/"+n["id"], "Task", label+"を使う")
        edge(use, "requires", resource)
        edge(actor, "performs", use)
    for finding in check(edges, nodes):
        diagnostics.append(str(finding))
    return dict(nodes=list(nodes.values()), edges=edges, diagnostics=diagnostics)


def markdown(graph):
    nodes = {n["id"]: n for n in graph["nodes"]}
    links = {}
    for e in graph["edges"]:
        links.setdefault((e["source"], e["kind"]), []).append(e["target"])

    def status(cid):
        value = nodes["claim/"+cid]["value"]
        return nodes[cid]["name"] + {None: "（未確認）", True: "（達成）", False: "（未達）"}[value]

    lines = [heading(nodes["guide"]["name"]).rstrip(), "", "目的は"+nodes["all"]["name"]+"こと。",
             "コンパスで未解明の現場へ向かい、難しい影は現場検証で解明する。疲れたら茶房で休憩できる。",
             "装備と試験紙は任意。各現場の座標はマップのタイル単位。", "",
             "全件の完了条件　"+status(links["all", "completed_when"][0])]
    for section in ("聞き込みと休憩", "現場での手順", "持ち物と入手場所", "事件・バッジ", "現場一覧"):
        lines.extend(["", heading(section, 2).rstrip(), ""])
        for uid, n in nodes.items():
            if n.get("section") != section:
                continue
            parts = [n["detail"]]
            for cid in links.get((uid, "guarded_by"), []):
                value = nodes["claim/"+cid]["value"]
                prefix = {None: "確認してください　", False: "前提未達　", True: "実行可能　"}[value]
                parts.append(prefix + status(cid))
            for cid in links.get((uid.removeprefix("task/"), "completed_when"), []):
                parts.append("完了条件　"+status(cid))
            lines.append(f'- **{n["name"]}**　'+"　".join(parts))
    if graph["diagnostics"]:
        lines.extend(["", heading("診断", 2).rstrip(), "", *("- "+m for m in graph["diagnostics"])])
    return "\n".join(lines)+"\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--observations", type=Path)
    args = parser.parse_args()
    data = json.loads(args.observations.read_text(encoding="utf-8")) if args.observations else {}
    graph = build(example_data("cities"), data)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"osaka-guide.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    (args.output/"osaka-guide.md").write_text(markdown(graph), encoding="utf-8")
    raise SystemExit(bool(graph["diagnostics"]))
