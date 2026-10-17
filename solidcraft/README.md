# SolidCraft driver — hackathon deliverables

An AI hardware engineer drives real CAD in **SolidCraft** (a Fusion-360-like
desktop app). Three things, each verified.

CLI: `/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli`
GUI: `/Applications/SolidCraft.app/Contents/MacOS/SolidCraft`

---

## 1. SQ-2 v3 assembly (real 78-part drone)

`scripts/build_sq2.py` reads the real per-part STEPs + material manifest from
`speed-quad/cad/out/sq2/v3/` and emits a SolidCraft `script.json`:
`file.insert_step` per part + `appearance.assign` per part (PBR metallic for
7075/6061/SS/brass, carbon-dark CFRP, matte PA6CF/TPU, translucent PC dome).

```bash
/opt/miniconda3/bin/python3 scripts/build_sq2.py --run      # build design
# snapshots:
CLI=/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli
$CLI snapshot --in designs/sq2_v3.solidcraft --out shots/sq2_v3_iso.png   --view iso   --width 1280 --height 960
$CLI snapshot --in designs/sq2_v3.solidcraft --out shots/sq2_v3_front.png --view front --width 1280 --height 960
$CLI snapshot --in designs/sq2_v3.solidcraft --out shots/sq2_v3_side.png  --view right --width 1280 --height 960
$CLI snapshot --in designs/sq2_v3.solidcraft scripts/explode.json --out shots/sq2_v3_exploded.png --view iso --width 1280 --height 960
```

Result: `designs/sq2_v3.solidcraft` (110 bodies, 2.50 kg). Renders
(`shots/sq2_v3_*.png`) match the Fusion reference
`speed-quad/docs/img/sq2/v3/fusion_v3_iso.png`: black PA6CF fuselage, silver
spinners, carbon-fibre X-struts, 4 tilt pods. Exploded view
(`explode.create` scale 2.0 + `explode.show`) reveals LiPo packs, PCBs,
motors, red spinner cones.

## 2. FORGE bracket — native sketch + extrude

`forge/solidcraft.py :: bracket_to_solidcraft(params, out_dir)` builds the
bracket **natively** (no imported STEP), from `forge/blocks.py` params:

- plate: YZ rect, extrude +X by `t_plate` (new)
- arm: YZ rect over `[plate_h-t_arm .. plate_h]`, extrude +X by `arm_len` (join)
- gusset: XZ triangle at y=0, symmetric extrude by `gusset` (join)
- 4 wall bolts: YZ circles, through-all cut along X
- motor + lightening holes: XY circles, through-all cut along Z

Saves `forge_bracket/bracket.solidcraft`, exports `bracket.step`, snapshots
`bracket.png`, then **verifies** the exported STEP volume against
`cadquery blocks.build(params).Volume()`.

```bash
/opt/miniconda3/bin/python3 -m forge.solidcraft            # default params
/opt/miniconda3/bin/python3 -m forge.solidcraft params.json
```

Verified (default params): native **16995.3 mm³** vs cadquery **16995.2 mm³**,
error **0.0005 %** — well within 2 %. Native sketching was fast and accurate,
so no STEP-insert fallback was needed.

## 3. Live GUI drive

The GUI listens when launched with `--control PORT`:

```
SolidCraft --control 7878
# -> "control server listening on 127.0.0.1:7878 (token in .../control/7878.token)"
```

`solidcraft-cli mcp --connect 127.0.0.1:PORT --token <T>` speaks JSON-RPC MCP
to that window. The `execute` tool runs any of the 385 commands live; the
audience watches the model appear in the viewport.

```bash
/opt/miniconda3/bin/python3 -m forge.solidcraft --live            # default
/opt/miniconda3/bin/python3 -m forge.solidcraft --live params.json
```

`drive_live()` launches/attaches to the window, replays the same 21-command
bracket build through MCP `execute`, then captures a window screenshot
(`shots/live_bracket_window.png`) as proof. Verified: 21 commands, 0 errors,
bracket + full timeline (plate/arm/gusset/bolts/zholes) visible in the live
window.

Token lives at `~/Library/Application Support/SolidCraft/control/<port>.token`.
`forge.solidcraft` reads it automatically. If a window is already open without
`--control`, there is no way to attach after the fact — relaunch with
`--control`, or open a saved design directly: `open -a SolidCraft <file>.solidcraft`.

---

## 4. MJ-1 supersonic jet (demo subject)

`scripts/build_mj1.py` assembles the MJ-1 in SolidCraft 0.15 from
`mj1/cad/out/kc/`: the OML skin (`OML_master.step`) + every placed vendor STEP
(JetCat P550 turbine, 2 KST servos, Matek H743 FC + GNSS + airspeed, fuel bag,
LiPo, RunCam/FPV cameras, VTX, CRSF RX, pitot). Appearances: orange skin
(matches `FINAL_vs_KingChaser.png`), grey metallic turbine, dark avionics,
tan fuel bag. 802 bodies, ~77 kg modelled mass.

```bash
/opt/miniconda3/bin/python3 scripts/build_mj1.py --run            # + optional --skeleton (108 MB)
```

Outputs in `shots/`:
- `mj1_iso.png`, `mj1_front.png` — orange jet, matches the reference render
- `mj1_exploded.png` — `explode.create` scale 1.4, turbine pulled aft + avionics fanned out
- `mj1_cutaway.png` — `inspect.section` (XZ at Y=0) viewed 3/4 from the right: the
  section cut through the orange skin reveals the grey turbine, tan fuel bag,
  avionics boxes and servos packed inside the fuselage
- `mj1_orbit.gif` — 20-frame camera orbit (headless `snapshot --camera`), for the video
- `mj1_clearance_report.json` — **JetCat turbine vs skin clearance**:
  min gap ~0.3 mm, ~3 % of the turbine surface outside the skin in x≈1722-2087
  (belly/intake). Verdict TIGHT — needs a local skin bulge or turbine shift.
  (Method note: SolidCraft's exact B-rep `inspect.clearance` on the 50M-mm³ OML
  solid did not finish headless within 150 s; the check falls back to a
  trimesh surface-sample proximity on the world-placed meshes exported from
  SolidCraft.)

---

## Files

```
solidcraft/
  scripts/build_sq2.py          SQ-2 assembly generator (+ --run)
  scripts/sq2_v3.script.json    generated 157-cmd assembly script
  scripts/explode.json          explode.create + explode.show
  designs/sq2_v3.solidcraft     built assembly (110 bodies)
  shots/sq2_v3_{iso,front,side,exploded}.png
  shots/live_bracket_window.png live GUI proof
  forge_bracket/bracket.{solidcraft,step,png,script.json}
forge/solidcraft.py             bracket_to_solidcraft() + drive_live()
```
