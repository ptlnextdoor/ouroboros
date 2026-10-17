# Tooling research: how others drive CAD from an agent, and what FORGE should steal

Date: 2026-10-17. Scope: 15-minute survey of open-source LLM-to-CAD bridges, compared
against our Fusion360LiveMCP add-in (`server/socket_server.py`, `event_bridge.py`,
`command_handler.py`) and the Studio client (`studio/fusion.py`, `studio/mj1bridge.py`).

## 1. Findings table

| Project | Transport | (a) Main-thread safety | (b) Timeouts / retries | (c) Viewport images | (d) Tools exposed |
|---|---|---|---|---|---|
| [frankhommers/autodesk-fusion-mcp](https://github.com/frankhommers/autodesk-fusion-mcp) (MIT, 28★, active Sep 2026) | Streamable HTTP MCP served *inside* the add-in, stdlib only | `registerCustomEvent` + `fireCustomEvent`, 75 ms timer tick with 2 s keepalive, batch of 8 per drain, `_run_lock` re-entrancy guard ([dispatch.py](https://raw.githubusercontent.com/frankhommers/autodesk-fusion-mcp/main/fusion_bridge/dispatch.py)) | Envelope state machine `queued -> running -> done/cancelled` with per-envelope lock. Timeout message distinguishes "queued, cancelled, safe to retry" from "running, may complete, do NOT retry". `wait_for_main_thread()` round-trips a `__startup_ping__` before binding the port so cold-start clients never hang ([PR #3](https://github.com/frankhommers/autodesk-fusion-mcp/pull/3)). Default main-thread timeout 120 s. | `capture_viewport` (PNG, temp views, transparency, crop), `get_viewport`/`set_viewport` camera state | 14 tools: `call_autodesk_api` (dotted path + `$stored` refs), `execute_python`, viewport x3, `get_active_selection`, `manage_annotations` (user pins geometry + note, agent claims/completes with revision check), API doc fetch, script store |
| [faust-machines/fusion360-mcp-server](https://github.com/faust-machines/fusion360-mcp-server) (MIT, 123★, PyPI) | stdio MCP -> TCP `:9876` newline JSON -> add-in. **This is the lineage of our add-in** (same port, same `ping` fast-path, same `get_scene_info`). | CustomEvent bridge in the add-in | Add-in bridge times out at 30 s and *cancels* the queued command; client waits 45 s so it receives the structured TIMEOUT. README rule: "Mutation commands are never auto-retried; after a timeout call `get_scene_info` to check what was applied." "One operation per tool call, batching crashes the add-in." | `export_view_sheet` (iso/front/top/right PNG sheet for visual inspection) | 93 tools: sketch, features, sheet metal, assembly joints, inspection (`measure_*`, `check_interference`, `compare_meshes`), parameters, import/export, CAM post-process |
| [neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) (trending, FreeCAD) | XML-RPC server thread -> Qt GUI thread | [gui_dispatch.py](https://raw.githubusercontent.com/neka-nat/freecad-mcp/main/addon/FreeCADMCP/rpc_server/gui_dispatch.py): per-call response queue, Qt signal wake + 500 ms heartbeat fallback, mouse-drag / popup / modal guards (capped at 5 s so a lost mouse-release can't wedge it), re-entrancy guard | Best design seen: **run budget starts when the task starts, queue wait budgeted separately** (`queue_timeout`), so two concurrent `execute_code` calls each get their full budget. **Stuck-task fail-fast**: once a running task overruns, later calls fail immediately until it returns. `get_rpc_status` reports dispatch health without touching the GUI thread. `execute_code_async` + `get_async_status` + `commit(fn)` for long OCCT work. | `get_view` screenshot of active 3D view (base64) | `execute_code{,_async,_headless}`, `create/edit/delete_object`, `get_objects`, `insert_part_from_library`, `run_fem_analysis` (CalculiX, 600 s timeout) |
| [Aaradhya-Dev-Tamrakar/fusion360-mcp](https://github.com/Aaradhya-Dev-Tamrakar/fusion360-mcp) | HTTP `/mcp` on `:9876` inside add-in | Worker thread fires `fireCustomEvent` and awaits a `threading.Event` | basic | captures viewport screenshots in the handler | modeling, inspection, script execution, rendering |
| [AuraFriday/Fusion-360-MCP-Server](https://github.com/AuraFriday/Fusion-360-MCP-Server) (Autodesk App Store) | SSE to an external MCP-Link server | "All Fusion API calls execute on Fusion's main UI thread", work-queue system | auto-reconnect with exponential backoff | n/a in README | inline Python with full `adsk.*`, popups, SQLite |
| [Adam-CAD/CADAM](https://github.com/Adam-CAD/CADAM) (GPL-3, 5.3k★) | Browser app, OpenSCAD WASM, not a Fusion bridge | n/a (no desktop CAD) | n/a | Three.js live preview, orbiting benchmark GIFs | Text/image -> OpenSCAD, **parameter extraction into sliders**, "smart updates" (re-render on slider change without re-prompting), STL/SCAD/DXF export, benchmarks/ folder with prompt + result per model |

Adam (adam.new, the commercial copilot): "CAD as code" (FeatureScript on Onshape, Python on Fusion), "workstreams" that chain Slack/CAD/Gmail, results presented for review before actions, draft-then-approve for emails, context preserved by referencing the original request and files. In Onshape they rely on the history tree for rollback and do not yet label which changes the agent made (Product Hunt maker reply, Oct 2026). Sources: [adam.new/copilot](https://adam.new/copilot), [Show HN](https://news.ycombinator.com/item?id=47977694), [Product Hunt](https://www.producthunt.com/products/adam-cad-copilot).

## 2. Where our add-in already matches or beats them

- `event_bridge.py` already has the CustomEvent + 200 ms backup timer, cancel-if-not-started, the "ALREADY RUNNING, do NOT retry" message, caller-settable `timeout_s` (max 600), and `late_results()` retention (20 entries). frankhommers has the same state machine; nobody else keeps late results.
- `render_view` clamps to 4096 px, restores the camera, returns base64 PNG. Equivalent to frankhommers `capture_viewport` minus transparency/crop.
- `hints.classify()` turns Fusion exceptions into `error_kind` + hints. None of the surveyed repos do this.

## 3. The 3 highest-value robustness fixes (each under 20 minutes)

### Fix 1: honest health check (the `ping` fast-path lies when the main thread is wedged)

Problem: `EventBridge.submit` answers `ping` without touching the queue, so `studio/fusion.py:ping()` and the Studio status pill report "fusion reachable" even while Fusion's main thread is stuck in a modal dialog or a 3000-feature recompute. Studio then launches a 120 s `execute_code` that is doomed. frankhommers solves this with `__startup_ping__` through the dispatcher; freecad-mcp with `get_rpc_status`.

Change, `event_bridge.py` `submit()`:
```python
if cmd_type == "ping" and not (command.get("params") or {}).get("deep"):
    return {"status": "success", "result": {"ok": True, "status": "pong"}}
# deep ping falls through to the queue; handler returns pong on main thread
```
and in `drain_queue` before `execute_command`: `if cmd_type == "ping": item.result = {"status":"success","result":{"ok":True,"status":"pong","main_thread":True}}`.

Change, `studio/fusion.py`:
```python
def ping(deep=True):
    try:
        r = call("ping", {"deep": deep, "timeout_s": 3}, timeout=3)
        return r.get("status") == "success"
    except Exception:
        return False
```
`server.py` `/health` already calls `fusion.ping()`; it now reflects real main-thread liveness in under 3 s.

### Fix 2: stuck-task fail-fast + busy status in the bridge (stop burning a full timeout per queued caller)

Problem: when one `execute_code` overruns, every later Studio call (`render_view`, `components()`, the worker thread and the chat thread both call `fusion.call`) queues behind it and waits its *own* full timeout before failing, so a 30 s stall becomes minutes of dead UI. freecad-mcp's dispatcher rejects immediately while a task is stuck and reports what is running.

Change, `event_bridge.py`:
```python
# __init__
self._current = None   # (cmd_type, started_monotonic, budget_s)

# drain_queue, right after item.started = True
self._current = (cmd_type, t0, command_timeout(item.command))
# ... in the finally:
self._current = None

# submit(), before queueing (after the ping fast-path)
cur = self._current
if cur is not None:
    name, t0, budget = cur
    elapsed = time.monotonic() - t0
    if elapsed > budget:
        return {"status": "error", "error_kind": "BUSY",
                "running": name, "running_for_s": round(elapsed, 1),
                "message": f"Fusion main thread has been running {name} for {elapsed:.0f}s "
                           f"(past its {budget:.0f}s budget). Not queued; retry after it finishes "
                           "or read late_results()."}
```
Also expose it: in `_cmd_get_scene_info` (or the deep ping result) add `"bridge": {"running": name, "queued": self._queue.qsize()}` so Studio can render "Fusion busy: execute_code 41 s" instead of a spinner.

### Fix 3: Studio client serialises its own calls and reconciles late results instead of failing the turn

Problem: `studio/server.py` has two daemon threads (`worker` at line 138, `run_turn` at line 336) that can both enter `fusion.call()`; the add-in accepts both connections and queues them, so each steals the other's time budget (the "two clients at once" timeout in the brief). And when `_exec` gets the "ALREADY RUNNING" TIMEOUT it raises, discarding work Fusion will finish seconds later.

Change, `studio/fusion.py`:
```python
import threading, time, uuid
_LOCK = threading.Lock()          # one in-flight Fusion call per Studio process

def call(cmd, params=None, timeout=90.0):
    with _LOCK:
        return _call_unlocked(cmd, params, timeout)   # existing body, renamed

def _exec(code, timeout=90.0):
    rid = uuid.uuid4().hex[:8]
    r = call("execute_code", {"code": code, "timeout_s": timeout, "request_id": rid}, timeout)
    if isinstance(r, dict) and r.get("error_kind") == "TIMEOUT" and "ALREADY RUNNING" in r.get("message", ""):
        deadline = time.time() + 60
        while time.time() < deadline:
            time.sleep(2)
            late = call("execute_code", {"code": "late_results()", "timeout_s": 5}, 10)
            for entry in (late.get("result") or {}).get("result") or []:
                if entry.get("request_id") == rid:
                    r = entry.get("response") or {"status": "error", "message": entry.get("error")}
                    break
            else:
                continue
            break
    if not isinstance(r, dict) or r.get("status") != "success":
        raise FusionError(f"execute_code failed: {json.dumps(r)[:400]}")
    ...
```
One-line companion in `event_bridge.py` `drain_queue` where `LATE_RESULTS.append(...)`: add `"request_id": (item.command.get("params") or {}).get("request_id")` so late results are correlatable. Never auto-retry a mutation (faust-machines rule); the reconciliation above is read-only.

## 4. Side-panel UX worth stealing

- **Workstream cards with an approval gate** (Adam): each agent step is a card with status, the Fusion viewport PNG it produced, and "apply / skip" before any mutation. We already return `image_base64` from `fusion_build` and `capture`; render it per card rather than at the end.
- **Source citations on cards**: Adam cites the original request and connected files; FORGE should cite the referee artifact (CalculiX run id, STEP path, `mass_delta_pct`) on the card. `fusion_build` already returns these fields.
- **Pinned-selection annotations** (frankhommers `manage_annotations`): user selects geometry in Fusion, types a note, agent claims it. Cheap version for us: `get_active_selection` via `execute_code` and show "working on: Body3 face 12" in the panel.
- **Parameter sliders** (CADAM): extract the sizing-model inputs (`t_plate`, `arm_len`, ...) into sliders; re-run `blocks.build` + STEP import on change without a new prompt.
- **Multi-view sheet** (faust `export_view_sheet`): one iso/front/top/right PNG per card beats four round-trips.
- **"Fusion busy" pill** fed by Fix 1 + Fix 2 instead of an indefinite spinner.

## 5. What to say to judges about tooling

FORGE drives the real Autodesk Fusion session, not a toy renderer: a stdlib-only add-in marshals every API call onto Fusion's main thread through the CustomEvent queue (the same pattern as the best open-source Fusion MCP bridges), distinguishes "cancelled before it ran, safe to retry" from "already running, never retry", keeps the results of calls that outlived their wait so nothing the agent did is lost, and classifies Fusion exceptions into actionable hints. Everything the agent shows you is a viewport capture from Fusion itself, and every part it imports is the exact STEP the CalculiX referee signed off, with Fusion's own volume cross-checked against the referee mass. Where Adam is a closed copilot and CADAM stops at OpenSCAD, FORGE closes the loop from physics to the engineer's actual CAD file, on a free inference stack, with the bridge code open and auditable.
