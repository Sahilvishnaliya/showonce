# ShowOnce

**Teach a robot by showing it once.**

A human demonstrates a pick-and-place task once on a bench. SAM 3.1 tracks every
object's mask through the demonstration; Muse Wonder compiles it into a robot
program — and ShowOnce infers the *rule* behind the demo (e.g. sort by colour),
so the robot repeats the task correctly on a rearranged bench, then verifies
its own work with vision.

Built for the Meta Global AI Developer Hackathon (Indie track · Push the Frontier ·
Robotics). New work, built during the event; commit history is the record.

## Run

```bash
pip install -r requirements.txt
python app.py            # http://127.0.0.1:5000
python -m unittest discover -s tests -v
```

The teach → learn → repeat → verify loop runs with no keys (deterministic rule
inference, planning, and verification are real code). For live camera SAM
segmentation, set `MODEL_API_KEY` and `SECONDNURSE_MODE=live` in the
environment (Vercel or `.env`); the `/api/segment-live` endpoint then segments
real bench frames with SAM 3.1 and decodes masks with the official
`meta_sam_parser`.

## How it works

1. **Demonstrate** — animated bench (or a real camera): objects are tracked.
2. **Learn** (`core/learn.py`) — tracks + bins → inferred rule + pick-and-place
   program (StepGraph-style JSON).
3. **Repeat** (`core/robot.py`) — a 2-link IK robot arm plans from *live* object
   positions, so shuffled benches work.
4. **Verify** (`core/robot.py`) — final object positions are checked against the
   rule; the robot scores its own run.

## API

| Route | Body | Returns |
|---|---|---|
| `GET /api/health` | — | status, SAM live/config mode |
| `POST /api/learn` | `{tracks, bins}` | learned program (rule, steps, confidence) |
| `POST /api/plan` | `{objects, bins, program}` | ordered pick/place actions |
| `POST /api/verify` | `{objects, bins}` | per-object pass/fail + score |
| `POST /api/segment-live` | `{image, prompts}` | SAM 3.1 boxes/masks for a camera frame |

## Design

Playground-theme product design: warm cream canvas, ink-navy Inter Tight,
single blue action colour, orange robotics accent, rounded floating product
cards. Docs in `docs/`.
