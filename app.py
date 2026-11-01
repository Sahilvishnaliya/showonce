"""ShowOnce web app. Thin Flask layer over core/."""
import os
import time
from collections import defaultdict, deque

from flask import Flask, jsonify, request, send_from_directory

from core.learn import learn_program
from core.passport import create_passport, verify_passport
from core.robot import plan_execution, verify_execution
from core.sam_live import live_enabled, segment_live

ROOT = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

_hits = defaultdict(deque)


def _rate_limited(key, limit=30, window=60):
    now = time.time()
    q = _hits[key]
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(now)
    return False


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=()"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
        "style-src 'self' https://fonts.googleapis.com; style-src-attr 'unsafe-inline'; "
        "font-src https://fonts.gstatic.com; script-src 'self'; connect-src 'self'"
    )
    return resp


@app.get("/")
def index():
    return send_from_directory(ROOT, "index.html")


@app.get("/styles.css")
def styles():
    return send_from_directory(ROOT, "styles.css", mimetype="text/css")


@app.get("/app.js")
def script():
    return send_from_directory(ROOT, "app.js", mimetype="text/javascript")


@app.get("/docs/")
def docs_index():
    return send_from_directory(os.path.join(ROOT, "docs"), "index.html")


@app.get("/docs/<path:name>")
def docs_page(name):
    if ".." in name or name.startswith("/"):
        return jsonify({"error": "Not found."}), 404
    return send_from_directory(os.path.join(ROOT, "docs"), name)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "sam_live": live_enabled(),
                    "models": {"reasoning": "muse-wonder-1.0", "segmentation": "sam-3.1"},
                    "mode": "live" if live_enabled() else "core (SAM camera needs MODEL_API_KEY)"})


def _body():
    if not request.is_json:
        return None
    b = request.get_json(silent=True)
    return b if isinstance(b, dict) else None


@app.post("/api/learn")
def learn_route():
    body = _body()
    if body is None or not isinstance(body.get("tracks"), list) or not isinstance(body.get("bins"), list):
        return jsonify({"error": "Body must be {tracks: [...], bins: [...]}."}), 400
    return jsonify(learn_program(body["tracks"], body["bins"]))


@app.post("/api/plan")
def plan_route():
    body = _body()
    if body is None or not isinstance(body.get("objects"), list) or not isinstance(body.get("bins"), list):
        return jsonify({"error": "Body must be {objects: [...], bins: [...], program: {...}}."}), 400
    return jsonify(plan_execution(body["objects"], body["bins"], body.get("program") or {}))


@app.post("/api/verify")
def verify_route():
    body = _body()
    if body is None or not isinstance(body.get("objects"), list) or not isinstance(body.get("bins"), list):
        return jsonify({"error": "Body must be {objects: [...], bins: [...]}."}), 400
    return jsonify(verify_execution(body["objects"], body["bins"]))


@app.post("/api/passport")
def passport_route():
    body = _body()
    if body is None or not isinstance(body.get("program"), dict):
        return jsonify({"error": "Body must be {program: {...}, verification: {...}}."}), 400
    return jsonify(create_passport(body["program"], body.get("verification") or {},
                                   str(body.get("bench", "showonce-bench"))[:60]))


@app.post("/api/passport/verify")
def passport_verify_route():
    body = _body()
    if body is None or not isinstance(body.get("passport"), dict):
        return jsonify({"error": "Body must be {passport: {...}}."}), 400
    result = verify_passport(body["passport"])
    return jsonify(result), (200 if result["valid"] else 422)


@app.post("/api/segment-live")
def segment_live_route():
    if _rate_limited((request.remote_addr or "local") + ":live", limit=20, window=60):
        return jsonify({"error": "Rate limit reached. Try again shortly."}), 429
    body = _body()
    if body is None:
        return jsonify({"error": "JSON body required."}), 400
    prompts = body.get("prompts", ["red cube"])
    if not isinstance(prompts, list) or not all(isinstance(p, str) for p in prompts):
        return jsonify({"error": "prompts must be a list of strings."}), 400
    try:
        return jsonify(segment_live(body.get("image", ""), prompts))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 503
    except Exception:
        return jsonify({"error": "Live segmentation failed. Check MODEL_API_KEY / SECONDNURSE_MODE."}), 502


@app.route("/api/index.py", methods=["GET", "POST"])
def vercel_dispatch():
    target = (request.args.get("sn_path") or "").strip("/")
    if target == "health" and request.method == "GET":
        return health()
    if target == "learn" and request.method == "POST":
        return learn_route()
    if target == "plan" and request.method == "POST":
        return plan_route()
    if target == "verify" and request.method == "POST":
        return verify_route()
    if target == "passport" and request.method == "POST":
        return passport_route()
    if target == "passport/verify" and request.method == "POST":
        return passport_verify_route()
    if target == "segment-live" and request.method == "POST":
        return segment_live_route()
    return jsonify({"error": "Not found."}), 404


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Request too large."}), 413


@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Not found."}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
