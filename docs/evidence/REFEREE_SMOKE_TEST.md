# Referee physics smoke test (pre-event, 2026-10-17 09:43 PT)

Environment check only: proves the installed toolchain works. No project code. The script is rewritten during the hackathon.

CadQuery 2.8 → STEP (60×6×6 mm Al bar) → gmsh (bundled in FreeCAD.app) 2nd-order tets → CalculiX ccx static solve.

| | value |
|---|---|
| mesh | 6,642 nodes, 3,606 C3D10 tets, 0.6 s |
| solve | 0.4 s |
| tip deflection, ccx | 0.9509 mm |
| Euler-Bernoulli PL³/3EI (P=100 N, E=70 GPa) | 0.9524 mm |
| error | **−0.2 %** |

So one evaluation takes about 1 s, which is enough for hundreds of referee runs during the event.
