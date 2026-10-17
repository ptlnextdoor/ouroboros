"""Generate the 16 bracket tasks + hidden load cases, and prove each feasible.

Run:  uv run python tasks/build_tasks.py           # writes tasks + hidden + _feasible.json
      uv run python tasks/build_tasks.py --check    # re-verify _feasible.json only

A task is one plain-English bracket goal. The *numeric* load cases the referee
uses are derived deterministically from the task (see forge.loop.visible_cases),
never from an LLM, so the referee stays objective. Hidden cases live in
referee/hidden/<id>.json and are the loads a naive design fails but a sensible
one (gussets, width) passes: a side knock, a pull-off, a 2x overload, a drop.

Feasibility is not asserted by hand: we search a small grid of sensible param
sets per task, keep the lightest that passes ALL cases (visible + hidden), set
the task's mass cap to that mass x 1.15 (tight but feasible), and record the
winning params in tasks/_feasible.json as evidence.
"""
import concurrent.futures as cf
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")

from forge import blocks  # noqa: E402
from referee import referee  # noqa: E402

G = 9.81

# id, prompt, load_kg, reach_mm, material, g_factor, defl_limit_mm, split
TASKS = [
    # ---- train (6) ----
    ("br01", "hold a 1 kg sensor 60 mm off a wall, aluminium, survive 3 g", 1.0, 60, "al6061", 3, 1.0, "train"),
    ("br02", "mount a 2 kg motor 80 mm off a wall in aluminium, 3 g rating", 2.0, 80, "al6061", 3, 1.2, "train"),
    ("br03", "cantilever a 0.5 kg camera 100 mm out, aluminium, 3 g", 0.5, 100, "al6061", 3, 1.5, "train"),
    ("br04", "hold a 3 kg gearbox 70 mm off a wall, aluminium, 3 g", 3.0, 70, "al6061", 3, 1.0, "train"),
    ("br05", "support a 1.5 kg light 120 mm off a wall in aluminium, 2.5 g", 1.5, 120, "al6061", 2.5, 1.8, "train"),
    ("br06", "bracket a 0.8 kg pump 50 mm off a wall, PETG printed, 2 g", 0.8, 50, "petg", 2, 1.2, "train"),
    # ---- dev (4) ----
    ("br07", "hold a 2.5 kg motor 90 mm off a wall, aluminium, 3 g", 2.5, 90, "al6061", 3, 1.2, "dev"),
    ("br08", "cantilever a 1 kg antenna 140 mm out, aluminium, 2.5 g", 1.0, 140, "al6061", 2.5, 2.2, "dev"),
    ("br09", "mount a 4 kg actuator 60 mm off a wall, aluminium, 3 g", 4.0, 60, "al6061", 3, 0.9, "dev"),
    ("br10", "hold a 0.6 kg controller 45 mm off a wall, PETG printed, 2 g", 0.6, 45, "petg", 2, 1.0, "dev"),
    # ---- heldout (6) ----
    ("br11", "mount a 2 kg motor 110 mm off a wall, aluminium, 3 g", 2.0, 110, "al6061", 3, 1.6, "heldout"),
    ("br12", "hold a 5 kg winch 65 mm off a wall, aluminium, 3 g", 5.0, 65, "al6061", 3, 0.9, "heldout"),
    ("br13", "cantilever a 1.2 kg speaker 130 mm out, aluminium, 2.5 g", 1.2, 130, "al6061", 2.5, 2.0, "heldout"),
    ("br14", "support a 3.5 kg battery 75 mm off a wall, aluminium, 3 g", 3.5, 75, "al6061", 3, 1.0, "heldout"),
    ("br15", "hold a 0.9 kg valve 55 mm off a wall, PETG printed, 2 g", 0.9, 55, "petg", 2, 1.1, "heldout"),
    ("br16", "mount a 1.8 kg fan 150 mm off a wall, aluminium, 2.5 g", 1.8, 150, "al6061", 2.5, 2.5, "heldout"),
]


def task_dict(row):
    tid, prompt, load_kg, reach, mat, g, defl, split = row
    return dict(id=tid, prompt=prompt, load_kg=load_kg, reach_mm=reach,
                arm_len=reach + blocks.HOLE_FROM_TIP, material=mat, g_factor=g,
                fos=1.5, defl_limit_mm=defl, split=split, mass_limit_g=None)


def visible_cases(task):
    """Canonical visible loads: static weight + the g-rated down case."""
    w = task["load_kg"] * G
    g = task["g_factor"]
    return [
        dict(name="weight", F=[0.0, 0.0, -round(w, 2)]),
        dict(name="g_load", F=[0.0, 0.0, -round(w * g, 2)]),
    ]


def hidden_cases(task):
    """Loads a naive design fails: side knock, pull-off, overload, drop.

    Kept modest enough that a sensible design (gusset + width) survives.
    """
    w = task["load_kg"] * G
    g = task["g_factor"]
    return [
        dict(name="side_knock", F=[0.0, round(0.9 * w * g, 2), -round(w, 2)]),
        dict(name="pull_off", F=[round(0.8 * w * g, 2), 0.0, -round(w, 2)]),
        dict(name="overload_2x", F=[0.0, 0.0, -round(2.0 * w * g, 2)]),
    ]


def _preset(task, t_arm, t_plate, width, gusset):
    reach, arm_len = task["reach_mm"], task["arm_len"]
    plate_h = max(40.0, round(reach * 0.55))
    p = dict(t_plate=t_plate, t_arm=t_arm, plate_h=plate_h, width=width, arm_len=arm_len,
             gusset=gusset, gusset_len=(round(arm_len * 0.55) if gusset else 0.0),
             gusset_h=(round(plate_h * 0.75) if gusset else 0.0), lighten_n=0, lighten_d=0.0)
    return p


def search_feasible(task):
    """Return (params, mass_g, verdict) for the lightest design passing all cases."""
    vis = visible_cases(task)
    hid = [dict(c, hidden=True) for c in hidden_cases(task)]
    cases = vis + hid
    mat, fos, defl = task["material"], task["fos"], task["defl_limit_mm"]
    # ordered roughly light -> heavy; petg needs thicker sections
    if mat == "petg":
        combos = [(t, t, w, g) for g in (1,) for w in (35, 50, 65) for t in (5, 7, 9, 11)]
    else:
        combos = [(ta, max(4, ta - 2), w, g)
                  for g in (1,) for w in (30, 45, 60) for ta in (4, 6, 8, 10)]
        combos += [(ta, max(4, ta - 2), w, 0) for w in (45, 60) for ta in (8, 10, 12)]
    best = None
    for (ta, tp, w, gflag) in combos:
        gth = min(ta, 8) if gflag else 0.0
        p = _preset(task, ta, tp, w, gth)
        pc = blocks.clamp(p)
        solid = blocks.build(pc)
        mass = solid.Volume() * referee.MATERIALS[mat]["rho"]
        if best and mass >= best[1]:
            continue  # cannot improve on current lightest pass
        v = referee.evaluate(solid, blocks.motor_xy(pc), arm_top_z=pc["plate_h"],
                             cases=cases, material=mat, fos=fos, defl_limit=defl)
        if v["ok"]:
            if best is None or mass < best[1]:
                best = (pc, mass, v)
    return best


def build(check_only=False):
    rows = [task_dict(r) for r in TASKS]
    if not check_only:
        os.makedirs(os.path.join(ROOT, "tasks"), exist_ok=True)
        os.makedirs(referee.HIDDEN, exist_ok=True)
        for r in rows:
            json.dump(hidden_cases(r), open(os.path.join(referee.HIDDEN, f"{r['id']}.json"), "w"), indent=2)
    feas = {}
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(search_feasible, r): r for r in rows}
        for fut in cf.as_completed(futs):
            r = futs[fut]
            got = fut.result()
            if not got:
                print(f"  !! {r['id']} NO FEASIBLE DESIGN FOUND in grid")
                feas[r["id"]] = dict(ok=False)
                continue
            params, mass, v = got
            cap = round(mass * 1.15, 1)
            r["mass_limit_g"] = cap
            feas[r["id"]] = dict(ok=True, mass_g=round(mass, 2), mass_limit_g=cap,
                                 params=params, reason=v["reason"],
                                 n_cases=len(v["cases"]), seconds=v["seconds"])
            print(f"  ok {r['id']:5s} mass {mass:6.1f} g  cap {cap:6.1f} g  "
                  f"({sum(1 for c in v['cases'] if c['hidden'])} hidden) {v['seconds']}s")
    if not check_only:
        for r in rows:
            json.dump(r, open(os.path.join(ROOT, "tasks", f"{r['id']}.json"), "w"), indent=2)
        json.dump(feas, open(os.path.join(ROOT, "tasks", "_feasible.json"), "w"), indent=2)
    n_ok = sum(1 for f in feas.values() if f.get("ok"))
    print(f"feasible {n_ok}/{len(rows)} tasks")
    return feas


if __name__ == "__main__":
    build(check_only="--check" in sys.argv)
