"""Learn a pick-and-place program from one human demonstration.

Input tracks come from object tracking (SAM masks -> centroids). The learner
infers the general rule behind the demonstration (e.g. sort by colour into the
matching bin), not just the literal moves, so the robot can repeat the task
on a rearranged bench.
"""

def _inside(px, py, rect):
    return rect["x"] <= px <= rect["x"] + rect["w"] and rect["y"] <= py <= rect["y"] + rect["h"]

def _dest_bin(end, bins):
    for b in bins:
        if _inside(end["x"], end["y"], b):
            return b
    return None

def learn_program(tracks, bins):
    """tracks: [{object_id, color, start:{x,y}, end:{x,y}}]; bins: [{id,color,x,y,w,h}]"""
    rules, steps, unexplained = {}, [], []
    for t in tracks or []:
        dest = _dest_bin(t.get("end", {}), bins or [])
        if dest is None:
            unexplained.append(t.get("object_id"))
            continue
        rules[t["color"]] = dest["id"]
        steps.append({"action": "pick", "object": t["object_id"], "color": t["color"],
                      "then": "place", "bin": dest["id"], "bin_color": dest["color"]})
    consistent = len(set(rules.values())) == len(rules)
    task = "sort_by_color" if rules and all(
        any(b["id"] == bid and b["color"] == color for b in bins) for color, bid in rules.items()
    ) else "pick_and_place"
    return {
        "task": task,
        "generalizes": task == "sort_by_color",
        "rules": rules,
        "steps": steps,
        "learned_from": len(steps),
        "unexplained": unexplained,
        "confidence": round(len(steps) / max(1, len(tracks or [])), 2),
        "summary": ("Sort every object into the bin of its own colour."
                    if task == "sort_by_color" else
                    "Pick each demonstrated object and place it in its demonstrated bin."),
    }
