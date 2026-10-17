"""SQ-2 pod-node referee review: the FORGE referee checking a REAL vehicle part.

Takes the machined 7075 pod node from the speed-quad SQ-2 drone
(cad/out/sq2/v3/pod_LD_node_7075.step) and runs it through the SAME referee
pipeline the designer agents are graded by (gmsh 2nd-order tets -> CalculiX
static solve), then compares the FEA peak von Mises against the hand-calc
margin for the governing load case.

We do NOT edit referee/referee.py. We import its internals (_mesh, _solve) and
add a local 7075-T6 material here. No LLM, no fudging: whatever CalculiX says
is the verdict.

Load case (honest, traceable):
  20 g POD-DOWN landing/crash. This is the governing case in the SQ-2 hand
  calc (speed-quad cad/out/sq2/v3/margins.json: "spar root bending, 20 g
  POD-DOWN", MS +0.48 -- the min adopted margin of the whole airframe).
  The pod inertia is F_pod_down = m_pod * 20 g, derived at
  speed-quad/cad/src/sq2_v3_margins.py:116-117
      m_pod = 0.148 + 0.009 + 0.027 + 0.033 + 0.018 + 0.009 + 0.004  # kg
      F_pod_down = m_pod * landing_g * g
  Everything in the pod (motor, spinner, prop, nacelles, fairing) bolts to the
  node; under 20 g pod-down that inertia is reacted by the CFRP spar in the
  node's spar socket. We apply the FULL pod inertia at the motor-mount flange
  (the longest lever to the socket) -> conservative bound on the node, and fix
  the spar-socket bore (spar bonded + 2x M2 set-screw, 25 mm engagement).

BCs (selected by geometry off the STEP, auto-detected, documented in output):
  FIX  : spar-socket bore (cylindrical face R~3.02) -> all 3 DOF (spar grips it)
  LOAD : motor-mount flange (planar face, -x normal) -> F = (0,0,-F_pod_down) N

Run: PY=/opt/miniconda3/bin/python3 FREECAD_BIN=.../bin python3 forge/sq2_review.py
"""
import json, math, os, sys, re, shutil, tempfile
import numpy as np
import cadquery as cq
import OCP.BRepAdaptor as BA

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import referee.referee as referee  # reuse _mesh / _solve, do NOT edit it

STEP = os.environ.get("SQ2_NODE_STEP",
    "/Users/aayu/Workspace/developer/speed-quad/cad/out/sq2/v3/pod_LD_node_7075.step")
OUT = os.path.join(ROOT, "ui", "fixture", "sq2_review")
os.makedirs(OUT, exist_ok=True)

# 7075-T6, local to this file (referee.MATERIALS only has al6061 / petg).
# E 71.7 GPa, nu 0.33, sy 503 MPa (tensile yield, matches speed-quad AL7075_TY).
AL7075 = dict(E=71700.0, nu=0.33, rho=2.81e-3, sy=503.0, name="Al 7075-T6")
FOS = 1.5

# ---- load case, lifted verbatim from sq2_v3_margins.py:116-117 -------------
G = 9.80665
LANDING_G = 20.0
M_POD = 0.148 + 0.009 + 0.027 + 0.033 + 0.018 + 0.009 + 0.004  # kg (motor,spinner,node,nacelles,fairing,prop,spar)
F_POD_DOWN = M_POD * LANDING_G * G                              # N
HANDCALC_GOV = dict(item="spar root bending, 20 g POD-DOWN (pod inertia x arm)",
                    member="CFRP spar (6x4 pultruded)", MS=0.48, sigma_MPa=None,
                    src="speed-quad/cad/out/sq2/v3/margins.json")


def _cyl(face):
    ad = BA.BRepAdaptor_Surface(face.wrapped)
    c = ad.Cylinder()
    ax = c.Axis().Direction(); p = c.Axis().Location()
    return c.Radius(), np.array([ax.X(), ax.Y(), ax.Z()]), np.array([p.X(), p.Y(), p.Z()])


def detect_bcs(solid):
    """Auto-find the motor-mount flange (planar, -x normal, biggest) and the
    spar-socket bore (cylindrical, R in 2.5..3.6, biggest). Returns geometry."""
    flange = None  # (area, x, center_yz)
    socket = None  # (area, R, axis, pt)
    for f in solid.Faces():
        gt = f.geomType()
        c = f.Center()
        if gt == "PLANE":
            n = f.normalAt(c)
            if n.x < -0.9 and (flange is None or f.Area() > flange[0]):
                flange = (f.Area(), c.x, np.array([c.y, c.z]))
        elif gt == "CYLINDER":
            R, ax, pt = _cyl(f)
            if 2.5 < R < 3.6 and (socket is None or f.Area() > socket[0]):
                socket = (f.Area(), R, ax / np.linalg.norm(ax), pt)
    if flange is None or socket is None:
        raise RuntimeError(f"could not detect BCs (flange={flange is not None}, socket={socket is not None})")
    return flange, socket


def main():
    t_sha = __import__("hashlib").sha256(open(STEP, "rb").read()).hexdigest()[:12]
    s = cq.importers.importStep(STEP)
    solid = s.val()
    assert solid.isValid() and solid.Volume() > 1, "bad STEP"
    bb = solid.BoundingBox()
    mass_g = solid.Volume() * AL7075["rho"]
    flange, socket = detect_bcs(solid)
    fa, fx, fyz = flange
    sa, sR, sax, spt = socket

    d = tempfile.mkdtemp(prefix="sq2_node_")
    step = os.path.join(d, "node.step")
    cq.exporters.export(cq.Workplane().add(solid), step)

    # mesh: clmax ~ thinnest structural wall. socket tube wall ~3 mm, flange 3.5 mm,
    # seat ring 2 mm. 1.2 keeps node count well under 80k on this 8 cc part.
    clmax = 1.2
    nodes, els = referee._mesh(step, d, clmax)
    ids = np.array(list(nodes)); X = np.array([nodes[i] for i in ids])
    while len(nodes) > 80000:
        clmax *= 1.25
        nodes, els = referee._mesh(step, d, clmax)
        ids = np.array(list(nodes)); X = np.array([nodes[i] for i in ids])

    # FIX: spar-socket bore. perpendicular distance from each node to the socket
    # axis < R+0.5 -> the bore wall + blind-cap material the spar grips.
    rel = X - spt
    t = rel @ sax
    perp = np.linalg.norm(rel - np.outer(t, sax), axis=1)
    fix = ids[perp < sR + 0.5].tolist()

    # LOAD: motor-mount flange face, radial extent < 12.5 mm about the flange centre.
    rflange = np.hypot(X[:, 1] - fyz[0], X[:, 2] - fyz[1])
    load = ids[(np.abs(X[:, 0] - fx) < 0.5) & (rflange < 12.5)].tolist()
    if len(fix) < 3 or len(load) < 3:
        raise RuntimeError(f"BC node count too low (fix {len(fix)}, load {len(load)})")

    F = [0.0, 0.0, -F_POD_DOWN]  # pod-down = body -z
    res = referee._solve(nodes, els, fix, load, F, AL7075, d)

    # per-node von Mises from the frd that _solve just wrote (for the PNG)
    txt = open(os.path.join(d, "job.frd")).read()

    def block(name):
        b = txt.split(f" -4  {name}")[1].split(" -3")[0]
        rows = {}
        for l in b.splitlines():
            if l.startswith(" -1"):
                nid = int(l[3:13]); vals = [float(l[13 + 12 * k:25 + 12 * k]) for k in range((len(l) - 13) // 12)]
                rows[nid] = vals
        return rows
    U = block("DISP"); S = block("STRESS")
    nid = np.array(sorted(S))
    Xs = np.array([nodes[i] for i in nid])
    vm = np.array([math.sqrt(0.5 * ((sx - sy) ** 2 + (sy - sz) ** 2 + (sz - sx) ** 2)
                             + 3 * (sxy ** 2 + syz ** 2 + szx ** 2))
                   for (sx, sy, sz, sxy, syz, szx) in (S[i][:6] for i in nid)])
    disp = np.array([U.get(i, [0, 0, 0])[:3] for i in nid])

    sigma_fea = res["sigma_max"]           # 99.5-percentile (referee's headline number)
    sigma_peak = res["sigma_peak"]         # absolute max node (concentration)
    allow = AL7075["sy"] / FOS
    ms_fea = AL7075["sy"] / (FOS * sigma_fea) - 1.0
    ms_peak = AL7075["sy"] / (FOS * sigma_peak) - 1.0

    # hand-calc node check: cantilever, socket-tube annulus, arm = flange centroid
    # to socket mid (3D). This is the beam-theory number the FEA is auditing.
    f_centroid = np.array([fx, fyz[0], fyz[1]])
    s_mid = spt + t.mean() * sax  # socket mid along its axis near the cloud
    # better socket mid: midpoint of fixed-node projections
    s_mid = (spt + np.median((X[perp < sR + 0.5] - spt) @ sax) * sax)
    arm = float(np.linalg.norm(f_centroid - s_mid))
    OD, ID = 2 * sa if False else 2 * 6.03, 2 * sR     # socket tube OD~12.06, ID=bore
    OD = 12.06
    I_tube = math.pi / 64 * (OD ** 4 - ID ** 4)
    M = F_POD_DOWN * arm
    sigma_hand = M * (OD / 2) / I_tube
    ms_hand = AL7075["sy"] / (FOS * sigma_hand) - 1.0
    gap = abs(sigma_fea - sigma_hand) / max(sigma_hand, 1e-9)
    kt = sigma_peak / sigma_hand

    # ---- verdict.json in referee.evaluate() shape (checks list) --------------
    checks = [
        dict(name="node von Mises (99.5 pct) vs 7075-T6 yield/FoS",
             limit=f"<= {allow:.0f} MPa", measured=round(sigma_fea, 1), ok=sigma_fea <= allow),
        dict(name="node peak von Mises (concentration) vs yield/FoS",
             limit=f"<= {allow:.0f} MPa", measured=round(sigma_peak, 1), ok=sigma_peak <= allow),
    ]
    verdict = dict(
        part="SQ-2 pod node (pod_LD, 7075-T6, machined)", step_sha=t_sha,
        material=AL7075["name"], fos=FOS, ok=all(c["ok"] for c in checks),
        reason="PASS" if all(c["ok"] for c in checks) else "node over allowable",
        load_case=dict(name="20 g POD-DOWN", F_N=[round(x, 2) for x in F],
                       F_pod_down_N=round(F_POD_DOWN, 2), m_pod_kg=round(M_POD, 3),
                       src="sq2_v3_margins.py:116-117", note="full pod inertia at flange = conservative"),
        bc=dict(fix="spar-socket bore (R %.2f, %d nodes, all DOF)" % (sR, len(fix)),
                load="motor-mount flange (x=%.1f, %d nodes)" % (fx, len(load)),
                fix_nodes=len(fix), load_nodes=len(load)),
        mesh=dict(nodes=len(nodes), tets=len(els), clmax=round(clmax, 2),
                  order="C3D10 (2nd-order tet)"),
        bbox=dict(x=[round(bb.xmin, 1), round(bb.xmax, 1)], y=[round(bb.ymin, 1), round(bb.ymax, 1)],
                  z=[round(bb.zmin, 1), round(bb.zmax, 1)]),
        mass_g=round(mass_g, 2),
        results=dict(
            sigma_FEA_MPa=round(sigma_fea, 1), sigma_peak_MPa=round(sigma_peak, 1),
            sigma_handcalc_MPa=round(sigma_hand, 1), arm_mm=round(arm, 1),
            allow_MPa=round(allow, 1), defl_mm=round(res["defl"], 4),
            MS_FEA=round(ms_fea, 2), MS_peak=round(ms_peak, 2), MS_handcalc=round(ms_hand, 2),
            Kt_peak_over_handcalc=round(kt, 2), gap_FEA_vs_handcalc=round(gap, 3)),
        handcalc_airframe_governing=HANDCALC_GOV,
        checks=checks,
        seconds=res.get("seconds"),
    )
    with open(os.path.join(OUT, "verdict.json"), "w") as f:
        json.dump(verdict, f, indent=2)

    # ---- deformed-shape / stress PNG ----------------------------------------
    _plot(Xs, vm, disp, F_POD_DOWN, sigma_fea, sigma_peak, allow)

    # keep the ccx job + frd as evidence
    for ext in ("inp", "frd", "step"):
        src = os.path.join(d, f"node.{ext}") if ext == "step" else os.path.join(d, f"job.{ext}")
        if os.path.exists(src):
            shutil.copy(src, os.path.join(OUT, f"sq2_node_{ext}.txt" if ext in ("inp",) else f"sq2_node.{ext}"))
    shutil.rmtree(d, ignore_errors=True)

    print(json.dumps(verdict, indent=2))
    print("\n=== SQ-2 POD NODE, REFEREE (CalculiX) vs HAND CALC ===")
    print(f"load case         : 20 g pod-down, F = {F_POD_DOWN:.1f} N on motor flange (m_pod {M_POD*1000:.0f} g)")
    print(f"mesh              : {len(nodes)} nodes / {len(els)} C3D10 tets, clmax {clmax:.2f} mm")
    print(f"sigma_FEA (99.5%%) : {sigma_fea:7.1f} MPa   (peak node {sigma_peak:.1f} MPa)")
    print(f"sigma_handcalc    : {sigma_hand:7.1f} MPa   (beam, arm {arm:.1f} mm, socket tube {OD:.1f}/{ID:.1f})")
    print(f"allow (503/1.5)   : {allow:7.1f} MPa")
    print(f"MS_FEA            : {ms_fea:+7.2f}   (peak {ms_peak:+.2f})   MS_handcalc {ms_hand:+.2f}")
    print(f"Kt peak/hand      : {kt:7.2f}   gap(99.5%% vs hand) {gap*100:.0f}%")
    print(f"airframe governing: {HANDCALC_GOV['item']} MS +{HANDCALC_GOV['MS']} (CFRP spar, not the node)")
    print(f"VERDICT           : node {'PASS' if verdict['ok'] else 'FAIL'} -> "
          + ("node is NOT the weak link; spar governs" if ms_fea > HANDCALC_GOV["MS"] else "node margin below spar"))
    return verdict


def _plot(Xs, vm, disp, F, s_fea, s_peak, allow):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    scale = 0.0 if disp.max() == 0 else min(5.0, 3.0 / max(np.linalg.norm(disp, axis=1).max(), 1e-9))
    Xd = Xs + disp * scale
    vmax = float(np.percentile(vm, 99.9))   # scale to the stress field, not the far-off allowable
    order = np.argsort(vm)                   # draw hot nodes last so the hotspot is visible
    fig = plt.figure(figsize=(11, 5))
    for k, (XX, ttl) in enumerate([(Xs, "undeformed"), (Xd, f"deformed x{scale:.0f} (max {np.linalg.norm(disp,axis=1).max()*1000:.0f} um)")]):
        ax = fig.add_subplot(1, 2, k + 1, projection="3d")
        p = ax.scatter(XX[order, 0], XX[order, 1], XX[order, 2], c=vm[order], cmap="turbo", s=4, vmin=0, vmax=vmax)
        ax.set_title(ttl, fontsize=9)
        ax.set_box_aspect((np.ptp(Xs[:, 0]), np.ptp(Xs[:, 1]), np.ptp(Xs[:, 2])))
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z"); ax.tick_params(labelsize=6)
        ax.view_init(elev=22, azim=-60)
    cb = fig.colorbar(p, ax=fig.axes, shrink=0.6, pad=0.08)
    cb.set_label(f"von Mises (MPa)  |  allow {allow:.0f} MPa (off-scale)")
    fig.suptitle(f"SQ-2 pod node 7075-T6, 20 g pod-down  F={F:.0f} N | "
                 f"sigma_FEA {s_fea:.0f} MPa (peak {s_peak:.0f}) | allow {allow:.0f} MPa", fontsize=10)
    fig.savefig(os.path.join(OUT, "pod_node_vm.png"), dpi=120, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
