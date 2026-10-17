"""Insert the optimized pod-node mesh next to its envelope solid in SolidCraft,
snapshot both (iso), and report the mass saving.

Uses the SolidCraft CLI (v0.15): solid.box for the envelope block, file.insert_mesh
for the optimized STL, appearance.assign for the house colours, then snapshot --view iso.

The envelope is the optimiser's design bounding box (Lx x 2R_in x 2R_in), the same
volume the solid billet would occupy. Masses use AlSi10Mg rho = 2.68 g/cc; the
optimized mass is read from the watertight STL volume (honest, mesh-measured).

Run (after forge/topopt_live.py has written ui/fixture/topopt/pod_node_final.stl):
  python3 forge/solidcraft_topopt.py
"""
from __future__ import annotations
import json, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CLI = "/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli"
FIXTURE = os.path.join(REPO, "ui/fixture/topopt")
OUT = os.path.join(REPO, "solidcraft/topopt")
RHO_ALSI = 2.68e-3   # g/mm^3

GREEN = "#2ee6a6"
STEEL = "#7f8a99"


def build_script(stl_path, env_dims, gap):
    """Envelope billet and optimized mesh side by side along Y, both centred on
    the same box (x 0..lx, y/z centred on 0), so the iso view reads cleanly."""
    lx, wy, wz = env_dims
    comp = os.path.splitext(os.path.basename(stl_path))[0]   # insert_mesh names the component after the file
    shift = wy + gap                                         # move the mesh clear of the billet along +Y
    return [
        {"command": "solid.box", "params": {
            "length": lx, "width": wy, "height": wz,
            "center": [lx / 2.0, shift / 2.0, 0.0], "name": "envelope_billet",
            "body_name": "envelope_billet"}},
        {"command": "appearance.assign", "params": {
            "bodies": ["envelope_billet"], "color": STEEL}},
        {"command": "file.insert_mesh", "params": {
            "path": stl_path, "translate": [0.0, -shift / 2.0, 0.0]}},
        {"command": "appearance.assign", "params": {
            "components": [comp], "color": GREEN}},
    ]


def run_cli(args, desc):
    print(f"  {desc}")
    r = subprocess.run([CLI, *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"    FAILED ({r.returncode}): {r.stderr.strip()[:400]}")
    return r


def main():
    os.makedirs(OUT, exist_ok=True)
    stl = os.path.join(FIXTURE, "pod_node_final.stl")
    live = json.load(open(os.path.join(FIXTURE, "live.json")))
    env_mm3 = live["envelope_mm3"]
    grid = live["grid"]; h = live["h_mm"]
    lx = grid[0] * h                              # axial length (motor face to spar)
    wy = wz = (env_mm3 / lx) ** 0.5              # square section of the quoted envelope

    script_path = os.path.join(OUT, "pod_node_compare.json")
    design_path = os.path.join(OUT, "pod_node_compare.solidcraft")
    shot_path = os.path.join(OUT, "pod_node_compare_iso.png")
    json.dump(build_script(stl, (lx, wy, wz), gap=24.0), open(script_path, "w"), indent=1)

    print("[solidcraft_topopt] building design")
    run_cli(["run", script_path, "--save", design_path], "run script -> design")
    print("[solidcraft_topopt] snapshot iso")
    run_cli(["snapshot", "--in", design_path, "--out", shot_path,
             "--view", "iso", "--width", "1600", "--height", "1000"], "snapshot iso")

    env_mass = env_mm3 * RHO_ALSI
    opt_mass = live["optimized_mass_g"]
    report = dict(
        envelope_dims_mm=[lx, wy, wz], envelope_mm3=env_mm3,
        envelope_mass_g=env_mass, optimized_mass_g=opt_mass,
        mass_reduction_pct=100 * (1 - opt_mass / env_mass),
        rho_g_cc=RHO_ALSI * 1e3, material="AlSi10Mg LPBF",
        calculix_check=live.get("calculix_check", {}),
        design=os.path.relpath(design_path, REPO),
        snapshot=os.path.relpath(shot_path, REPO))
    json.dump(report, open(os.path.join(OUT, "mass_report.json"), "w"), indent=1, default=float)
    print(f"[solidcraft_topopt] envelope {env_mass:.1f} g -> optimized {opt_mass:.1f} g "
          f"({report['mass_reduction_pct']:.1f}% lighter)")
    print(f"[solidcraft_topopt] snapshot {shot_path}")


if __name__ == "__main__":
    main()
