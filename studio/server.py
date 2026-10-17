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
TRANSCRIPTS = os.path.join(HERE, "runs")
os.makedirs(TRANSCRIPTS, exist_ok=True)

from forge.llm import MODELS                       # noqa: E402
from forge import loop as forge_loop               # noqa: E402
from studio import fusion                          # noqa: E402
from studio import mj1bridge                        # noqa: E402
from studio import mj1flow                          # noqa: E402
from studio import router, cadtools                  # noqa: E402

# words that route a goal to the MJ-1 supersonic-jet pipeline instead of brackets
JET_WORDS = ("supersonic", "mach", "jet", "drone", "aircraft", "plane", "boom",
             "delivery", "flight", "fly", "turbine", "wing")

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

    # route: one Nemotron-Super call decides new_jet / new_bracket / edit / question
    t0 = time.time()
    try:
        mj1bridge._activate("MJ1")
        names = cadtools.list_occurrences().get("names", [])
    except Exception:
        names = []
    decision = router.route(goal, names)
    intent = decision["intent"]
    ed = decision.get("edit") or {}
    rtxt = f"intent: {intent}"
    if intent == "edit":
        rtxt += f" · target: {ed.get('target')} · {ed.get('value')}"
    send("step", agent="Router", model="Nemotron-3-Super", kind="result",
         ms=int(1000 * (time.time() - t0)), text=rtxt, decision=decision)

    if intent == "new_jet":
        try:
            mj1flow.run_mj1_turn(goal, send, mj1bridge)
        except Exception as e:
            send("error", message=f"{type(e).__name__}: {e}")
        finally:
            q.put(None)
        return
    if intent in ("edit", "question"):
        try:
            _edit_turn(goal, decision, send)
        except Exception as e:
            send("error", message=f"{type(e).__name__}: {e}")
        finally:
            q.put(None)
        return

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


def _edit_turn(goal, decision, send):
    """edit -> apply in Fusion, stream image + Done; question -> one Spec step."""
    send("turn_mj1", goal=goal, subject="MJ-1", rules=mj1flow.BOOM_RULES)
    if decision["intent"] == "question":
        send("step", agent="Spec", model=MODELS["spec"], kind="result",
             text=decision.get("reply") or "(no reply)")
        send("summary_mj1", done=decision.get("reply") or "Done.")
        return
    ed = decision["edit"]
    t0 = time.time()
    if ed["action"] == "revert":
        send("step", agent="CAD", model="Fusion 360", kind="tool",
             text="restoring the original appearances saved before our edits, removing FORGE colours")
        r = cadtools.revert_appearance(ed.get("target") or ".*")
        what = (f"Restored the original appearance on {r.get('count', 0)} bodies and removed "
                f"{len(r.get('removed', []))} added colour(s)")
    elif ed["action"] == "visibility":
        show = str(ed.get("value", "hide")).lower().startswith("show")
        send("step", agent="CAD", model="Fusion 360", kind="tool",
             text=f"{'showing' if show else 'hiding'} occurrences matching /{ed['target']}/")
        r = cadtools.set_visibility(ed["target"], show)
        what = f"{'Showed' if show else 'Hid'} {r['count']} part(s) ({', '.join(r['targets'][:6])})"
    else:
        send("step", agent="CAD", model="Fusion 360", kind="tool",
             text=f"searching appearance libraries for '{ed['value']}' · applying to /{ed['target']}/")
        r = cadtools.set_appearance(ed["target"], ed["value"])
        what = (f"Applied {r['appearance']} to {r['count']} parts "
                f"({', '.join(r['targets'][:6])})")
    ms = int(1000 * (time.time() - t0))
    send("step", agent="CAD", model="Fusion 360", kind="result", ms=ms, text=what, **r)
    png = cadtools.capture("iso")
    send("image", source="fusion", caption=f"MJ-1 in Fusion 360 · {what}", image_base64=png)
    send("summary_mj1", done=f"Done. {what}.")


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
SQ2_SYSTEM = (
    "You are FORGE's CAD agent editing SQ-2, a 590 km/h electric quadcopter, written in OpenSCAD. "
    "You get the CURRENT full source and one request. Change the model the way an aero/mechanical "
    "engineer would. Reply with STRICT JSON only:\n"
    '{"set": {"<param>": <number>, ...}, "replace": [{"old": "<exact unique substring>", "new": "<text>"}], '
    '"say": "<one short sentence: what changed and the engineering effect>"}\n'
    "Prefer \"set\" for anything a top-of-file parameter covers (values must respect the [min:max] "
    "comments). Use \"replace\" only for topology the parameters cannot express (new module, "
    "different section shape, extra part); old must be copied exactly from the source. Keep the "
    "model a valid closed solid. Never remove the stage logic. Either key may be empty. "
    "The say sentence must be physically correct: SQ-2 flies at Mach 0.48, so there is no wave "
    "drag; a blunter or shorter nose ADDS pressure drag, a longer finer nose cuts it; thinner, "
    "more swept fins cut drag but lose some yaw authority. If a request costs performance, say so."
)
_SQ2_LLM = None


def sq2_edit(message, code, error=None):
    """-> {set, replace, say, ms, model}. One Crusoe call, Lightning first (about 1 s)."""
    global _SQ2_LLM
    from forge.llm import LLM, parse_json
    if _SQ2_LLM is None:
        _SQ2_LLM = LLM(run_dir="runs/_sq2edit", budget_usd=3.0)
    user = f"CURRENT SOURCE:\n```openscad\n{code}\n```\n\nREQUEST: {message}"
    if error:
        user += f"\n\nYour previous edit failed to compile:\n{error[:1500]}\nFix it."
    t0 = time.time()
    out = {"set": {}, "replace": [], "say": ""}
    for role in ("designer", "spec"):
        try:
            txt = _SQ2_LLM.chat(role, [{"role": "system", "content": SQ2_SYSTEM},
                                       {"role": "user", "content": user}],
                                temperature=0, max_tokens=1500, meta=dict(agent="sq2_edit"))
            got = parse_json(txt)
            if isinstance(got, dict) and (got.get("set") or got.get("replace")):
                out.update({k: got[k] for k in ("set", "replace", "say") if k in got})
                out["model"] = MODELS[role]
                break
        except Exception as e:
            out["say"] = f"model error: {e}"[:200]
    out["ms"] = int((time.time() - t0) * 1000)
    return out


SQ2_FUSION_DOC = "SQ2 FORGE live"
_SQ2_FIT = [False]


def sq2_to_fusion(groups, snap=False):
    """groups: [{rgb:[r,g,b] 0-1, tris: base64 float32 xyz*9 per tri}] -> Fusion.

    One STL per colour group, imported as mesh bodies into the 'SQ2 FORGE live' document.
    The previous version's bodies are deleted first, so Fusion always shows exactly the
    current geometry (no stacked copies)."""
    import base64, struct
    t0 = time.time()
    d = os.path.join(HERE, "runs", "sq2_fusion")
    os.makedirs(d, exist_ok=True)
    files = []
    for i, g in enumerate(groups):
        raw = base64.b64decode(g["tris"])
        n = len(raw) // 36
        p = os.path.join(d, f"g{i}.stl")
        with open(p, "wb") as f:
            f.write(b"\0" * 80 + struct.pack("<I", n))
            for k in range(n):
                f.write(b"\0" * 12 + raw[36 * k:36 * k + 36] + b"\0\0")
        files.append([p, [int(255 * c) for c in g["rgb"]]])
    if snap:
        sd = os.path.join(d, "snaps")
        os.makedirs(sd, exist_ok=True)
        snap = os.path.join(sd, "pending.png")
    code = f'''
import adsk.core, adsk.fusion, json
app = adsk.core.Application.get()
DOC = {SQ2_FUSION_DOC!r}
doc = None
for i in range(app.documents.count):
    if app.documents.item(i).name.startswith(DOC):
        doc = app.documents.item(i)
if doc is None:
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    doc.name = DOC
doc.activate()
des = adsk.fusion.Design.cast(app.activeProduct)
if des.designType != adsk.fusion.DesignTypes.DirectDesignType:
    des.designType = adsk.fusion.DesignTypes.DirectDesignType
root = des.rootComponent
for i in range(root.meshBodies.count - 1, -1, -1):
    root.meshBodies.item(i).deleteMe()
lib = app.materialLibraries.itemByName("Fusion Appearance Library")
base = None
for i in range(lib.appearances.count):
    a = lib.appearances.item(i)
    if "Paint - Enamel Glossy" in a.name:
        base = a; break
n = 0
for path, rgb in {files!r}:
    mb = root.meshBodies.add(path, adsk.fusion.MeshUnits.MillimeterMeshUnit)
    nm = "SQ2_%d_%d_%d" % tuple(rgb)
    ap = des.appearances.itemByName(nm)
    if ap is None and base is not None:
        ap = des.appearances.addByCopy(base, nm)
        for k in range(ap.appearanceProperties.count):
            pr = ap.appearanceProperties.item(k)
            if isinstance(pr, adsk.core.ColorProperty):
                pr.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255); break
    for k in range(mb.count):
        b = mb.item(k)
        if ap is not None: b.appearance = ap
        n += 1
vp = app.activeViewport
vp.visualStyle = adsk.core.VisualStyles.ShadedVisualStyle
cam = vp.camera
cam.isSmoothTransition = False
cam.cameraType = adsk.core.CameraTypes.PerspectiveCameraType
tgt = adsk.core.Point3D.create(28.0, 0, 0)
cam.target = tgt
# same view direction as the FORGE three.js camera (1.15, -1.35, 0.75 in SCAD axes)
cam.eye = adsk.core.Point3D.create(28.0 + 1.15 * 70, -1.35 * 70, 0.75 * 70)
cam.upVector = adsk.core.Vector3D.create(0, 0, 1)
cam.viewExtents = 265.0
vp.camera = cam
vp.refresh()
snap = {snap!r}
if snap:
    vp.saveAsImageFile(snap, 1280, 1440)
json.dumps({{"bodies": n, "doc": doc.name}})
'''
    r = fusion._exec(code, 60.0)
    out = json.loads(r) if isinstance(r, str) else (r or {})
    if isinstance(out, dict) and isinstance(out.get("result"), str):
        try:
            out = json.loads(out["result"])
        except Exception:
            pass
    out["ms"] = int((time.time() - t0) * 1000)
    if snap and os.path.exists(snap):
        os.rename(snap, os.path.join(os.path.dirname(snap), f"{time.time():.3f}.png"))
    return out


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
        elif path == "/sq2":
            self._send_file("sq2.html", "text/html; charset=utf-8")
        elif path == "/sq2.scad":
            self._send_file("sq2.scad", "text/plain; charset=utf-8")
        elif path.startswith("/vendor/") and ".." not in path:
            ext = path.rsplit(".", 1)[-1]
            self._send_file(path[1:], {"js": "text/javascript", "wasm": "application/wasm"}.get(ext, "application/octet-stream"))
        elif path == "/last":
            body = json.dumps(self._last_turn()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()

    def _last_turn(self):
        """Newest complete MJ-1 transcript (has a fusion image), for auto-replay."""
        try:
            files = sorted((f for f in os.listdir(TRANSCRIPTS) if f.startswith("turn_") and f.endswith(".jsonl")),
                           reverse=True)
        except FileNotFoundError:
            return {"events": []}
        for fn in files:
            try:
                lines = [json.loads(x) for x in open(os.path.join(TRANSCRIPTS, fn)) if x.strip()]
            except Exception:
                continue
            has_img = any(e.get("event") == "image" for e in lines)
            is_mj1 = any(e.get("event") == "turn_mj1" for e in lines)
            if is_mj1 and has_img:
                return {"file": fn, "events": lines}
        # fall back to any complete turn with an image
        for fn in files:
            try:
                lines = [json.loads(x) for x in open(os.path.join(TRANSCRIPTS, fn)) if x.strip()]
            except Exception:
                continue
            if any(e.get("event") == "image" for e in lines):
                return {"file": fn, "events": lines}
        # fresh clone: fall back to the committed fixture transcript
        fx = os.path.join(HERE, "fixture", "last_mj1_turn.jsonl")
        if os.path.exists(fx):
            try:
                lines = [json.loads(x) for x in open(fx) if x.strip()]
                return {"file": "fixture", "events": lines}
            except Exception:
                pass
        return {"events": []}

    def _approve(self):
        """Release the design that is open in Fusion: export the whole design to STEP via the
        Fusion API and write a release record next to it. Returns {ok, step, record, kb}."""
        rel_dir = os.path.join(os.path.dirname(TRANSCRIPTS), "releases")
        os.makedirs(rel_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        code = f'''
import adsk.core, adsk.fusion, json, os
app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
name = app.activeDocument.name.split(" ")[0].rstrip("*")
path = os.path.join({rel_dir!r}, name + "_" + {stamp!r} + ".step")
em = des.exportManager
em.execute(em.createSTEPExportOptions(path, des.rootComponent))
json.dumps({{"design": name, "step": path, "bytes": os.path.getsize(path) if os.path.exists(path) else 0}})
'''
        try:
            res = fusion._exec("import json\n" + code, 120.0)
            info = json.loads(res) if isinstance(res, str) else res
        except Exception as e:
            return {"ok": False, "error": str(e)[:300]}
        # Fusion finishes writing STEP after execute() returns; wait for real B-rep entities.
        step = info.get("step")
        solids = 0
        for _ in range(60):
            if step and os.path.exists(step):
                with open(step, errors="ignore") as f:
                    txt = f.read()
                solids = txt.count("MANIFOLD_SOLID_BREP")
                if solids and txt.rstrip().endswith("END-ISO-10303-21;"):
                    break
            time.sleep(0.5)
        info["bytes"] = os.path.getsize(step) if step and os.path.exists(step) else 0
        info["solids"] = solids
        if not solids:
            # Fusion wrote an empty STEP (the open MJ1 doc is an assembly of imported references).
            # Release the build's own STEP outputs instead, and say so.
            src = "/Users/aayu/Workspace/developer/mj1/cad/out/kc/OML_master.step"
            if os.path.exists(src):
                import shutil
                dst = os.path.join(rel_dir, f"MJ1_OML_{stamp}.step")
                shutil.copyfile(src, dst)
                with open(dst, errors="ignore") as f:
                    info["solids"] = f.read().count("MANIFOLD_SOLID_BREP")
                info.update(step=dst, bytes=os.path.getsize(dst), source_step=src)
        record = dict(info, approved_at=time.strftime("%Y-%m-%d %H:%M:%S"), source="FORGE Studio")
        rec_path = os.path.join(rel_dir, f"{info.get('design', 'design')}_{stamp}.json")
        with open(rec_path, "w") as f:
            json.dump(record, f, indent=2)
        return {"ok": bool(info.get("solids")), "design": info.get("design"), "step": info.get("step"),
                "record": rec_path, "kb": round((info.get("bytes") or 0) / 1024), "solids": info.get("solids")}

    def do_POST(self):
        if self.path.split("?")[0] == "/approve":
            body = json.dumps(self._approve()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/sq2/fusion":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            try:
                res = sq2_to_fusion(req.get("groups", []), bool(req.get("snap")))
            except Exception as e:
                res = {"error": str(e)[:300]}
            body = json.dumps(res).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.split("?")[0] == "/sq2/edit":
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            body = json.dumps(sq2_edit(req.get("message", ""), req.get("code", ""), req.get("error"))).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        q = queue.Queue()
        th = threading.Thread(target=run_turn, args=(goal, q), daemon=True)
        th.start()
        # record this turn so the panel can auto-replay the last one on next launch
        tpath = os.path.join(TRANSCRIPTS, f"turn_{int(time.time())}.jsonl")
        tf = open(tpath, "w")
        tf.write(json.dumps({"event": "goal", "message": goal}) + "\n")
        while True:
            item = q.get()
            if item is None:
                break
            try:
                tf.write(json.dumps(item) + "\n")
            except Exception:
                pass
            try:
                self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break
        try:
            tf.close()
        except Exception:
            pass
        try:
            self.wfile.write(b'data: {"event": "end"}\n\n')
            self.wfile.flush()
        except Exception:
            pass
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
