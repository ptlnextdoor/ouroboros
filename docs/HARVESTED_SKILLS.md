# Engineering skills harvested from SQ-2 + MJ-1 (for the parts agent)

Source: `~/Workspace/developer/speed-quad` (SQ-2 speed quad) and `~/Workspace/developer/mj1` (MJ-1 supersonic RC jet).
All of this is **pre-existing**. Reuse **methods and lessons** freely. Reusing **code** means declaring it in
`PROVENANCE.md`. Default plan: rewrite small versions today and treat these repos as references.

## 1. Toolchain already installed on this Mac (verified 2026-10-17)

| tool | path | role in the parts agent |
|---|---|---|
| CadQuery 2.8 (OpenCascade) | python | geometry from agent-written code, STEP/STL export, volume and mass |
| **gmsh** | `/Applications/FreeCAD.app/Contents/Resources/bin/gmsh` | tetra mesh from STEP |
| **CalculiX `ccx`** | `/Applications/FreeCAD.app/Contents/Resources/bin/ccx` | **independent referee FEA** (2nd-order tets, von Mises, displacement) |
| `freecadcmd` | same dir | headless FreeCAD FEM wrapper (proven in `speed-quad/sq2/fc_ccx_check.py`) |
| numpy/scipy/pyamg | python | fast voxel FEA (the agents' own sim) |
| shapely, trimesh | python | 2D sections, mesh checks |

**Two-solver design (this is the sim-parity story):**
- the *agents* use a fast voxel FEA (seconds), their "simulation"
- the *referee* runs CalculiX on a 2nd-order tet mesh of the real STEP, the "physics truth"
- score = parity gap |agent claim − ccx| plus pass/fail on hidden load cases

## 2. Proven methods to reuse

| method | where | lesson |
|---|---|---|
| Voxel SIMP FEA kernel + **analytic self-check** | `speed-quad/sq2/topopt.py`, `sq2/fe_selfcheck.py` | Validate the FE kernel against a cantilever, PL³/3EI and Mc/I, before trusting it. **Ship the same self-check today.** |
| Independent ccx cross-check | `speed-quad/sq2/fc_ccx_check.py` | 124,950-node 2nd-order tet run on the topopt node. FreeCAD force units are **mN·mm**, so always pass `Quantity("60 N")`. |
| Automated design checks as the acceptance gate | `speed-quad/cad/src/sq2_v3_margins.py` (205/205 checks) | margins table (MS = allowable/actual − 1), every number traced to a check |
| Per-pair interference volume caps **with written reasons** | SQ-2 v3.2 M8 commit | no blanket "allowed" exceptions: each exception has a numeric ceiling and a reason, plus a stale-cap check |
| Build prunes stale exports | SQ-2 v3.2 commit a69a8ee | "export dir == built parts" check (a planted stale file gets pruned) |
| Area-rule / physics check sliced from the real STEP | `mj1/tools/area_rule.py` | Judge the **actual exported geometry**, not the optimiser's assumed number. MJ-1 assumed E_WD 1.8, the CAD measured 7.1 |
| Iterate with a table of change → metric | `mj1/docs/MJ1_STATUS.md` | each row is one change and its measured effect: 7.1 → 5.5 → 5.3 → 6.9 (bug) → 3.06 |
| Robust OCC booleans | `mj1/cad/kc_skin.py` | serial booleans (OCC thread pool deadlocks under fork), **fuzzy value only on retry** (3-10× slower), volume-check every boolean, bisect on failure |
| Geometry from live sections | `mj1/cad/kc_skel_lib.py` | shapely polygons ↔ CadQuery solids, clearance via BRepExtrema, ray tests |

## 3. Failure modes we already hit (these become the referee's checks)

| failure | where it happened | referee check |
|---|---|---|
| Optimiser crowned a **negative-drag** design (CdA −1.61) | `speed-quad/cfd/out/shape_opt/best.json` | physics sanity: no negative drag, stress ≥ 0, mass = ρV |
| 5/10 evals died in meshing (7–27 s) and were silently dropped | same `history.json` | mesh failure = explicit FAIL with reason, never skipped |
| Solver "converged" to a non-physical lift mode | `speed-quad/docs/cfd/CFD_VALIDATION.md` | symmetry check: symmetric part + symmetric load → symmetric response |
| CFD geometry ≠ CAD geometry (stale opt_flown.json) | CFD_VALIDATION §2 provenance note | hash the STEP that the referee solves, and show it in the report |
| Optimiser assumed E_WD 1.8, the real geometry gave 7.1 | MJ-1 area rule | parity gap = assumed vs measured, the headline metric |
| Retracted claim (ideal-cycle 0.73 reference error) | MJ1_STATUS | keep failed and retracted claims in the log, never delete them |

## 4. What NOT to bring
- Fusion 360 bridge (`fusion_client.py`): desktop GUI, no headless mode, and the demo shouldn't depend on it.
- OpenFOAM CFD: 4–30 min per run, too slow for a learning loop.
- SQ-2/MJ-1 domain models (BEM props, turbojet ram model): out of scope.
