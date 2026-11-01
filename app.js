"use strict";
/* ShowOnce front end. All dynamic text via textContent. */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const SVGNS = "http://www.w3.org/2000/svg";

fetch("/api/health").then(r => r.json()).then(h => {
  const pill = $("#mode-pill");
  pill.textContent = h.sam_live ? "SAM 3.1 · live" : "Core ready · SAM needs API key";
  pill.classList.toggle("live", !!h.sam_live);
}).catch(() => { $("#mode-pill").textContent = "Offline"; });

/* ================= BENCH ================= */
const COLORS = { red: "#D64541", blue: "#2F6FED", yellow: "#E3A008" };
const SOFT = { red: "#FBEAE8", blue: "#E8EFFD", yellow: "#FBF0D3" };
const BINS = [
  { id: "bin-red", color: "red", x: 40, y: 28, w: 150, h: 86 },
  { id: "bin-blue", color: "blue", x: 245, y: 28, w: 150, h: 86 },
  { id: "bin-yellow", color: "yellow", x: 450, y: 28, w: 150, h: 86 },
];
const HOME = { red: { x: 110, y: 322 }, blue: { x: 295, y: 322 }, yellow: { x: 480, y: 322 } };
let cubes = Object.keys(COLORS).map(c => ({ id: `cube-${c}`, color: c, x: HOME[c].x, y: HOME[c].y, el: null }));
let program = null, tracks = [], busy = false;

function drawBins() {
  const g = $("#bins");
  BINS.forEach(b => {
    const r = document.createElementNS(SVGNS, "rect");
    r.setAttribute("x", b.x); r.setAttribute("y", b.y);
    r.setAttribute("width", b.w); r.setAttribute("height", b.h);
    r.setAttribute("rx", 14); r.setAttribute("fill", SOFT[b.color]);
    r.setAttribute("stroke", COLORS[b.color]); r.setAttribute("stroke-width", "2");
    r.setAttribute("stroke-dasharray", "7 6");
    const t = document.createElementNS(SVGNS, "text");
    t.setAttribute("x", b.x + b.w / 2); t.setAttribute("y", b.y + b.h + 20);
    t.setAttribute("text-anchor", "middle");
    t.setAttribute("font-family", "IBM Plex Mono, monospace"); t.setAttribute("font-size", "11");
    t.setAttribute("fill", "#667085"); t.textContent = `${b.color.toUpperCase()} BIN`;
    g.append(r, t);
  });
}
function drawCubes() {
  const g = $("#cubes");
  cubes.forEach(c => {
    const r = document.createElementNS(SVGNS, "rect");
    r.setAttribute("width", 28); r.setAttribute("height", 28); r.setAttribute("rx", 7);
    r.setAttribute("fill", COLORS[c.color]); r.setAttribute("stroke", "rgba(14,30,50,.35)");
    c.el = r; placeCube(c, c.x, c.y);
    g.append(r);
  });
}
function placeCube(c, x, y) {
  c.x = x; c.y = y;
  c.el.setAttribute("x", x); c.el.setAttribute("y", y);
}
function cubeAt(c) { return { x: c.x + 14, y: c.y + 14 }; }

function logEvent(kind, text) {
  const log = $("#log");
  const empty = $(".log-empty", log); if (empty) empty.remove();
  const li = document.createElement("li");
  if (kind === "ok") li.className = "ok";
  const t = document.createElement("span"); t.className = "t";
  t.textContent = `${kind.toUpperCase()} · `;
  li.append(t, document.createTextNode(text));
  log.prepend(li);
}
function setState(text) { $("#console-state").textContent = text; }
function flowState(activeId, doneIds) {
  ["btn-demo", "btn-learn", "btn-shuffle", "btn-robot"].forEach(id => {
    const b = $("#" + id);
    b.classList.toggle("is-active", id === activeId);
    b.classList.toggle("is-done", doneIds.includes(id));
  });
}

function animate(dur, onFrame) {
  return new Promise(resolve => {
    const t0 = performance.now();
    (function tick(t) {
      const p = Math.min(1, (t - t0) / dur), e = p < .5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
      onFrame(e);
      if (p < 1) requestAnimationFrame(tick); else resolve();
    })(t0);
  });
}
const lerp = (a, b, p) => a + (b - a) * p;

async function moveCubeWithHand(cube, toX, toY, record) {
  const hand = $("#hand");
  const from = { x: cube.x, y: cube.y };
  const startC = cubeAt(cube);
  hand.setAttribute("opacity", "1");
  hand.setAttribute("transform", `translate(${startC.x},${startC.y - 26})`);
  await animate(950, p => {
    const x = lerp(from.x, toX, p), y = lerp(from.y, toY, p);
    placeCube(cube, x, y);
    hand.setAttribute("transform", `translate(${x + 14},${y - 12})`);
  });
  if (record) tracks.push({ object_id: cube.id, color: cube.color, start: startC, end: cubeAt(cube) });
  hand.setAttribute("opacity", "0");
}

/* ---- arm kinematics (2-link IK) ---- */
const BASE = { x: 320, y: 402 }, L1 = 118, L2 = 108;
function setArm(tx, ty) {
  let dx = tx - BASE.x, dy = ty - BASE.y;
  let d = Math.min(L1 + L2 - 2, Math.hypot(dx, dy));
  const a = Math.acos(Math.max(-1, Math.min(1, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))));
  const ang = Math.atan2(dy, dx) + a;
  const ex = BASE.x + L1 * Math.cos(ang), ey = BASE.y + L1 * Math.sin(ang);
  const up = $("#arm-upper"), fo = $("#arm-fore");
  up.setAttribute("x2", ex); up.setAttribute("y2", ey);
  fo.setAttribute("x1", ex); fo.setAttribute("y1", ey);
  fo.setAttribute("x2", tx); fo.setAttribute("y2", ty);
  $("#arm-elbow").setAttribute("cx", ex); $("#arm-elbow").setAttribute("cy", ey);
  $("#gripper").setAttribute("transform", `translate(${tx},${ty})`);
  return { x: tx, y: ty };
}
let grip = { x: 320, y: 215 };
async function moveArm(toX, toY, carrying) {
  const from = { ...grip };
  await animate(620, p => {
    grip = setArm(lerp(from.x, toX, p), lerp(from.y, toY, p));
    if (carrying) placeCube(carrying, grip.x - 14, grip.y + 4);
  });
}

/* ================= FLOW ================= */
$("#btn-demo").addEventListener("click", async () => {
  if (busy) return; busy = true;
  flowState("btn-demo", []);
  $("#btn-learn").disabled = true; $("#btn-shuffle").disabled = true; $("#btn-robot").disabled = true;
  tracks = [];
  cubes.forEach(c => placeCube(c, HOME[c.color].x, HOME[c.color].y));
  setState("Demonstration in progress — watch the hand");
  logEvent("demo", "Human demonstration started. SAM is tracking every object.");
  for (const cube of cubes) {
    const bin = BINS.find(b => b.color === cube.color);
    await moveCubeWithHand(cube, bin.x + bin.w / 2 - 14, bin.y + bin.h / 2 - 14, true);
    logEvent("track", `${cube.color} cube tracked: bench → ${cube.color} bin.`);
  }
  setState("Demonstration complete — now teach the robot");
  $("#btn-learn").disabled = false;
  flowState(null, ["btn-demo"]);
  busy = false;
});

$("#btn-learn").addEventListener("click", async () => {
  if (busy || !tracks.length) return; busy = true;
  flowState("btn-learn", ["btn-demo"]);
  setState("Compiling demonstration into a robot program…");
  try {
    const r = await fetch("/api/learn", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks, bins: BINS }) });
    program = await r.json();
    if (!r.ok) throw new Error(program.error || "Learning failed.");
    renderProgram(program);
    logEvent("learn", `Program learned: ${program.summary} (confidence ${program.confidence}).`);
    setState("Program learned — shuffle the bench");
    $("#btn-shuffle").disabled = false;
    flowState(null, ["btn-demo", "btn-learn"]);
  } catch (e) { setState(e.message); }
  busy = false;
});

function renderProgram(p) {
  const wrap = $("#program"); wrap.textContent = "";
  const head = document.createElement("p");
  head.innerHTML = "";
  const strong = document.createElement("strong"); strong.textContent = p.summary;
  head.append(strong); wrap.append(head);
  for (const [color, bin] of Object.entries(p.rules)) {
    const line = document.createElement("div"); line.className = "rule-line";
    const sw = document.createElement("span"); sw.className = `cube ${color}`;
    const txt = document.createElement("span");
    txt.textContent = `${color} cube → ${bin} · pick & place`;
    line.append(sw, txt); wrap.append(line);
  }
  const foot = document.createElement("p"); foot.className = "mono muted";
  foot.textContent = `task: ${p.task} · generalizes: ${p.generalizes} · learned from ${p.learned_from} demonstration(s)`;
  wrap.append(foot);
}

$("#btn-shuffle").addEventListener("click", () => {
  if (busy) return;
  const slots = [{ x: 70, y: 322 }, { x: 200, y: 348 }, { x: 330, y: 318 }, { x: 460, y: 348 }, { x: 540, y: 315 }];
  const shuffled = [...slots].sort(() => Math.random() - .5);
  cubes.forEach((c, i) => placeCube(c, shuffled[i].x, shuffled[i].y));
  $("#verify-box").hidden = true;
  setState("Bench shuffled — the robot has never seen this arrangement");
  logEvent("shuffle", "Bench rearranged. Positions are new; the rule is the same.");
  $("#btn-robot").disabled = false;
  flowState("btn-shuffle", ["btn-demo", "btn-learn"]);
});

$("#btn-robot").addEventListener("click", async () => {
  if (busy || !program) return; busy = true;
  flowState("btn-robot", ["btn-demo", "btn-learn", "btn-shuffle"]);
  setState("Robot is repeating the task…");
  try {
    const r = await fetch("/api/plan", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objects: cubes.map(c => ({ id: c.id, color: c.color, ...cubeAt(c) })), bins: BINS, program }) });
    const plan = await r.json();
    if (!r.ok) throw new Error(plan.error || "Planning failed.");
    for (const a of plan.actions) {
      const cube = cubes.find(c => c.id === a.object);
      const c0 = cubeAt(cube);
      await moveArm(c0.x, c0.y - 18, null);
      await moveArm(c0.x, c0.y + 2, null);
      await moveArm(a.to.x, a.to.y - 30, cube);
      await moveArm(a.to.x, a.to.y, cube);
      placeCube(cube, a.to.x - 14, a.to.y - 14);
      logEvent("robot", `Placed ${cube.color} cube in ${a.bin}.`);
    }
    await moveArm(320, 215, null);
    const v = await fetch("/api/verify", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ objects: cubes.map(c => ({ id: c.id, color: c.color, ...cubeAt(c) })), bins: BINS }) })
      .then(x => x.json());
    $("#verify-box").hidden = false;
    $("#verify-score").textContent = `${v.score}%`;
    $("#verify-detail").textContent = `${v.correct}/${v.total} objects in the right bin`;
    logEvent(v.score === 100 ? "ok" : "verify", `Self-check: ${v.correct}/${v.total} correct — score ${v.score}%.`);
    setState(v.score === 100 ? "Task complete — and the robot proved it" : "Run finished — self-check found problems");
    flowState(null, ["btn-demo", "btn-learn", "btn-shuffle", "btn-robot"]);
    $("#btn-shuffle").disabled = false;
  } catch (e) { setState(e.message); }
  busy = false;
});

$$("[data-goto-demo]").forEach(b => b.addEventListener("click", () => {
  $("#console").scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => $("#btn-demo").click(), 450);
}));
$("#cta-demo").addEventListener("click", () => {
  $("#console").scrollIntoView({ behavior: "smooth", block: "center" });
  setTimeout(() => $("#btn-demo").click(), 450);
});

/* ================= CAMERA (SAM live) ================= */
let stream = null;
$("#btn-camera").addEventListener("click", async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    $("#camera-video").srcObject = stream;
    $("#cam-empty").hidden = true;
    $("#btn-analyze").disabled = false; $("#btn-camera-off").disabled = false;
    $("#camera-status").textContent = "Camera live. Analyze a frame to see SAM masks.";
  } catch { $("#camera-status").textContent = "Camera permission unavailable here."; }
});
$("#btn-camera-off").addEventListener("click", () => {
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
  $("#camera-video").srcObject = null;
  $("#cam-empty").hidden = false;
  $("#btn-analyze").disabled = true; $("#btn-camera-off").disabled = true;
  $("#camera-status").textContent = "Camera is off.";
});
$("#btn-analyze").addEventListener("click", async () => {
  const video = $("#camera-video"), out = $("#segment-status");
  if (!video.videoWidth) { out.textContent = "Enable the camera first."; return; }
  const canvas = document.createElement("canvas");
  const scale = Math.min(1, 640 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale); canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  out.textContent = "Analyzing with SAM 3.1…";
  try {
    const r = await fetch("/api/segment-live", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: canvas.toDataURL("image/jpeg", 0.72),
        prompts: ["red cube", "blue cube", "yellow cube", "bin"] }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || "Segmentation failed.");
    const overlay = $("#cam-overlay"); overlay.textContent = "";
    for (const res of d.results || []) {
      const fw = res.frame_w || 640, fh = res.frame_h || 400;
      for (const b of res.boxes || []) {
        const el = document.createElement("div"); el.className = "cam-box";
        el.style.left = `${(b.x / fw) * 100}%`; el.style.top = `${(b.y / fh) * 100}%`;
        el.style.width = `${(b.w / fw) * 100}%`; el.style.height = `${(b.h / fh) * 100}%`;
        const tag = document.createElement("span"); tag.textContent = b.label || res.prompt;
        el.append(tag); overlay.append(el);
      }
    }
    const found = (d.results || []).map(x => `${x.prompt}:${(x.boxes || []).length}`).join(" · ");
    out.textContent = `SAM 3.1 · ${d.latency_ms}ms · ${found}`;
  } catch (e) { out.textContent = e.message; }
});

drawBins();
drawCubes();
setArm(320, 215);
