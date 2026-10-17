#!/usr/bin/env python3
"""MJ-1 supersonic RC jet — assemble in SolidCraft 0.15.

Loads the OML skin + skeleton + every placed vendor STEP into one design with
good appearances (orange skin, grey turbine, black carbon, coloured avionics),
then produces iso/front snapshots, an exploded view, a cutaway section, and an
orbit GIF. Also runs inspect.clearance between the turbine and the skin.

Headless CLI path (reliable): `solidcraft-cli run script.json --save ...` then
`snapshot`/`render`. The 108 MB skeleton STEP is optional (--skeleton).

Usage:
  /opt/miniconda3/bin/python3 scripts/build_mj1.py            # write script
  /opt/miniconda3/bin/python3 scripts/build_mj1.py --run      # build + shots
  /opt/miniconda3/bin/python3 scripts/build_mj1.py --run --skeleton
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOLIDCRAFT = os.path.dirname(HERE)
REPO = os.path.dirname(SOLIDCRAFT)
MJ1 = "/Users/aayu/Workspace/developer/mj1"
KC = os.path.join(MJ1, "cad", "out", "kc")
CLI = "/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli"
SHOTS = os.path.join(SOLIDCRAFT, "shots")

OML = os.path.join(KC, "OML_master.step")
SKELETON = os.path.join(KC, "skeleton_assembly.step")
VENDOR_PLACED = os.path.join(KC, "vendor_placed.json")

# appearance by vendor category -> (color hex, pbr?)
CAT_LOOK = {
    "jetcat":  ("#8f949a", {"metallic": 1.0, "roughness": 0.35, "dielectric_ior": 1.5}),
    "fuel":    ("#d9d2b6", None),
    "kst":     ("#1d1f24", None),
    "matek":   ("#1e3a2e", None),
    "runcam":  ("#111111", None),
    "tbs":     ("#111111", None),
    "battery": ("#2b2b2b", None),
}
SKIN_ORANGE = "#e2611a"       # orange OML skin (matches FINAL_vs_KingChaser)
SKELETON_GREY = "#c4c7cc"     # 6061 frames / carbon spars shown light grey


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def build_script(with_skeleton=False):
    cmds = [{"command": "file.new", "params": {"name": "MJ-1"}}]

    # 1) orange OML skin, translucent so the guts show in the cutaway shots
    cmds.append({"command": "file.insert_step",
                 "params": {"path": OML, "name": "OML_skin", "names": "solid"}})
    cmds.append({"command": "appearance.assign",
                 "params": {"components": ["OML_skin"],
                            "color": _hex_to_rgb(SKIN_ORANGE), "opacity": 1.0,
                            "pbr": {"metallic": 0.0, "roughness": 0.5,
                                    "dielectric_ior": 1.5}}})

    # 2) optional skeleton (108 MB; grey)
    if with_skeleton:
        cmds.append({"command": "file.insert_step",
                     "params": {"path": SKELETON, "name": "skeleton", "names": "solid"}})
        cmds.append({"command": "appearance.assign",
                     "params": {"components": ["skeleton"],
                                "color": _hex_to_rgb(SKELETON_GREY), "opacity": 1.0,
                                "pbr": {"metallic": 0.6, "roughness": 0.5,
                                        "dielectric_ior": 1.5}}})

    # 3) every placed vendor part, coloured by category
    vendor = json.load(open(VENDOR_PLACED))
    for v in vendor:
        path = os.path.join(MJ1, v["file"])
        if not os.path.exists(path):
            print("  WARN missing", path, file=sys.stderr)
            continue
        name = os.path.splitext(os.path.basename(v["file"]))[0].replace("_placed", "")
        cmds.append({"command": "file.insert_step",
                     "params": {"path": path, "name": name, "names": "solid"}})
        hexc, pbr = CAT_LOOK.get(v["category"], (v.get("colour", "#888888"), None))
        ap = {"components": [name], "color": _hex_to_rgb(hexc), "opacity": 1.0}
        if pbr:
            ap["pbr"] = pbr
        cmds.append({"command": "appearance.assign", "params": ap})
    return {"commands": cmds}, [os.path.splitext(os.path.basename(v["file"]))[0].replace("_placed", "") for v in vendor]


def main():
    with_skeleton = "--skeleton" in sys.argv
    script, vendor_names = build_script(with_skeleton)
    os.makedirs(os.path.join(SOLIDCRAFT, "scripts"), exist_ok=True)
    out = os.path.join(SOLIDCRAFT, "scripts", "mj1.script.json")
    json.dump(script, open(out, "w"), indent=1)
    n = sum(1 for c in script["commands"] if c["command"] == "file.insert_step")
    print(f"wrote {out}  ({n} inserts, {len(script['commands'])} commands, skeleton={with_skeleton})")

    if "--run" not in sys.argv:
        return 0

    os.makedirs(SHOTS, exist_ok=True)
    design = os.path.join(SOLIDCRAFT, "designs", "mj1.solidcraft")
    print("building ->", design)
    r = subprocess.run([CLI, "run", out, "--save", design, "--allow-errors"],
                       capture_output=True, text=True)
    print(r.stdout[-800:])
    if r.returncode != 0:
        print("STDERR", r.stderr[-1500:], file=sys.stderr)
        return r.returncode

    # snapshots: iso + front
    for view in ("iso", "front"):
        subprocess.run([CLI, "snapshot", "--in", design, "--out",
                        os.path.join(SHOTS, f"mj1_{view}.png"),
                        "--view", view, "--width", "1600", "--height", "900"],
                       capture_output=True, text=True)
    # exploded
    expl = os.path.join(SOLIDCRAFT, "scripts", "mj1_explode.json")
    json.dump({"commands": [
        {"command": "explode.create", "params": {"name": "blown", "scale": 1.4}},
        {"command": "explode.show", "params": {"view": "blown"}},
    ]}, open(expl, "w"))
    subprocess.run([CLI, "snapshot", "--in", design, expl, "--out",
                    os.path.join(SHOTS, "mj1_exploded.png"),
                    "--view", "iso", "--width", "1600", "--height", "900"],
                   capture_output=True, text=True)
    # cutaway: horizontal section through the body centreline (XZ at Y=0)
    sect = os.path.join(SOLIDCRAFT, "scripts", "mj1_section.json")
    json.dump({"commands": [
        {"command": "inspect.section", "params": {"plane": "XZ", "offset": 0}},
    ]}, open(sect, "w"))
    subprocess.run([CLI, "snapshot", "--in", design, sect, "--out",
                    os.path.join(SHOTS, "mj1_cutaway.png"),
                    "--view", "iso", "--width", "1600", "--height", "900"],
                   capture_output=True, text=True)

    print("snapshots written to", SHOTS)

    # clearance: JetCat turbine vs OML skin. The exact B-rep inspect.clearance
    # on the 50M-mm3 OML solid does not finish headless in a sane time, so we
    # export both parts' world-placed meshes and do a trimesh proximity check.
    clearance_turbine_vs_skin(design)
    return 0


def clearance_turbine_vs_skin(design):
    """Report the JetCat P550 turbine vs MJ-1 skin clearance (mesh proximity)."""
    try:
        import trimesh  # noqa: F401
    except ImportError:
        print("trimesh not available; skipping clearance", file=sys.stderr)
        return None
    turb_step = os.path.join(KC, "vendor", "jetcat_p550_placed.step")
    turb_stl = os.path.join(SHOTS, "mj1_turbine_placed.stl")
    oml_stl = os.path.join(SHOTS, "mj1_oml.stl")
    subprocess.run([CLI, "run", turb_step, "--out", turb_stl], capture_output=True, text=True)
    subprocess.run([CLI, "run", OML, "--out", oml_stl], capture_output=True, text=True)

    import json as _json
    import trimesh
    from trimesh.proximity import ProximityQuery
    turb = trimesh.load(turb_stl); oml = trimesh.load(oml_stl)
    if hasattr(turb, "dump"):
        turb = turb.dump(concatenate=True)
    if hasattr(oml, "dump"):
        oml = oml.dump(concatenate=True)
    pts, _ = trimesh.sample.sample_surface(turb, 8000)
    dist = ProximityQuery(oml).on_surface(pts)[1]
    outside = ~oml.contains(pts)
    rep = {
        "check": "JetCat P550 turbine vs MJ-1 OML skin",
        "method": "trimesh surface-sample proximity on world-placed meshes "
                  "exported from SolidCraft (exact B-rep inspect.clearance on the "
                  "50M-mm3 OML solid did not finish headless in time)",
        "min_gap_mm": round(float(dist.min()), 2),
        "pct_turbine_surface_within_5mm_of_skin": round(float((dist < 5).mean() * 100), 1),
        "pct_turbine_surface_outside_skin": round(float(outside.mean() * 100), 1),
        "protrusion_x_range_mm": ([round(float(pts[outside][:, 0].min()), 1),
                                   round(float(pts[outside][:, 0].max()), 1)]
                                  if outside.any() else None),
    }
    _json.dump(rep, open(os.path.join(SHOTS, "mj1_clearance_report.json"), "w"), indent=1)
    print("clearance:", _json.dumps(rep))
    return rep


if __name__ == "__main__":
    sys.exit(main())
