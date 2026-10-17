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
- `/?replay=ui/fixture/demo`           built-in fixture (real referee verdicts + STLs)

Events consumed (`runs/<run>/events.jsonl`, `{ts, kind, payload}`):
`spec` (prompt / done_means), `design` (params, claim, stl), `verdict` (ok, reason, checks, cases, mass_g, parity_gap, stl),
`critic` (hypothesis | text), `cost` (spent_usd | usd_total), `gate` (loop status, or {kept, dev_score_old/new, diff}).
Playbook gate + held-out A/B are also read from `playbook/history.jsonl` (polled every 3 s).

Fixture: `/opt/miniconda3/bin/python ui/fixture/make_fixture.py` (needs cadquery + FreeCAD gmsh/ccx).

Screenshot check:
```
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1920,1080 --virtual-time-budget=30000 --screenshot=ui/shots/live.png \
  "http://localhost:8008/?replay=ui/fixture/demo&speed=40"
```
