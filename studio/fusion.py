"""Live Fusion 360 bridge for FORGE Studio.

Everything here talks to the Fusion360LiveMCP add-in on localhost:9876 (the same
newline-delimited JSON socket speed-quad uses). We never render 3D ourselves:
Fusion owns the geometry and the viewport. We send it the exact referee solid as
STEP, assign aluminium, verify the mass it reports against the physics referee,
and pull back a viewport PNG.

Why STEP import and not hand-built sketches: forge.blocks.build already produces
the precise solid the CalculiX referee meshed and signed off (plate, arm, gusset
triangle, bolt + motor + lightening holes). Re-drawing that by hand through the
sketch API would risk a part that is visually close but not the verified one, so
the mass check would be meaningless. Importing the referee's own STEP guarantees
what appears in Fusion is the part physics passed. We say so in the chat.
"""
import json
import os
import socket
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST, PORT = "localhost", 9876

# Fusion's add-in is single-threaded: every command runs on the one UI thread.
# Serialize ALL our calls through this lock so two turns (or a capture mid-build)
# never collide and trip "main thread busy". One process, one lock, one caller.
_FUSION_LOCK = threading.Lock()

# referee density for al6061 (g/mm3); mirrors referee.MATERIALS["al6061"]["rho"]
RHO = {"al6061": 2.70e-3, "petg": 1.27e-3}


class FusionError(RuntimeError):
    pass


def call(cmd, params=None, timeout=90.0):
    """One newline-delimited JSON round-trip to the add-in, serialized + retried."""
    params = dict(params or {})
    last = None
    with _FUSION_LOCK:
        for attempt in range(3):
            try:
                s = socket.create_connection((HOST, PORT), timeout=timeout + 15)
            except OSError as e:
                last = FusionError(f"Fusion add-in not reachable on {HOST}:{PORT} ({e})")
                time.sleep(1.0 + attempt)
                continue
            try:
                s.sendall((json.dumps({"type": cmd, "params": params}) + "\n").encode())
                buf = b""
                while not buf.endswith(b"\n"):
                    chunk = s.recv(1 << 20)
                    if not chunk:
                        break
                    buf += chunk
            finally:
                s.close()
            if not buf:
                last = FusionError(f"empty reply from Fusion for {cmd}")
                time.sleep(1.0 + attempt)
                continue
            r = json.loads(buf.decode())
            # a busy main thread is transient: back off and retry the same command
            if isinstance(r, dict) and r.get("error_kind") in ("TIMEOUT", "BUSY"):
                last = FusionError(f"Fusion busy on {cmd}: {r.get('message', '')[:120]}")
                time.sleep(1.5 + attempt)
                continue
            return r
    raise last or FusionError(f"Fusion call {cmd} failed")


def ping():
    try:
        r = call("ping", timeout=10)
        return r.get("status") == "success" or r.get("result") is not None
    except Exception:
        return False


def _exec(code, timeout=90.0):
    """Run python inside Fusion, return its `result` value or raise."""
    r = call("execute_code", {"code": code, "timeout_s": timeout}, timeout)
    if not isinstance(r, dict) or r.get("status") != "success":
        raise FusionError(f"execute_code failed: {json.dumps(r)[:400]}")
    res = r.get("result")
    if isinstance(res, dict) and res.get("executed"):
        return res.get("result")
    return res


def build_step(params, material="al6061"):
    """forge.blocks.build(params) -> STEP file on disk. Returns (path, mass_g)."""
    os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from forge import blocks
    import cadquery as cq

    pc = blocks.clamp(params)
    solid = blocks.build(pc)
    if solid is None or not solid.isValid() or solid.Volume() <= 1:
        raise FusionError("blocks.build produced an invalid solid")
    mass_g = round(solid.Volume() * RHO.get(material, RHO["al6061"]), 2)
    fd, path = tempfile.mkstemp(suffix=".step", prefix="forge_part_")
    os.close(fd)
    cq.exporters.export(cq.Workplane().add(solid), path)
    return path, mass_g, pc


# Fusion-side script. Imports the STEP into a fresh component, assigns an
# aluminium appearance + physical material (best effort over a few known names),
# fits the view, and returns volume/mass so we can check parity with the referee.
_BUILD_SCRIPT = r'''
import adsk.core, adsk.fusion, traceback
_step = {step!r}
_name = {name!r}
app = adsk.core.Application.get()

# Open a dedicated FORGE part document so the real SQ-2 assembly stays pristine.
# Reuse the FORGE doc across builds if it's already open; otherwise make one.
doc = None
for i in range(app.documents.count):
    d = app.documents.item(i)
    if d.name.startswith("FORGE"):
        doc = d; doc.activate(); break
if doc is None:
    doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent

# fresh named component so repeated builds don't pile up
occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
comp = occ.component
comp.name = _name

imp = app.importManager
opts = imp.createSTEPImportOptions(_step)
opts.isViewFit = False
imp.importToTarget(opts, comp)

# collect the imported bodies (they land in the new component)
bodies = [comp.bRepBodies.item(i) for i in range(comp.bRepBodies.count)]
for occ2 in comp.allOccurrences:
    for i in range(occ2.component.bRepBodies.count):
        bodies.append(occ2.component.bRepBodies.item(i))

# assign aluminium material + appearance (best effort across library names)
assigned_mat = None
try:
    libs = app.materialLibraries
    want = ["Aluminum 6061", "Aluminum 6061-T6", "Aluminum"]
    alum = None
    for li in range(libs.count):
        lib = libs.item(li)
        for nm in want:
            m = lib.materials.itemByName(nm)
            if m:
                alum = m; assigned_mat = nm; break
        if alum: break
    if alum:
        for b in bodies:
            try: b.material = alum
            except Exception: pass
except Exception:
    pass

assigned_app = None
try:
    libs = app.materialLibraries
    wantA = ["Aluminum - Satin", "Aluminum - Polished", "Aluminum (Flat)", "Aluminum"]
    appe = None
    for li in range(libs.count):
        lib = libs.item(li)
        try: coll = lib.appearances
        except Exception: continue
        for nm in wantA:
            a = coll.itemByName(nm)
            if a:
                appe = a; assigned_app = nm; break
        if appe: break
    if appe:
        for b in bodies:
            try: b.appearance = appe
            except Exception: pass
except Exception:
    pass

# physical properties (volume is geometry-only, independent of material)
vol_cm3 = 0.0
try:
    for b in bodies:
        pp = b.getPhysicalProperties(adsk.fusion.CalculationAccuracy.HighCalculationAccuracy)
        vol_cm3 += pp.volume
except Exception:
    pass

vp = app.activeViewport
try: vp.fit()
except Exception: pass

json.dumps({{
    "component": comp.name,
    "bodies": len(bodies),
    "volume_cm3": round(vol_cm3, 4),
    "material": assigned_mat,
    "appearance": assigned_app,
}})
'''


def fusion_build(params, task_id="part", material="al6061", referee_mass_g=None):
    """Build the winning bracket live in Fusion 360. Returns a result dict.

    Steps: cadquery STEP -> import into a new component "FORGE <task>" ->
    aluminium material -> fit -> read Fusion's own volume -> mass delta vs the
    referee -> iso viewport PNG (base64).
    """
    step_path, mass_g, pc = build_step(params, material)
    comp_name = f"FORGE {task_id}"
    code = "import json\n" + _BUILD_SCRIPT.format(step=step_path, name=comp_name)
    try:
        raw = _exec(code, timeout=120.0)
    finally:
        try:
            os.remove(step_path)
        except Exception:
            pass
    info = json.loads(raw) if isinstance(raw, str) else (raw or {})

    # Fusion's volume (cm3) -> mass with the referee density, so the number we
    # show is the one the referee signed off, cross-checked by Fusion geometry.
    vol_cm3 = float(info.get("volume_cm3") or 0.0)
    fusion_mass_g = round(vol_cm3 * 1000.0 * RHO.get(material, RHO["al6061"]), 2)
    delta_g = round(fusion_mass_g - mass_g, 2) if vol_cm3 else None
    delta_pct = round(100.0 * delta_g / mass_g, 2) if (delta_g is not None and mass_g) else None

    png = render_png(view="iso")
    return dict(
        component=info.get("component", comp_name),
        bodies=info.get("bodies"),
        material=info.get("material"),
        appearance=info.get("appearance"),
        cadquery_mass_g=mass_g,
        fusion_mass_g=fusion_mass_g,
        referee_mass_g=referee_mass_g,
        mass_delta_g=delta_g,
        mass_delta_pct=delta_pct,
        params=pc,
        image_base64=png,
        method="STEP import of the referee-verified solid",
    )


def render_png(view="iso", width=1024, height=768):
    """Active Fusion viewport -> base64 PNG string (no data: prefix)."""
    try:
        r = call("render_view", {"view": view, "width": width, "height": height, "fit": True}, 90.0)
    except Exception as e:
        raise FusionError(f"render_view failed: {e}")
    res = r.get("result") if isinstance(r, dict) else None
    if isinstance(res, dict) and res.get("image_base64"):
        return res["image_base64"]
    # some bridge versions nest it under execute-style result
    if isinstance(r, dict) and r.get("image_base64"):
        return r["image_base64"]
    raise FusionError(f"no image in render_view reply: {json.dumps(r)[:300]}")


def scene_info():
    r = call("get_scene_info", {}, 60.0)
    return r.get("result") if isinstance(r, dict) else r


def fusion_open_sq2():
    """Show whatever assembly is open (the real SQ-2) and capture it."""
    info = scene_info()
    name = info.get("design_name") if isinstance(info, dict) else None
    bodies = len(info.get("bodies", [])) if isinstance(info, dict) else None
    png = render_png(view="iso")
    return dict(design_name=name, bodies=bodies, image_base64=png)


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        print("ping:", ping())
        gp = {"t_plate": 3, "t_arm": 5, "plate_h": 50, "width": 30, "arm_len": 90,
              "gusset": 4, "gusset_len": 40, "gusset_h": 30, "lighten_n": 2, "lighten_d": 6}
        out = fusion_build(gp, task_id="br02", referee_mass_g=None)
        out2 = dict(out); out2["image_base64"] = f"<{len(out['image_base64'])} b64 chars>"
        print(json.dumps(out2, indent=2))
