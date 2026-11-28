"""Generate the all-world guide and its graph with the Portfolio pages dependencies."""
import argparse
import json
from pathlib import Path

import world
from markdown import heading
from ontautology import check
from world_shell import SPACES, dialogue_graph


def build():
    nodes, edges = {}, []

    def add(uid, kind, label, **attrs):
        if uid in nodes:
            raise ValueError(f"duplicate guide id: {uid}")
        nodes[uid] = dict(id=uid, type=kind, name=label, **attrs)
        return uid

    def link(source, kind, target):
        edges.append(dict(source=source, kind=kind, target=target))

    root = add("guide", "Guide", "ワールド探索ガイド")
    for route, (scene, label) in SPACES.items():
        link(root, "explains", add("#"+route, "Guide", label, scene=scene))
    for scene in dict.fromkeys(scene for scene, _ in SPACES.values()):
        spec = world.world_validate(world.example_data(scene))
        primary = next(route for route, entry in SPACES.items() if entry[0] == scene)
        for shot in spec["shots"]:
            tid = add("shot/"+scene+"/"+shot["id"], "Task", shot["title"], detail=shot["body"])
            link("#"+primary, "offers", tid)
        rpg = spec.get("rpg", {})
        relics = {relic["spot"]: relic for relic in world.relic_catalogue(spec)}
        spot_routes = {}
        for floor in spec["floors"]:
            fid = floor["id"]
            route = fid if SPACES.get(fid, (None,))[0] == scene else primary
            spot_routes.update((p["id"], route) for p in floor["spots"] + floor["actors"])
            area = add(f"{scene}/{fid}", "State", floor["label"])
            link("#"+route, "contains", area)
            for actor in floor["actors"]:
                aid = add(f'actor/{area}/{actor["id"]}', "Actor", actor["emoji"]+" "+actor["label"], detail=actor["body"])
                link(area, "offers", aid)
            for s in floor["spots"]:
                sid = s["id"]
                spot = add(f"{area}/{sid}", "Task", s["label"], detail=s["body"], x=s["x"], y=s["y"])
                link(area, "offers", spot)
                relic = relics.get(sid)
                if relic:
                    link(spot, "guarded_by", add("guard/"+spot, "Condition", relic["condition"]))
                if relic and relic["kind"] == "dragon":
                    resource = add("item/"+spot, "Resource", relic["label"], usage="竜の秘宝",
                                   collection=True, href="#"+relic["fragment"])
                    link(spot, "provides", resource)
                elif "item" in s:
                    item = rpg.get("loot", {}).get(sid, {})
                    mode = ("消費" if item.get("consumable") else
                            "繰り返し使える" if sid == world.EXPLORATION_SCROLL["id"] else
                            "装備" if item else "取得")
                    attrs = dict(collection=True, href="#"+relic["fragment"]) if relic else {}
                    resource = add("item/"+spot, "Resource", s["item"]["label"],
                                   detail=s["item"]["body"], usage=mode, **attrs)
                    link(spot, "provides", resource)
                    if "requires_enemy" in item and not relic:
                        guard = add("guard/"+spot, "Condition", rpg["enemies"][item["requires_enemy"]]["name"]+"の討伐")
                        link(spot, "guarded_by", guard)
                if sid in rpg.get("enemies", {}):
                    foe = rpg["enemies"][sid]
                    link(spot, "offers", add("enemy/"+spot, "Goal", foe["name"]+"の討伐", hp=foe["hp"]))
            rescue = spec.get("rescue", {})
            if fid == rescue.get("floor"):
                for n in rescue["nodes"]:
                    detail = n.get("desc") or n.get("greeting")
                    tid = add("rescue/"+n["id"], "Task", n["label"], detail=detail, tx=n["tx"], ty=n["ty"])
                    link(area, "offers", tid)
                    if "item_label" in n:
                        mode = "装備" if not n["consumable"] else "消費・火災現場専用" if n["item_type"] == "bomb" else "消費"
                        link(tid, "provides", add("item/"+tid, "Resource", n["item_label"], usage=mode))
                    if n.get("requires_fires"):
                        link(tid, "guarded_by", add("guard/"+tid, "Condition", f'鎮火 {n["requires_fires"]}件以上'))
                fires = [p for p in floor.get("props", []) if p["kind"] == "fire"]
                for i, p in enumerate(fires):
                    f = world.rescue_fire_profile(i, p["x"]//floor["tile"], p["y"]//floor["tile"], rescue["seed"],
                                                 start_cell=rescue["start_cell"], boss_cell=rescue["boss_cell"])
                    link(area, "offers", add(f'rescue/{f["id"]}', "Task", f["name"], tx=f["tx"], ty=f["ty"], heat=f["heat"]))
            if fid == spec.get("detective", {}).get("floor"):
                link(area, "see_also", add("osaka-guide.json", "Guide", "大阪の捜査手帳", markdown="osaka-guide.md"))
        npc_routes = {spot_routes[sid] for sid in rpg.get("npcs", {})}
        rpg_route = next(iter(npc_routes)) if len(npc_routes) == 1 else primary
        rescue = spec.get("rescue", {})
        for rules, route, currency in ((rpg, rpg_route, "G"), (rescue, rescue.get("floor"), "メダル")):
            for q in rules.get("quests", []):
                goal = add("quest/"+q["id"], "Goal", q["title"], detail=q["desc"])
                link("#"+spot_routes.get(q.get("target"), route), "offers", goal)
                link(goal, "completed_when", add("condition/"+q["id"], "Condition", q["kind"],
                                                 minimum=q["count"], target=q.get("target")))
            for shop in rules.get("shop", []):
                buy = add("buy/"+shop["id"], "Task", shop["label"]+"を購入", detail=shop["desc"])
                link("#"+spot_routes.get(shop.get("spot_id"), route), "offers", buy)
                link(buy, "guarded_by", add("price/"+buy, "Condition", f'{shop["cost"]}{currency}以上'))
    for i, fact in enumerate(dialogue_graph(world)["facts"]):
        claim = add(f"fact/{i}", "Claim", fact["edge"], detail=fact["text"])
        link(root, "explains", claim)
        for url in fact["urls"]:
            if url not in nodes:
                add(url, "Evidence", url)
            link(claim, "supported_by", url)
    findings = check(edges, nodes)
    if findings:
        raise ValueError(findings)
    return {"nodes": list(nodes.values()), "edges": edges}


def render(graph):
    ns = {n["id"]: n for n in graph["nodes"]}
    children = {}
    for e in graph["edges"]:
        children.setdefault((e["source"], e["kind"]), []).append(ns[e["target"]])

    def related(n, relation):
        return children.get((n["id"], relation), [])

    lines = [heading(ns["guide"]["name"]).rstrip(), "",
             "ワールド画面の ☰ から各入口へ。🛗 でフロアを切り替えます。", ""]
    for n in related(ns["guide"], "explains"):
        if n["type"] != "Guide":
            continue
        lines.extend([heading(n["name"], 2).rstrip(), ""])
        for area in related(n, "contains"):
            lines.extend([heading(area["name"], 3).rstrip(), ""])
            for task in related(area, "offers"):
                text = task["name"]
                if "tx" in task:
                    text += f'（{task["tx"]}, {task["ty"]} マス）'
                if "heat" in task:
                    text += f'　熱量 {task["heat"]}'
                if "detail" in task:
                    text += "　"+task["detail"]
                for resource in related(task, "provides"):
                    name = resource["name"]
                    if resource.get("collection"):
                        name = f'[{name}](https://myon-bioinformatics.github.io/tools/{resource["href"]})'
                    text += f'　{name}（{resource["usage"]}）'
                for guard in related(task, "guarded_by"):
                    text += "　前提 "+guard["name"]
                lines.append("- "+text)
            for more in related(area, "see_also"):
                lines.append(f'- [{more["name"]}]({more["markdown"]})')
            lines.append("")
        for task in related(n, "offers"):
            guards = related(task, "guarded_by")
            condition = related(task, "completed_when")
            note = "　必要 "+guards[0]["name"] if guards else ""
            if condition:
                note += f'　達成数 {condition[0]["minimum"]}'
            lines.append(f'- **{task["name"]}**　{task["detail"]}'+note)
        lines.append("")
    lines.extend([heading("世界をまたぐ道具と手掛かり", 2).rstrip(), ""])
    for n in related(ns["guide"], "explains"):
        if n["type"] == "Claim":
            lines.append("- "+n["detail"])
    return "\n".join(lines)+"\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    out = parser.parse_args().out
    out.mkdir(exist_ok=True, parents=True)
    graph = build()
    (out/"world-guide.json").write_text(json.dumps(graph, ensure_ascii=False, indent=1)+"\n", encoding="utf-8")
    (out/"world-guide.md").write_text(render(graph), encoding="utf-8")
