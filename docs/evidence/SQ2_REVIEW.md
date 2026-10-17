# SQ-2 Pod Node — FORGE Referee Review

**The FORGE referee (independent CalculiX physics) checking a real flight vehicle part, not a test bracket.**

Part: `pod_LD_node_7075.step` — the machined 7075-T6 motor-mount node from the
SQ-2 drone (speed-quad, `cad/out/sq2/v3/`). It carries the T-Motor V3120 pod
(motor + spinner + prop + nacelles + fairing) and sockets onto the CFRP spar
that cantilevers off the hub. STEP SHA `see verdict.json`.

Pipeline: `forge/sq2_review.py` imports the STEP with CadQuery and reuses the
**unmodified** referee internals (`referee._mesh` → gmsh 2nd-order tets,
`referee._solve` → CalculiX static). No edits to `referee/referee.py`; 7075-T6
is a local material dict. No LLM, no hand-tuning of the result.

```
PY=/opt/miniconda3/bin/python3  FREECAD_BIN=/Applications/FreeCAD.app/Contents/Resources/bin
cd recursive-agents-hack && FREECAD_BIN=$FREECAD_BIN $PY forge/sq2_review.py
```

## Load derivation (honest, traceable)

Governing airframe case in the SQ-2 hand calc is **20 g pod-down** landing/crash
(`speed-quad/cad/out/sq2/v3/margins.json`, item *"spar root bending, 20 g
POD-DOWN"*, **MS +0.48** — the minimum adopted margin of the whole airframe).

The driving force is the pod inertia, taken **verbatim** from
`speed-quad/cad/src/sq2_v3_margins.py:116-117`:

```python
m_pod = 0.148 + 0.009 + 0.027 + 0.033 + 0.018 + 0.009 + 0.004   # kg  (motor, spinner, node, nacelles, fairing, prop, spar)
F_pod_down = m_pod * landing_g * g                               # landing_g = 20, g = 9.80665
```

→ `m_pod = 0.248 kg`, **`F_pod_down = 48.6 N`**.

Everything in the pod bolts to the node and is reacted by the spar in the node's
socket. We apply the **full** pod inertia at the motor-mount flange (the longest
lever to the socket) → a deliberately **conservative** bound on the node.

## Boundary conditions (auto-selected off the STEP geometry)

| | Face (detected) | DOF / load |
|---|---|---|
| **FIX** | spar-socket bore, cylindrical R≈3.02 mm, 25 mm engagement (spar bonded + 2× M2 set-screw) | all 3 DOF, nodes within R+0.5 mm of the socket axis |
| **LOAD** | motor-mount flange, planar face, −x normal, area ≈1029 mm² | `F = (0, 0, −48.6) N` (body −z = pod-down), over flange nodes within r<12.5 mm |

Faces are found by type + orientation + radius (see `detect_bcs`), so the script
is not hard-coded to one export. Node counts for both BC sets are recorded in
`verdict.json`.

## Mesh

| nodes | tets | element | clmax | budget |
|---|---|---|---|---|
| 48,031 | 27,442 | C3D10 (2nd-order tet) | 1.20 mm | < 80k ✔ |

clmax 1.20 mm ≈ thinnest structural wall (socket tube wall ~3 mm, flange 3.5 mm,
seat ring 2 mm); referee self-test validates this pipeline against beam theory to
<3 %.

## Results — FEA vs hand calc (FoS 1.5, 7075-T6 σy 503 MPa, allow 335 MPa)

| quantity | value |
|---|---|
| σ_FEA (99.5-percentile, referee headline) | **10.7 MPa** |
| σ_peak (single hottest node, socket/set-screw concentration) | 44.8 MPa |
| σ_handcalc (beam: socket tube annulus 12.1/6.0 mm, arm 25 mm) | 7.5 MPa |
| allow = σy / 1.5 | 335.3 MPa |
| max deflection | 0.013 mm |
| **MS_FEA** = σy/(1.5·σ_FEA) − 1 | **+30.3** |
| MS_peak (on the hottest node) | +6.5 |
| MS_handcalc | +43.6 |
| gap, σ_FEA(99.5%) vs hand calc | 43 % |
| K_t, σ_peak / σ_handcalc | 5.95 |

## Verdict (two ways this is a demo win)

1. **The referee confirms the design intent.** The node is nowhere near the weak
   link: MS_FEA **+30** vs the airframe-governing spar at **MS +0.48**. The
   machined 7075 node is correctly *not* the limiting part — the CFRP spar is, as
   the hand calc says. The referee independently backs the design's structural
   story.

2. **The referee catches what a beam hand calc misses.** A plain annulus beam
   formula gives 7.5 MPa; CalculiX finds a local **44.8 MPa** at the socket
   mouth / set-screw region — a stress-concentration factor **≈6×** that no
   closed-form annulus calc exposes. Still a huge margin here, but this is
   exactly the kind of local hotspot the referee exists to surface before a part
   is cut.

`verdict.json` is written in the same `checks[]` shape `referee.evaluate()`
returns, so the UI can show it directly.

## Honest caveats

- **Load application is conservative but idealized.** Full pod inertia is a point
  force resultant spread over the flange face, not the true distributed
  motor-bolt + spinner + prop reaction. It bounds the node; it is not the exact
  in-service field.
- **The fixed socket is a rigid clamp.** The real spar is a finite-stiffness
  bonded/grub-screw joint; a rigid clamp over-stiffens locally and can inflate
  the socket-edge peak. The 99.5-pct number (10.7 MPa) is the robust headline;
  the 44.8 MPa single node is mesh/BC-sensitive (hence reported separately).
- **One load case.** Only 20 g pod-down (the governing airframe case) is run.
  Thrust (~13.7 N/rotor at 590 km/h) and side-gust cases are smaller for this
  part and not solved here.
- **Hand calc compared is a node-level beam estimate**, derived here from the
  socket-tube section; the +0.48 airframe margin it sits next to is the *spar*,
  a different member. The node and the spar share the same 20 g pod-down load,
  which is the honest common basis for the comparison.

## Artifacts

`ui/fixture/sq2_review/`
- `verdict.json` — referee-shaped verdict (checks list, results, BCs, mesh)
- `pod_node_vm.png` — von Mises on the node, undeformed + deformed ×5
- `sq2_node.step` — the exact solid solved
- `sq2_node.frd.gz`, `sq2_node_inp.txt.gz` — raw CalculiX deck + results (evidence)
