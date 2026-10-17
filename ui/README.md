# FORGE live demo UI

Single-screen live view. stdlib server, plain HTML/JS, three.js vendored (no install).

```
python3 ui/serve.py                 # http://localhost:8008  tails newest runs/**/events.jsonl
python3 ui/serve.py --run runs/X    # pin one run dir
```

URLs
- `/`                                  live: SSE tail of the newest run (auto-switches when a newer run appears)
- `/?run=runs/<dir>`                   live tail of a specific run
- `/?replay=runs/<dir>&speed=4`        judges' fallback: replay a finished run at 4x (`&n=12` stops after 12 events)
- `/?replay=ui/fixture/br02`           cached real run (br02, playbook v2, solved; includes playbook/history snapshot). Default fallback.
- `/?replay=ui/fixture/demo`           synthetic fixture built by make_fixture.py (two iterations, gate events inline)

Events consumed (`runs/<run>/events.jsonl`, `{ts, kind, payload}`):
`spec` (prompt / done_means), `design` (params, claim, stl), `verdict` (ok, reason, checks, cases, mass_g, parity_gap, stl),
`critic` (hypothesis | text), `cost` (spent_usd | usd_total), `gate` (loop status, or {kept, dev_score_old/new, diff}).
Playbook gate + held-out A/B are also read from `playbook/history.jsonl` (polled every 3 s).

Fixtures: `ui/fixture/br02` is a straight copy of `runs/br02_<ts>/{events.jsonl,br02/*.stl}` plus `playbook/{v*.md,history.jsonl}` with paths rewritten to `ui/fixture/br02/playbook/`. To refresh: copy the run dir, then `sed 's#"playbook/#"ui/fixture/br02/playbook/#g' playbook/history.jsonl > ui/fixture/br02/playbook/history.jsonl`.
`ui/fixture/demo`: `/opt/miniconda3/bin/python ui/fixture/make_fixture.py` (needs cadquery + FreeCAD gmsh/ccx).

Verdict colouring mirrors `forge/loop.py physics_ok`: parity (agent claim vs referee) never gates solved, so a design with all safety checks green but a parity miss shows **PASS · parity gap** (green) with the gap in the referee panel.

Screenshot check:
```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1920,1080 --virtual-time-budget=30000 --screenshot=ui/shots/live.png \
  "http://localhost:8008/?replay=ui/fixture/demo&speed=40"
```
