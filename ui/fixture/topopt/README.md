# topopt - generative topology optimization (SQ-2 pod node)

Live run of the validated 3D SIMP optimiser from speed-quad (`sq2.topopt`), captured
and rendered for the demo. The pod node carries everything the rotor does (thrust,
reaction torque, gyroscopic moment, 20 g landing) from the T-Motor V3120 face into the
10 mm CFRP spar socket.

## Headline (honest, AlSi10Mg rho 2.68 g/cc both sides)
- Envelope billet **154.4 g** -> optimized **15.0 g** = **90.3 % lighter**
- Compliance **18.0 -> 0.36 N mm** over 18 iterations
- Re-analysed binary design: **vm_max 2.5 MPa** (body), min margin of safety **+53**
- Independent CalculiX cross-check on the finished node (`speed-quad/sq2/out/
  pod_node_ccx_thrust.json`): 124,950 nodes, **vm_max 14.0 MPa**, disp_max 1.8 µm

## Files
- `growth.mp4`, `growth.gif` - material growing/eroding into the optimal shape
- `frames/iter_###.png` - per-iteration iso-surface (dark bg, green material)
- `convergence.png` - compliance (green) and grey fraction (blue) vs iteration
- `pod_node_final.stl` - thresholded final shape (watertight, 5362 faces)
- `live.json` - full history + headline numbers + per-load-case stress

## Reproduce
```bash
PY=/opt/miniconda3/bin/python3
$PY forge/topopt_live.py --h 1.5 --vf 0.12 --iters 18 --every 1   # ~3 min
$PY forge/solidcraft_topopt.py                                     # SolidCraft compare
```

Grid h=1.5 mm (24x27x27) is the demo resolution; the shipped SQ-2 node was solved at
h=1.0 (36x40x40). Density is recovered from the penalised stiffness each iteration
(`xp = ((Ee-Emin)/(1-Emin))**(1/p)`), so the frames are the real optimiser state, not a
re-render. The SolidCraft comparison (`solidcraft/topopt/`) places this STL next to a
solid billet of the same 36x40x40 mm envelope.
