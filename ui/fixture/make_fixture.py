"""Build a realistic demo fixture for the UI using the real blocks + referee.

Run:  /opt/miniconda3/bin/python ui/fixture/make_fixture.py
Writes ui/fixture/demo/events.jsonl, STLs, and ui/fixture/demo/playbook/.
Event contract mirrors runs/<run>/events.jsonl (see task brief).
"""
import json, os, sys, time, random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import cadquery as cq
from forge import blocks
from referee import referee as R

OUT = os.path.join(ROOT, "ui", "fixture", "demo")
TASK = "bracket_2kg_80mm"
os.makedirs(os.path.join(OUT, TASK), exist_ok=True)
os.makedirs(os.path.join(OUT, "playbook"), exist_ok=True)
random.seed(7)

GOAL = "Wall bracket for a 2 kg motor, 80 mm off the wall, Al 6061, under 40 g, FoS 1.5"
CASES = [dict(name="motor weight x3g", F=[0, 0, -60.0], hidden=False),
         dict(name="side kick", F=[0, 300.0, 0], hidden=True),
         dict(name="belt pull", F=[80.0, 0, -40.0], hidden=True)]
MASS_LIMIT = 40.0

# iteration 0: naive designs; iteration 1: after critic (gusset, wider)
DESIGNS = [
    [dict(t_plate=4, t_arm=4, plate_h=45, width=12, arm_len=90, gusset=0, lighten_n=0),            # narrow: passes visible, fails hidden side kick
     dict(t_plate=4, t_arm=4, plate_h=45, width=20, arm_len=90, gusset=0, lighten_n=3, lighten_d=8),  # holes, fails
     dict(t_plate=5, t_arm=5, plate_h=50, width=24, arm_len=90, gusset=0, lighten_n=0),            # passes visible, heavy?
     dict(t_plate=2.5, t_arm=2.5, plate_h=40, width=30, arm_len=90, gusset=0, lighten_n=0)],       # thin wide
    [dict(t_plate=3, t_arm=3, plate_h=45, width=22, arm_len=90, gusset=3, gusset_len=45, gusset_h=30, lighten_n=0),
     dict(t_plate=3.5, t_arm=3.5, plate_h=50, width=20, arm_len=90, gusset=4, gusset_len=50, gusset_h=35, lighten_n=2, lighten_d=6),
     dict(t_plate=4, t_arm=3, plate_h=50, width=26, arm_len=90, gusset=3, gusset_len=55, gusset_h=38, lighten_n=0),
     dict(t_plate=3, t_arm=4, plate_h=45, width=24, arm_len=90, gusset=5, gusset_len=40, gusset_h=30, lighten_n=0)],
]

events = []
t = time.time()
usd = 0.0


def emit(kind, payload, dt=1.0):
    global t
    t += dt
    events.append(dict(ts=round(t, 3), kind=kind, payload=payload))


def cost(call, model="nvidia/nemotron-3.5-lightning-30b-a3b", cached=0):
    global usd
    usd += call
    emit("cost", dict(usd_total=round(usd, 4), usd_call=round(call, 4), model=model, cached_tokens=cached), 0.2)


emit("spec", dict(task=TASK, goal=GOAL, material="al6061", fos=1.5, mass_limit_g=MASS_LIMIT,
                  checks=["geometry valid + meshes", "mass <= 40 g (from STEP)", "stress <= 184 MPa on visible loads",
                          "stress <= 184 MPa on HIDDEN loads", "parity gap <= 25 %"],
                  visible_cases=[c for c in CASES if not c["hidden"]]), 0.5)
cost(0.0041, "nvidia/Nemotron-3-Super-120B-A12B")

CRITIC = {
    (0, 0): "Visible load passed, but the HIDDEN side kick pushed sigma past allowable. 12 mm width gives almost no lateral section modulus. Hypothesis: lateral bending about z is the governing mode, not the visible vertical load. Change: width >= 22 mm or add a gusset to stiffen the root.",
    (0, 1): "Stress passed every case, but the agent's own claim was 38 % below the referee: the voxel sim smeared the 8 mm lightening holes. Parity gate failed, so this design is not trusted. Change: no holes within 30 mm of the wall, and calibrate the fast sim on a holed arm.",
    (0, 2): "Every load case passes, but 42 g blows the 40 g cap. 5 mm plate and arm are overbuilt for the visible load. Change: drop to 3 mm and put the material in a gusset at the root instead.",
    (1, 0): "All cases pass with margin. Mass 31 g under the 40 g cap. Gusset carries the root moment; parity within 10 %. Keep.",
}

# referee auto clmax = min(bbox)/2.5 is coarser than thin walls -> ccx jacobian errors; pass explicit
CL = lambda p: 1.3 if p["width"] <= 12 else max(0.8, min(p["t_plate"], p["t_arm"]) / 2)
BIAS = {(0, 0): 0.91, (0, 1): 0.62, (0, 2): 0.96, (0, 3): 0.88, (1, 0): 1.05, (1, 1): 0.95, (1, 2): 0.97, (1, 3): 0.9}
best = None
for it, designs in enumerate(DESIGNS):
    for k, p in enumerate(designs):
        p = blocks.clamp(p)
        emit("design", dict(task=TASK, iter=it, k=k, params=p, agent=f"designer-{k}"), 0.6)
        cost(0.0009 + random.random() * 0.0006, cached=random.choice([0, 1800, 2400]))
        solid = blocks.build(p)
        stl_rel = f"ui/fixture/demo/{TASK}/{it}_{k}.stl"
        # NOTE: export STL *after* evaluate. STL export tessellates the solid and BoundingBox() then
        # carries the mesh deflection margin (xmin ~ -8e-4), which makes the referee find 0 fixed nodes.
        # fake agent claim: voxel sim is optimistic by 5..40 %
        tmp = R.evaluate(solid, blocks.motor_xy(p), p["plate_h"], [c for c in CASES if not c["hidden"]], fos=1.5, clmax=CL(p))
        truth = tmp["cases"][0]["sigma_MPa"] if tmp["cases"] else 100.0
        bias = BIAS.get((it, k), 0.93)
        claim = dict(sigma_MPa=round(truth * bias, 1), mass_g=round(tmp.get("mass_g", 0) * random.choice([0.98, 1.0, 1.02]), 1))
        v = R.evaluate(solid, blocks.motor_xy(p), p["plate_h"], CASES, fos=1.5, mass_limit=MASS_LIMIT, claim=claim, clmax=CL(p))
        v.update(task=TASK, iter=it, k=k, stl=stl_rel, params=p, claim=claim)
        cq.exporters.export(cq.Workplane().add(solid), os.path.join(ROOT, stl_rel))
        emit("verdict", v, 1.8)
        print(f"iter {it} k {k}: ok={v['ok']} reason={v['reason']} mass={v.get('mass_g')} gap={v.get('parity_gap')}")
        if v["ok"] and (best is None or v["mass_g"] < best["mass_g"]):
            best = v
        if (it, k) in CRITIC:
            emit("critic", dict(task=TASK, iter=it, k=k, ok=v["ok"], text=CRITIC[(it, k)]), 1.2)
            cost(0.0062, "deepseek-ai/DeepSeek-V4-Pro")
    if it == 0:
        pb_old = "# Playbook v0\n\n- Choose t_arm from bending stress at the root under the visible load.\n- Use lightening holes to hit the mass target.\n"
        pb_new = ("# Playbook v1\n\n- Choose t_arm from bending stress at the root under the visible load.\n"
                  "+ Any cantilever > 50 mm gets a gusset (thickness ~ t_arm, length ~ half the arm).\n"
                  "+ Assume an unlisted side load of ~0.75x the vertical load. Width >= 20 mm.\n"
                  "- Lightening holes only beyond 30 mm from the wall, d <= width/3.\n")
        open(os.path.join(OUT, "playbook", "v0.md"), "w").write(pb_old)
        open(os.path.join(OUT, "playbook", "v1.md"), "w").write(pb_new)
        emit("playbook", dict(version=1, text=pb_new, path="ui/fixture/demo/playbook/v1.md"), 1.0)
        cost(0.0088, "deepseek-ai/DeepSeek-V4-Pro")
        diff = ("--- v0\n+++ v1\n@@\n Choose t_arm from bending stress at the root under the visible load.\n"
                "-Use lightening holes to hit the mass target.\n"
                "+Any cantilever > 50 mm gets a gusset (thickness ~ t_arm, length ~ half the arm).\n"
                "+Assume an unlisted side load of ~0.75x the vertical load. Width >= 20 mm.\n"
                "+Lightening holes only beyond 30 mm from the wall, d <= width/3.\n")
        emit("gate", dict(version=1, dev_score_old=0.25, dev_score_new=0.75, kept=True, diff=diff,
                          heldout=dict(v0=0.2, vN=0.7, n=10)), 2.5)

# a rejected playbook edit after iteration 1
diff2 = "--- v1\n+++ v2 (proposed)\n@@\n-Width >= 20 mm.\n+Width >= 40 mm always.\n"
emit("playbook", dict(version=2, text="(proposed) width >= 40 mm always", path=None), 1.0)
cost(0.0071, "deepseek-ai/DeepSeek-V4-Pro")
emit("gate", dict(version=2, dev_score_old=0.75, dev_score_new=0.5, kept=False, diff=diff2,
                  heldout=dict(v0=0.2, vN=0.7, n=10)), 2.0)

hist = [dict(version=1, kept=True, dev_score_old=0.25, dev_score_new=0.75),
        dict(version=2, kept=False, dev_score_old=0.75, dev_score_new=0.5)]
with open(os.path.join(OUT, "playbook", "history.jsonl"), "w") as f:
    for h in hist:
        f.write(json.dumps(h) + "\n")
with open(os.path.join(OUT, "events.jsonl"), "w") as f:
    for e in events:
        f.write(json.dumps(e) + "\n")
print(f"wrote {len(events)} events to {OUT}/events.jsonl; best={best and (best['iter'], best['k'], best['mass_g'])}")
