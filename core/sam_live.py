"""Live SAM 3.1 integration: Responses API call, wire-grammar parser, mask math.

Without MODEL_API_KEY (or SECONDNURSE_MODE != live) every function returns
With a key, frames
go to SAM 3.1 and returned boxes/masks are parsed per Meta's documented
grammar: <Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;..;data=H,W,enc+payload|>
"""
import base64
import json
import os
import re
import time
import urllib.request

API_URL = "https://api.meta.ai/v1/responses"
MODEL = "sam-3.1"
MAX_IMAGE_BYTES = 6 * 1024 * 1024

BOX_RE = re.compile(
    r"(?P<oid>\d+)<\|box;x1=(?P<x1>\d+);y1=(?P<y1>\d+);x2=(?P<x2>\d+);y2=(?P<y2>\d+)"
    r";w=(?P<fw>\d+);h=(?P<fh>\d+)(?:;c=(?P<conf>[0-9.]+))?\|>"
    r"(?:<\|mask;x=0;y=0(?:;c=[0-9.]+)?;data=(?P<mh>\d+),(?P<mw>\d+),(?P<enc>[~!])(?P<payload>.*?)\|>)?",
    re.DOTALL,
)
FRAME_RE = re.compile(r"<(\d+)f>")


def live_enabled():
    return bool(os.getenv("MODEL_API_KEY")) and os.getenv("SECONDNURSE_MODE") == "live"


def parse_sam_output(text):
    """Parse SAM wire text into frames of records with boxes + mask metadata."""
    frames = []
    parts = FRAME_RE.split(text or "")
    # parts: [prefix, frame_no, body, frame_no, body, ...]
    for i in range(1, len(parts) - 1, 2):
        frame_no = int(parts[i])
        records = []
        for m in BOX_RE.finditer(parts[i + 1]):
            x1, y1, x2, y2 = (int(m.group(k)) for k in ("x1", "y1", "x2", "y2"))
            rec = {
                "id": int(m.group("oid")),
                "box": {"x": x1, "y": y1, "w": max(0, x2 - x1), "h": max(0, y2 - y1)},
                "frame_w": int(m.group("fw")), "frame_h": int(m.group("fh")),
                "confidence": float(m.group("conf")) if m.group("conf") else None,
                "mask": None,
            }
            if m.group("payload") is not None:
                rec["mask"] = {"h": int(m.group("mh")), "w": int(m.group("mw")),
                               "encoding": "one_bit" if m.group("enc") == "!" else "lossless",
                               "payload": m.group("payload")}
            records.append(rec)
        if records:
            frames.append({"frame": frame_no, "records": records})
    return frames


def decode_raster(record):
    """Decode a record's mask payload to a 0/1 bytes raster, or None."""
    mask = (record or {}).get("mask")
    if not mask:
        return None
    try:
        from meta_sam_parser import SegmentationMask, decode_mask_to_raster
        m = SegmentationMask(encoding=mask["encoding"], payload=mask["payload"],
                             width=mask["w"], height=mask["h"])
        return decode_mask_to_raster(m)
    except Exception:
        return None


def mask_overlap_px(a, b):
    """True pixel overlap of two records' masks (falls back to box overlap)."""
    ra, rb = decode_raster(a), decode_raster(b)
    if ra is None or rb is None:
        ax, ay = a["box"]["x"], a["box"]["y"]
        bx, by = b["box"]["x"], b["box"]["y"]
        ox = max(0, min(ax + a["box"]["w"], bx + b["box"]["w"]) - max(ax, bx))
        oy = max(0, min(ay + a["box"]["h"], by + b["box"]["h"]) - max(ay, by))
        return float(ox * oy), "box"

    def points(rec, raster):
        pts = set()
        w, h = rec["mask"]["w"], rec["mask"]["h"]
        ox, oy = rec["box"]["x"], rec["box"]["y"]
        for yy in range(h):
            row = raster[yy * w:(yy + 1) * w]
            for xx, v in enumerate(row):
                if v:
                    pts.add((ox + xx, oy + yy))
        return pts

    pa, pb = points(a, ra), points(b, rb)
    if len(pa) > len(pb):
        pa, pb = pb, pa
    return float(sum(1 for p in pa if p in pb)), "mask"


def _response_text(data):
    out = []
    for item in (data or {}).get("output", []) or []:
        for part in item.get("content", []) or []:
            if part.get("type") == "output_text" and part.get("text"):
                out.append(part["text"])
    return "\n".join(out)


def call_sam(image_url, prompt, timeout=60):
    """One SAM 3.1 Responses call for one concept prompt. Returns parsed frames."""
    key = os.getenv("MODEL_API_KEY", "")
    body = json.dumps({
        "model": MODEL,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_image", "image_url": image_url},
        ]}],
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
    }).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    return parse_sam_output(_response_text(data))


_CANONICAL = [
    ("sterile_tip", ("connector", "tip")),
    ("hand", ("hand", "glove")),
    ("cap", ("cap",)),
    ("field", ("field", "mat", "drape")),
]


def _canonical(prompt):
    low = prompt.lower()
    for name, keys in _CANONICAL:
        if any(k in low for k in keys):
            return name
    return "object"


def segment_live(image_data_url, prompts):
    """Segment one captured frame for several prompts via live SAM 3.1."""
    prompts = [str(p)[:80] for p in (prompts or [])][:5] or ["red connector"]
    started = time.time()
    if not live_enabled():
        raise RuntimeError("Meta API not configured: set MODEL_API_KEY and SECONDNURSE_MODE=live.")
    if not (isinstance(image_data_url, str) and image_data_url.startswith("data:image/")):
        raise ValueError("image must be a data:image URL")
    if len(image_data_url) > MAX_IMAGE_BYTES * 1.4:
        raise ValueError("image too large")
    results = []
    touch = None
    for prompt in prompts:
        frames = call_sam(image_data_url, prompt)
        boxes = []
        for fr in frames:
            for rec in fr["records"]:
                boxes.append({**rec["box"], "label": prompt,
                              "confidence": rec["confidence"],
                              "mask": {"h": rec["mask"]["h"], "w": rec["mask"]["w"]} if rec["mask"] else None,
                              "_record": rec})
        fw = frames[0]["records"][0]["frame_w"] if frames and frames[0]["records"] else 0
        fh = frames[0]["records"][0]["frame_h"] if frames and frames[0]["records"] else 0
        results.append({"prompt": prompt, "canonical": _canonical(prompt),
                        "boxes": boxes, "frame_w": fw, "frame_h": fh})
    # True mask-overlap measurement when both actors were found.
    by_canon = {r["canonical"]: r for r in results}
    if "hand" in by_canon and "sterile_tip" in by_canon:
        hr = by_canon["hand"]["boxes"][0]["_record"] if by_canon["hand"]["boxes"] else None
        tr = by_canon["sterile_tip"]["boxes"][0]["_record"] if by_canon["sterile_tip"]["boxes"] else None
        if hr and tr:
            area, kind = mask_overlap_px(hr, tr)
            touch = {"overlap_px": area, "method": kind}
    for r in results:
        for b in r["boxes"]:
            b.pop("_record", None)
    return {"live": True, "model": MODEL, "results": results,
            "touch": touch, "latency_ms": int((time.time() - started) * 1000)}
