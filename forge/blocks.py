"""Parametric part family the agents design with. Agents choose numbers, never raw CAD.

Frame: wall at x=0, +x out from the wall, +z up, y across. Units mm.
Plate: x in [0, t_plate], y in [-width/2, width/2], z in [0, plate_h].
Arm:   x in [0, arm_len], z in [plate_h - t_arm, plate_h]. Motor hole (d 6.5) at x = arm_len - 10.
Gusset: triangle under the arm in the XZ plane, centred at y = 0.
"""
import cadquery as cq

PARAMS = {  # name: (min, max, meaning)
    "t_plate":    (1.0, 12.0, "wall plate thickness"),
    "t_arm":      (1.0, 12.0, "arm thickness"),
    "plate_h":    (20.0, 120.0, "wall plate height"),
    "width":      (10.0, 80.0, "bracket width"),
    "arm_len":    (20.0, 200.0, "wall to arm tip; motor hole sits 10 mm in from the tip"),
    "gusset":     (0.0, 12.0, "gusset thickness, 0 = none"),
    "gusset_len": (0.0, 200.0, "gusset length along the arm"),
    "gusset_h":   (0.0, 120.0, "gusset height down the plate"),
    "lighten_n":  (0, 6, "number of lightening holes in the arm"),
    "lighten_d":  (0.0, 30.0, "lightening hole diameter"),
}
HOLE_FROM_TIP = 10.0


def describe():
    return "\n".join(f'  "{k}": {lo}..{hi}  # {m}' for k, (lo, hi, m) in PARAMS.items())


def clamp(p):
    out = {}
    for k, (lo, hi, _) in PARAMS.items():
        v = float(p.get(k, lo if k in ("gusset", "lighten_n", "lighten_d", "gusset_len", "gusset_h") else (lo + hi) / 2))
        out[k] = min(max(v, lo), hi)
    out["lighten_n"] = int(round(out["lighten_n"]))
    return out


def motor_xy(p):
    return p["arm_len"] - HOLE_FROM_TIP, 0.0


def build(p):
    p = clamp(p)
    T, A, H, W, L = p["t_plate"], p["t_arm"], p["plate_h"], p["width"], p["arm_len"]
    s = cq.Solid.makeBox(T, W, H, cq.Vector(0, -W / 2, 0))
    s = s.fuse(cq.Solid.makeBox(L, W, A, cq.Vector(0, -W / 2, H - A)))
    if p["gusset"] > 0 and p["gusset_len"] > 1 and p["gusset_h"] > 1:
        gl, gh, g = min(p["gusset_len"], L - T), min(p["gusset_h"], H - A), p["gusset"]
        tri = (cq.Workplane("XZ").polyline([(T, H - A), (T + gl, H - A), (T, H - A - gh)]).close()
               .extrude(g / 2, both=True)).val()
        s = s.fuse(tri)
    cut = []
    for zf in (0.3, 0.7):                                   # two M5 wall bolts through the plate
        for y in (-W / 4, W / 4):
            cut.append(cq.Solid.makeCylinder(2.75, T + 2, cq.Vector(-1, y, H * zf - A * zf), cq.Vector(1, 0, 0)))
    mx, my = motor_xy(p)
    cut.append(cq.Solid.makeCylinder(3.25, A + 2, cq.Vector(mx, my, H - A - 1), cq.Vector(0, 0, 1)))
    n, d = p["lighten_n"], p["lighten_d"]
    if n > 0 and d > 1:
        x0, x1 = T + d / 2 + 2 + (p["gusset_len"] if p["gusset"] > 0 else 0), mx - 6.5 - d / 2
        if x1 > x0 and d < W - 4:
            for i in range(n):
                x = x0 + (x1 - x0) * (i + 0.5) / n
                cut.append(cq.Solid.makeCylinder(d / 2, A + 2, cq.Vector(x, 0, H - A - 1), cq.Vector(0, 0, 1)))
    for c in cut:
        s = s.cut(c)
    return s.clean()


if __name__ == "__main__":
    s = build({"t_plate": 4, "t_arm": 4, "plate_h": 50, "width": 30, "arm_len": 90, "gusset": 3, "gusset_len": 40, "gusset_h": 30, "lighten_n": 2, "lighten_d": 10})
    assert s.isValid() and s.Volume() > 0
    print("blocks selftest ok, volume mm3 =", round(s.Volume()))
