"""Robot task planning + self-verification (pure, testable)."""

def _inside(px, py, rect):
    return rect["x"] <= px <= rect["x"] + rect["w"] and rect["y"] <= py <= rect["y"] + rect["h"]

def plan_execution(objects, bins, program):
    """objects: [{id,color,x,y}]; returns ordered pick/place actions."""
    rules = (program or {}).get("rules", {})
    by_id = {b["id"]: b for b in bins}
    actions = []
    for obj in objects or []:
        bin_id = rules.get(obj["color"])
        if not bin_id or bin_id not in by_id:
            continue
        b = by_id[bin_id]
        actions.append({"action": "pick", "object": obj["id"], "color": obj["color"],
                        "from": {"x": obj["x"], "y": obj["y"]},
                        "then": "place", "bin": bin_id,
                        "to": {"x": b["x"] + b["w"] / 2, "y": b["y"] + b["h"] / 2}})
    return {"actions": actions, "count": len(actions)}

def verify_execution(objects, bins):
    """objects carry final x/y. Correct = inside the bin of its own colour."""
    by_color = {b["color"]: b for b in bins}
    results = []
    for obj in objects or []:
        b = by_color.get(obj["color"])
        ok = bool(b) and _inside(obj["x"], obj["y"], b)
        results.append({"object": obj["id"], "color": obj["color"], "correct": ok,
                        "bin": b["id"] if b else None})
    correct = sum(1 for r in results if r["correct"])
    return {"results": results, "correct": correct, "total": len(results),
            "score": round(100 * correct / max(1, len(results)))}
