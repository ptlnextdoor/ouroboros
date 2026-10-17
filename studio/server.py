"""FORGE Studio server: one HTTP endpoint that streams a real agent turn.

POST /chat {message} -> Server-Sent Events. We run the real FORGE loop
(forge.loop.solve) on the task closest to the typed goal, tail its events.jsonl,
and forward every step to the browser as it happens: spec, each designer, the
CalculiX referee verdict (incl. HIDDEN loads), the critic, running $ cost. When
the loop solves, we build the winning bracket LIVE in Fusion 360 and stream the
viewport PNG back into the chat.

No mocking: the agents run on Crusoe Managed Inference, the referee runs
CalculiX, and the part is imported into Fusion over the add-in socket. Numbers
shown are the ones those tools produced.
"""
import json
import os
import queue
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")

HERE = os.path.dirname(os.path.abspath(__file__))

from forge.llm import MODELS                       # noqa: E402
from forge import loop as forge_loop               # noqa: E402
from studio import fusion                          # noqa: E402

# human labels for the agent rows
AGENT_MODEL = {
    "spec": ("Spec", MODELS["spec"]),
    "design": ("Designer", MODELS["designer"]),
    "designer": ("Designer", MODELS["designer"]),
    "verdict": ("Referee", "CalculiX (CCX) FEA"),
    "critic": ("Critic", MODELS["critic"]),
    "gate": ("Gate", "FORGE"),
    "cost": ("", ""),
}

# the 16 known bracket goals, for closest-match resolution of a typed prompt
TASKS = forge_loop  # re-use its loaders


def load_catalogue():
    cat = []
    tdir = os.path.join(ROOT, "tasks")
    for fn in sorted(os.listdir(tdir)):
        if fn.startswith("br") and fn.endswith(".json"):
            cat.append(json.load(open(os.path.join(tdir, fn))))
    return cat


CATALOGUE = load_catalogue()


def _tokens(s):
    out, cur = set(), ""
    for ch in s.lower():
        if ch.isalnum() or ch == ".":
            cur += ch
        elif cur:
            out.add(cur); cur = ""
    if cur:
        out.add(cur)
    return out


def closest_task(goal):
    g = goal.lower()
    for t in CATALOGUE:
        if t["id"] in g:
            return t
    gt = _tokens(goal)
    best, best_score = CATALOGUE[1], -1.0
    for t in CATALOGUE:
        tt = _tokens(t["prompt"])
        uni = len(gt | tt)
        score = len(gt & tt) / uni if uni else 0.0
        if score > best_score:
            best, best_score = t, score
    return best


# ---------------------------------------------------------------------------
# run one turn, streaming SSE events into a queue
# ---------------------------------------------------------------------------
def run_turn(goal, q, playbook_rel="playbook/v2.md"):
    def send(ev, **data):
        q.put(dict(event=ev, **data))

    try:
        task = closest_task(goal)
        send("turn", task=task["id"], prompt=task["prompt"], goal=goal,
             material=task["material"], mass_limit_g=task["mass_limit_g"],
             fos=task["fos"], defl_limit_mm=task["defl_limit_mm"])

        run_dir = os.path.join(ROOT, "runs", f"studio_{task['id']}_{int(time.time())}")
        os.makedirs(run_dir, exist_ok=True)
        events_path = os.path.join(run_dir, "events.jsonl")
        open(events_path, "a").close()

        playbook = open(os.path.join(ROOT, playbook_rel)).read()
        result = {"best": None, "trace": None, "error": None}

        def worker():
            try:
                from forge.llm import LLM
                llm = LLM(run_dir=run_dir, budget_usd=1.0)
                best, trace = forge_loop.solve(task, playbook, llm=llm, run_dir=run_dir,
                                               max_iters=6, n_designers=4, save_stl=False)
                result["best"], result["trace"] = best, trace
            except Exception as e:  # surface, don't hang the stream
                result["error"] = f"{type(e).__name__}: {e}"

        th = threading.Thread(target=worker, daemon=True)
        th.start()

        # tail events.jsonl, forward each as an SSE event, until the loop ends
        pos = 0
        step_t0 = {}
        done = False
        while not done:
            if not th.is_alive() and result["trace"] is not None:
                done = True  # one last drain pass below
            try:
                with open(events_path) as f:
                    f.seek(pos)
                    lines = f.readlines()
                    pos = f.tell()
            except FileNotFoundError:
                lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                _forward(rec, send, step_t0)
            if result["error"] and not th.is_alive():
                break
            if not done:
                time.sleep(0.15)

        th.join(timeout=5)
        if result["error"]:
            send("error", message=result["error"])
            return

        best, trace = result["best"], result["trace"]
        solved = bool(trace and trace.get("solved"))
        send("summary", solved=solved, iters=trace.get("iters") if trace else None,
             stop_reason=trace.get("stop_reason") if trace else None,
             spent_usd=trace.get("spent_usd") if trace else None,
             calls=trace.get("calls") if trace else None,
             mass_g=(best["verdict"].get("mass_g") if best else None))

        # the moment: build the winning part live in Fusion 360
        if best and best.get("clamped"):
            send("fusion", status="start", note="building the winning bracket in Fusion 360")
            try:
                fb = fusion.fusion_build(best["clamped"], task_id=task["id"],
                                         material=task["material"],
                                         referee_mass_g=best["verdict"].get("mass_g"))
                send("fusion", status="done", **{k: v for k, v in fb.items() if k != "image_base64"})
                send("image", source="fusion", caption=f"{fb['component']} in Fusion 360",
                     image_base64=fb["image_base64"])
            except Exception as e:
                send("fusion", status="error", message=f"{type(e).__name__}: {e}")
        else:
            send("fusion", status="skip", message="no passing design to build")
    except Exception as e:
        send("error", message=f"{type(e).__name__}: {e}")
    finally:
        q.put(None)  # sentinel: stream complete


def _forward(rec, send, step_t0):
    """Translate a forge.loop event record into a Studio SSE event."""
    kind = rec.get("kind")
    p = rec.get("payload", {})
    ts = rec.get("ts", time.time())

    if kind == "spec":
        if p.get("status") == "start":
            step_t0["spec"] = ts
            send("step", agent="Spec", model=MODELS["spec"], kind="thought",
                 text=f"reading goal: {p.get('prompt', '')}")
        else:
            ms = int(1000 * (ts - step_t0.get("spec", ts)))
            send("step", agent="Spec", model=MODELS["spec"], kind="result", ms=ms,
                 text="definition of done set",
                 done_means=p.get("done_means"), mass_limit_g=p.get("mass_limit_g"))
    elif kind == "design":
        if p.get("status") == "start":
            step_t0[f"design{p.get('iter')}"] = ts
            send("step", agent="Designer", model=MODELS["designer"], kind="thought",
                 iter=p.get("iter"),
                 text=f"iteration {p.get('iter', 0) + 1}: {p.get('n', 4)} designers proposing in parallel")
        else:
            send("step", agent=f"Designer {p.get('k', 0) + 1}", model=MODELS["designer"],
                 kind="tool", iter=p.get("iter"), k=p.get("k"),
                 params=p.get("params"), claim=p.get("claim"),
                 text=p.get("rationale", ""))
    elif kind == "verdict":
        send("step", agent="Referee", model="CalculiX FEA", kind="verdict",
             iter=p.get("iter"), k=p.get("k"), ok=p.get("ok"), reason=p.get("reason"),
             mass_g=p.get("mass_g"), parity_gap=p.get("parity_gap"),
             checks=p.get("checks"), cases=p.get("cases"))
    elif kind == "critic":
        send("step", agent="Critic", model=MODELS["critic"], kind="thought",
             iter=p.get("iter"), text=p.get("hypothesis", ""))
    elif kind == "cost":
        send("cost", spent_usd=p.get("spent_usd"), calls=p.get("calls"))
    elif kind == "gate":
        status = p.get("status")
        if status in ("solved", "stuck", "done"):
            send("step", agent="Gate", model="FORGE", kind="verdict",
                 text=f"{status}: {p.get('reason') or p.get('stop_reason') or ''}",
                 ok=(status == "solved" or p.get("solved")), mass_g=p.get("mass_g"),
                 score=p.get("score"))


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send_file(self, rel, ctype):
        path = os.path.join(HERE, rel)
        try:
            data = open(path, "rb").read()
        except FileNotFoundError:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send_file("index.html", "text/html; charset=utf-8")
        elif path == "/health":
            body = json.dumps({"ok": True, "fusion": fusion.ping()}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if self.path.split("?")[0] == "/layout":
            self._tile_windows()
            return
        if self.path.split("?")[0] != "/chat":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            goal = (json.loads(raw).get("message") or "").strip()
        except Exception:
            goal = ""
        if not goal:
            self.send_response(400); self.end_headers(); return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        q = queue.Queue()
        th = threading.Thread(target=run_turn, args=(goal, q), daemon=True)
        th.start()
        while True:
            item = q.get()
            if item is None:
                break
            try:
                self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break

    def _tile_windows(self):
        try:
            from studio import layout
            msg = layout.tile()
            ok = True
        except Exception as e:
            msg, ok = f"{type(e).__name__}: {e}", False
        body = json.dumps({"ok": ok, "message": msg}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8010)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"FORGE Studio on http://127.0.0.1:{args.port}  (fusion reachable: {fusion.ping()})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
