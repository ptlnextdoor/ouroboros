"""Referee: independent physics the designer agents cannot see or influence.

STEP -> gmsh 2nd-order tets -> CalculiX static solve, once per load case -> verdict.
Load cases come from the task spec (visible) plus referee/hidden/<task>.json (hidden, referee-only).
Loads are spread over the motor-hole land on the arm top. Wall bolts: plate back face (x=0) fixed.
No LLM in here. Failure modes from our own history are explicit FAILs, never skips.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
import numpy as np
import cadquery as cq

BIN = os.environ.get("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")
GMSH, CCX = os.path.join(BIN, "gmsh"), os.path.join(BIN, "ccx")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIDDEN = os.path.join(ROOT, "referee", "hidden")

MATERIALS = {  # E MPa, nu, density g/mm3, yield MPa
    "al6061": dict(E=68900.0, nu=0.33, rho=2.70e-3, sy=276.0, name="Al 6061-T6"),
    "petg": dict(E=2100.0, nu=0.38, rho=1.27e-3, sy=50.0, name="PETG (printed)"),
}


def _mesh(step, d, clmax):
    inp = os.path.join(d, "m.inp")
    r = subprocess.run([GMSH, step, "-3", "-order", "2", "-clmax", str(clmax), "-format", "inp", "-o", inp],
                       capture_output=True, text=True, timeout=120)
    if r.returncode or not os.path.exists(inp):
        raise RuntimeError("gmsh failed: " + (r.stderr or r.stdout)[-300:])
    s = open(inp).read()
    m = re.search(r"\*NODE\n(.*?)\n\*", s, re.S)
    nodes = {}
    for l in m.group(1).splitlines():
        p = l.split(",")
        nodes[int(p[0])] = [float(x) for x in p[1:4]]
    els = []
    for blk in re.finditer(r"\*ELEMENT, type=C3D10, ELSET=\w+\n(.*?)(?=\n\*|\Z)", s, re.S):
        els += [[int(x) for x in l.split(",")] for l in blk.group(1).splitlines() if l.strip()]
    if not els:
        raise RuntimeError("gmsh produced no tetrahedra")
    return nodes, els


def _solve(nodes, els, fix, load_nodes, F, mat, d):
    with open(os.path.join(d, "job.inp"), "w") as f:
        f.write("*NODE\n" + "".join(f"{i},{x},{y},{z}\n" for i, (x, y, z) in nodes.items()))
        f.write("*ELEMENT,TYPE=C3D10,ELSET=EALL\n" + "".join(",".join(map(str, e)) + "\n" for e in els))
        f.write("*NSET,NSET=FIX\n" + "".join(f"{i},\n" for i in fix))
        f.write(f"*MATERIAL,NAME=M\n*ELASTIC\n{mat['E']},{mat['nu']}\n*SOLID SECTION,ELSET=EALL,MATERIAL=M\n")
        f.write("*BOUNDARY\nFIX,1,3\n*STEP\n*STATIC\n*CLOAD\n")
        for i in load_nodes:
            for k in range(3):
                if F[k]:
                    f.write(f"{i},{k + 1},{F[k] / len(load_nodes)}\n")
        f.write("*NODE FILE\nU\n*EL FILE\nS\n*END STEP\n")
    r = subprocess.run([CCX, "job"], cwd=d, capture_output=True, text=True, timeout=300)
    frd = os.path.join(d, "job.frd")
    if r.returncode or not os.path.exists(frd) or "Job finished" not in r.stdout:
        raise RuntimeError("ccx failed: " + r.stdout[-300:])
    txt = open(frd).read()

    def block(name):
        b = txt.split(f" -4  {name}")[1].split(" -3")[0]
        rows = {}
        for l in b.splitlines():
            if l.startswith(" -1"):
                nid = int(l[3:13]); vals = [float(l[13 + 12 * k:25 + 12 * k]) for k in range((len(l) - 13) // 12)]
                rows[nid] = vals
        return rows
    U = block("DISP"); S = block("STRESS")
    umag = max(np.linalg.norm(v[:3]) for v in U.values())
    vm = []
    for sxx, syy, szz, sxy, syz, szx in (v[:6] for v in S.values()):
        vm.append(np.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2) + 3 * (sxy ** 2 + syz ** 2 + szx ** 2)))
    vm = np.array(vm)
    return dict(sigma_max=float(np.percentile(vm, 99.5)), sigma_peak=float(vm.max()), defl=float(umag),
                ux_tip=float(np.mean([U[i][0] for i in load_nodes])), uy_tip=float(np.mean([U[i][1] for i in load_nodes])),
                uz_tip=float(np.mean([U[i][2] for i in load_nodes])))


def evaluate(solid, motor_xy, arm_top_z, cases, material="al6061", fos=1.5, defl_limit=None, mass_limit=None,
             clmax=None, workdir=None, claim=None):
    """cases: [{name, F:[Fx,Fy,Fz] N, hidden:bool}]. Returns verdict dict."""
    mat = MATERIALS[material]
    t0 = time.time()
    v = dict(checks=[], cases=[], material=mat["name"], fos=fos, ok=False, reason="")
    d = workdir or tempfile.mkdtemp(prefix="ref_")
    os.makedirs(d, exist_ok=True)
    try:
        if solid is None or not solid.isValid() or solid.Volume() <= 1:
            raise RuntimeError("invalid geometry (not a closed positive-volume solid)")
        step = os.path.join(d, "part.step")
        cq.exporters.export(cq.Workplane().add(solid), step)
        v["step_sha"] = hashlib.sha256(open(step, "rb").read()).hexdigest()[:12]
        bb = solid.BoundingBox()
        mass = solid.Volume() * mat["rho"]
        v["mass_g"] = round(mass, 2)
        if mass_limit:
            v["checks"].append(dict(name="mass", limit=f"<= {mass_limit} g", measured=round(mass, 1), ok=mass <= mass_limit))
        nodes, els = _mesh(step, d, clmax or max(1.0, min(bb.xlen, bb.ylen, bb.zlen) / 2.5))
        ids = np.array(list(nodes)); X = np.array([nodes[i] for i in ids])
        fix = ids[np.abs(X[:, 0] - bb.xmin) < 1e-6].tolist()
        mx, my = motor_xy
        r = np.hypot(X[:, 0] - mx, X[:, 1] - my)
        land = ids[(np.abs(X[:, 2] - arm_top_z) < 1e-4) & (r > 3.2) & (r < 6.5)].tolist()
        if len(fix) < 3 or len(land) < 3:
            raise RuntimeError(f"cannot apply BCs (fixed nodes {len(fix)}, load nodes {len(land)}): motor land or wall face missing")
        v["mesh"] = dict(nodes=len(nodes), tets=len(els))
        allow = mat["sy"] / fos
        for c in cases:
            cd = os.path.join(d, c["name"]); os.makedirs(cd, exist_ok=True)
            res = _solve(nodes, els, fix, land, c["F"], mat, cd)
            # sanity: response must oppose nothing silly; symmetric part + load in xz-plane -> tiny uy
            sym_ok = True
            if abs(c["F"][1]) < 1e-9 and abs(my) < 1e-9:
                sym_ok = abs(res["uy_tip"]) <= 0.05 * max(res["defl"], 1e-9) + 1e-6
            work_ok = (res["ux_tip"] * c["F"][0] + res["uy_tip"] * c["F"][1] + res["uz_tip"] * c["F"][2]) > 0
            ok = res["sigma_max"] <= allow and sym_ok and work_ok
            row = dict(name=c["name"], hidden=bool(c.get("hidden")), F=c["F"], sigma_MPa=round(res["sigma_max"], 1),
                       allow_MPa=round(allow, 1), defl_mm=round(res["defl"], 4), sym_ok=sym_ok, work_ok=work_ok, ok=ok)
            if defl_limit and not c.get("hidden"):
                row["defl_ok"] = res["defl"] <= defl_limit
                row["ok"] = ok and row["defl_ok"]
            v["cases"].append(row)
        vis = [c for c in v["cases"] if not c["hidden"]]
        hid = [c for c in v["cases"] if c["hidden"]]
        v["checks"].append(dict(name="stress, visible loads", limit=f"<= {allow:.0f} MPa", measured=max((c["sigma_MPa"] for c in vis), default=0), ok=all(c["ok"] for c in vis)))
        if hid:
            v["checks"].append(dict(name="stress, HIDDEN loads", limit=f"<= {allow:.0f} MPa", measured=max(c["sigma_MPa"] for c in hid), ok=all(c["ok"] for c in hid)))
        if claim and vis:
            truth = vis[0]["sigma_MPa"]
            gap = abs(claim.get("sigma_MPa", 0) - truth) / max(truth, 1e-9)
            v["parity_gap"] = round(gap, 3)
            v["checks"].append(dict(name="parity (agent claim vs referee)", limit="<= 25 %", measured=f"{gap * 100:.0f} %", ok=gap <= 0.25))
        v["ok"] = all(ch["ok"] for ch in v["checks"])
        v["reason"] = "PASS" if v["ok"] else "; ".join(ch["name"] for ch in v["checks"] if not ch["ok"])
    except Exception as e:  # mesh/solve/geometry failure is a verdict, never a skip
        v["ok"] = False; v["reason"] = f"FAIL: {e}"[:400]
    v["seconds"] = round(time.time() - t0, 2)
    if not workdir:
        shutil.rmtree(d, ignore_errors=True)
    return v


def hidden_cases(task_id):
    p = os.path.join(HIDDEN, f"{task_id}.json")
    return [dict(c, hidden=True) for c in json.load(open(p))] if os.path.exists(p) else []


def selftest():
    """Cantilever 60x6x6 Al, tip load 100 N: CalculiX tip deflection vs PL^3/3EI."""
    bar = cq.Solid.makeBox(60, 6, 6, cq.Vector(0, -3, 0))
    d = tempfile.mkdtemp(prefix="ref_selftest_")
    step = os.path.join(d, "bar.step"); cq.exporters.export(cq.Workplane().add(bar), step)
    nodes, els = _mesh(step, d, 1.5)
    ids = np.array(list(nodes)); X = np.array([nodes[i] for i in ids])
    fix = ids[X[:, 0] < 1e-6].tolist(); tip = ids[X[:, 0] > 60 - 1e-6].tolist()
    res = _solve(nodes, els, fix, tip, [0, 0, -100.0], MATERIALS["al6061"], d)
    theory = 100 * 60 ** 3 / (3 * MATERIALS["al6061"]["E"] * 6 ** 4 / 12)
    err = abs(abs(res["uz_tip"]) - theory) / theory
    shutil.rmtree(d, ignore_errors=True)
    print(f"referee selftest: ccx tip {abs(res['uz_tip']):.4f} mm vs beam theory {theory:.4f} mm, err {err * 100:.2f} %")
    assert err < 0.03, "referee physics disagrees with beam theory"
    return err


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
