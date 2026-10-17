#!/usr/bin/env python3
"""Deliverable 1: assemble the REAL SQ-2 v3 drone in SolidCraft from the
per-part STEP files, with PBR materials driven by the manifest.

Emits a SolidCraft script.json (file.insert_step per part + appearance.assign
per part) that `solidcraft-cli run` replays into a .solidcraft design.

Usage:
    python3 build_sq2.py            # writes scripts/sq2_v3.script.json
    python3 build_sq2.py --run      # also runs the CLI + snapshots
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOLIDCRAFT = os.path.dirname(HERE)                      # recursive-agents-hack/solidcraft
REPO = os.path.dirname(SOLIDCRAFT)
V3 = "/Users/aayu/Workspace/developer/speed-quad/cad/out/sq2/v3"
MANIFEST = os.path.join(V3, "parts", "manifest.json")
CLI = "/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli"


def pbr_for(material):
    """Return (pbr dict or None, opacity_override or None) for a material.

    metallic for the alloys / steel / brass, carbon-dark dielectric for CFRP,
    matte for the PA6CF / TPU plastics, translucent for the PC dome.
    """
    m = material.upper()
    if m in ("AL7075", "AL6061"):
        return {"metallic": 1.0, "roughness": 0.30, "dielectric_ior": 1.5}, None
    if m in ("SS", "STEEL"):
        return {"metallic": 1.0, "roughness": 0.22, "dielectric_ior": 1.5}, None
    if m == "BRASS":
        return {"metallic": 1.0, "roughness": 0.28, "dielectric_ior": 1.5}, None
    if m == "CFRP":                       # carbon fibre: dark, near-dielectric, glossy
        return {"metallic": 0.1, "roughness": 0.35, "dielectric_ior": 1.6}, None
    if m == "PA6CF":                      # matte dark grey nylon-carbon print
        return {"metallic": 0.0, "roughness": 0.85, "dielectric_ior": 1.5}, None
    if m == "TPU":                        # light soft rubber
        return {"metallic": 0.0, "roughness": 0.75, "dielectric_ior": 1.5}, None
    if m == "PC":                         # translucent polycarbonate dome
        return {"metallic": 0.0, "roughness": 0.08, "dielectric_ior": 1.58}, 0.35
    if m in ("MOTOR",):                   # anodized bell / stator
        return {"metallic": 0.9, "roughness": 0.4, "dielectric_ior": 1.5}, None
    # PCB, LIPO, ESC, CAM, PROP, VIS, VTX, PUFOAM: plain shaded from rgba
    return None, None


def build_script():
    manifest = json.load(open(MANIFEST))
    commands = [{"command": "file.new", "params": {"name": "SQ-2 v3"}}]
    for part in manifest:
        name = part["name"]
        step = os.path.join(V3, name + ".step")
        if not os.path.exists(step):
            print("  WARN missing", step, file=sys.stderr)
            continue
        commands.append({
            "command": "file.insert_step",
            "params": {"path": step, "name": name, "names": "solid"},
        })
        rgba = part["rgba"]
        r, g, b = (int(round(c * 255)) for c in rgba[:3])
        opacity = rgba[3] if len(rgba) > 3 else 1.0
        pbr, opacity_override = pbr_for(part["material"])
        if opacity_override is not None:
            opacity = opacity_override
        appearance = {
            "components": [name],
            "color": [r, g, b],
            "opacity": round(float(opacity), 3),
        }
        # pbr requires opacity 1 per the schema; skip pbr on translucent parts
        if pbr is not None and appearance["opacity"] >= 0.999:
            appearance["pbr"] = pbr
        commands.append({"command": "appearance.assign", "params": appearance})
    return {"commands": commands}


def main():
    script = build_script()
    out = os.path.join(SOLIDCRAFT, "scripts", "sq2_v3.script.json")
    json.dump(script, open(out, "w"), indent=1)
    n_parts = sum(1 for c in script["commands"] if c["command"] == "file.insert_step")
    print(f"wrote {out}  ({n_parts} parts, {len(script['commands'])} commands)")

    if "--run" in sys.argv:
        design = os.path.join(SOLIDCRAFT, "designs", "sq2_v3.solidcraft")
        print("running CLI ->", design)
        r = subprocess.run([CLI, "run", out, "--save", design, "--allow-errors"],
                           capture_output=True, text=True)
        print(r.stdout[-2000:])
        if r.returncode != 0:
            print("STDERR:", r.stderr[-2000:], file=sys.stderr)
        return r.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
