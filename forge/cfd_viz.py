"""Render demo visuals from the SQ-2 OpenFOAM run (Oct 16 2026, converged, 2500 it).

Reads only. Never launches a solver. Every number printed comes from the case files:
  postProcessing/forceCoeffs_total/0/coefficient.dat  (Cd history)
  case_meta.json                                      (V, Aref, alpha, Mach)
  VTK/case_2500/boundary/*.vtp, internal.vtu          (surface p, velocity field)

Outputs (ui/fixture/cfd/):
  sq2_cfd_orbit.mp4 / .gif     orbit of the body colored by Cp with streamlines
  sq2_cfd_convergence.png      Cd vs iteration
  sq2_cfd_receipt.png          one-slide validation receipt
  sq2_cfd_kenburns.mp4         fallback: pan/zoom over the existing CFD PNGs

Usage: /opt/miniconda3/bin/python3 forge/cfd_viz.py [orbit|convergence|receipt|kenburns|all]
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

SQ2 = Path("/Users/aayu/Workspace/developer/speed-quad")
CASE = SQ2 / "cfd/cases/sq2_l0"
VTK_DIR = CASE / "VTK/case_2500"
IMG_DIR = SQ2 / "docs/img/cfd"
OUT = Path(__file__).resolve().parent.parent / "ui/fixture/cfd"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

BG = "#06080d"
GREEN = "#2ee6a6"
RED = "#ff5f6d"
BLUE = "#4aa8ff"
FG = "#e6e9ef"
DIM = "#7b8494"

W, H = 1920, 1080
FPS = 30
ORBIT_SECONDS = 7

# Numbers from docs/cfd/CFD_VALIDATION.md sections V1 and V3 (Oct 16 run).
CELLS = 3_553_627
ITERS = 2500
CDA_CFD_CM2 = 32.36
CDA_DESIGN_CM2 = 31.92
SPHEROID_CD = 0.07097
SPHEROID_REF = 0.073
RUN_LABEL = "OpenFOAM simpleFoam k-omega SST, converged run of 2026-10-16"


def meta() -> dict:
    return json.loads((CASE / "case_meta.json").read_text())


def cd_history() -> tuple[np.ndarray, np.ndarray]:
    rows = []
    for line in (CASE / "postProcessing/forceCoeffs_total/0/coefficient.dat").read_text().splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        rows.append((float(parts[0]), float(parts[1])))
    arr = np.array(rows)
    return arr[:, 0], arr[:, 1]


def hex_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def run_ffmpeg(args: list[str]) -> None:
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", *args], check=True)


# ---------------------------------------------------------------- orbit


def render_orbit() -> None:
    import vtk

    m = meta()
    v_inf = m["V"]
    q_kin = 0.5 * v_inf * v_inf  # p in the case is kinematic (p/rho)

    def load_vtp(name: str):
        r = vtk.vtkXMLPolyDataReader()
        r.SetFileName(str(VTK_DIR / "boundary" / f"{name}.vtp"))
        r.Update()
        return r.GetOutput()

    body = vtk.vtkAppendPolyData()
    for patch in m["patches"]:
        body.AddInputData(load_vtp(patch))
    body.Update()
    surf = body.GetOutput()

    calc = vtk.vtkArrayCalculator()
    calc.SetInputData(surf)
    calc.SetAttributeTypeToPointData()
    calc.AddScalarArrayName("p")
    calc.SetFunction(f"p/{q_kin}")
    calc.SetResultArrayName("Cp")
    calc.Update()
    surf = calc.GetOutput()

    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(surf)
    normals.SplittingOff()
    normals.Update()
    surf = normals.GetOutput()

    lut = vtk.vtkColorTransferFunction()
    lut.SetColorSpaceToLab()
    lut.AddRGBPoint(-1.5, *hex_rgb(BLUE))
    lut.AddRGBPoint(-0.4, 0.20, 0.42, 0.62)
    lut.AddRGBPoint(0.0, 0.55, 0.57, 0.62)
    lut.AddRGBPoint(0.6, 0.93, 0.62, 0.42)
    lut.AddRGBPoint(1.0, *hex_rgb(RED))

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(surf)
    mapper.SetScalarModeToUsePointFieldData()
    mapper.SelectColorArray("Cp")
    mapper.SetLookupTable(lut)
    mapper.SetScalarRange(-1.5, 1.0)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetSpecular(0.25)
    actor.GetProperty().SetSpecularPower(30)

    # Streamlines from the internal field, seeded on a disc just upstream of the nose.
    print("loading internal.vtu (700 MB) ...", flush=True)
    ur = vtk.vtkXMLUnstructuredGridReader()
    ur.SetFileName(str(VTK_DIR / "internal.vtu"))
    ur.Update()
    grid = ur.GetOutput()
    grid.GetPointData().SetActiveVectors("U")

    lo, hi = m["bounds_lo"], m["bounds_hi"]
    seeds = vtk.vtkPointSource()
    seeds.SetCenter(lo[0] - 0.05 * (hi[0] - lo[0]), 0.0, 0.0)
    seeds.SetRadius(0.85 * max(hi[1] - lo[1], hi[2] - lo[2]) / 2)
    seeds.SetDistributionToShell()
    seeds.SetNumberOfPoints(90)
    seeds.SetDistributionToUniform()
    seeds.Update()

    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(grid)
    tracer.SetSourceConnection(seeds.GetOutputPort())
    tracer.SetIntegratorTypeToRungeKutta45()
    tracer.SetIntegrationDirectionToForward()
    tracer.SetMaximumPropagation(1.6 * (hi[0] - lo[0]))
    tracer.SetInitialIntegrationStep(0.2)
    tracer.SetMaximumNumberOfSteps(4000)
    tracer.Update()
    lines = tracer.GetOutput()
    print("streamlines:", lines.GetNumberOfLines(), flush=True)

    tube = vtk.vtkTubeFilter()
    tube.SetInputData(lines)
    tube.SetRadius(0.0009)
    tube.SetNumberOfSides(6)
    tube.Update()

    speed = vtk.vtkColorTransferFunction()
    speed.AddRGBPoint(0.4 * v_inf, 0.18, 0.22, 0.30)
    speed.AddRGBPoint(1.0 * v_inf, 0.55, 0.65, 0.80)
    speed.AddRGBPoint(1.3 * v_inf, *hex_rgb(GREEN))
    smap = vtk.vtkPolyDataMapper()
    smap.SetInputConnection(tube.GetOutputPort())
    smap.SetScalarModeToUsePointFieldData()
    smap.SelectColorArray("U")
    smap.SetLookupTable(speed)
    smap.SetScalarRange(0.4 * v_inf, 1.3 * v_inf)
    smap.GetLookupTable().SetVectorModeToMagnitude()
    sactor = vtk.vtkActor()
    sactor.SetMapper(smap)
    sactor.GetProperty().SetOpacity(0.55)

    ren = vtk.vtkRenderer()
    ren.SetBackground(*hex_rgb(BG))
    ren.AddActor(actor)
    ren.AddActor(sactor)
    ren.SetUseFXAA(True)
    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(W, H)
    rw.SetMultiSamples(0)
    rw.AddRenderer(ren)

    cx = 0.5 * (lo[0] + hi[0])
    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(cx, 0.0, 0.0)
    cam.SetViewUp(0, 0, 1)
    cam.SetViewAngle(24)
    dist = 2.3 * (hi[0] - lo[0])

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.ReadFrontBufferOff()
    writer = vtk.vtkPNGWriter()

    frames = OUT / "_orbit_frames"
    frames.mkdir(parents=True, exist_ok=True)
    n = ORBIT_SECONDS * FPS
    for i in range(n):
        t = i / n
        az = math.radians(-155 + 115 * t)  # front three-quarter sweeping to rear three-quarter, same side
        el = math.radians(22 + 8 * math.sin(math.pi * t))
        cam.SetPosition(
            cx + dist * math.cos(el) * math.cos(az),
            dist * math.cos(el) * math.sin(az),
            dist * math.sin(el),
        )
        ren.ResetCameraClippingRange()
        rw.Render()
        w2i.Modified()
        w2i.Update()
        writer.SetFileName(str(frames / f"f{i:04d}.png"))
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()
        if i % 30 == 0:
            print(f"frame {i}/{n}", flush=True)

    caption = caption_png(
        "orbit",
        [
            ("SQ-2  surface Cp + streamlines", 44, FG, 72, 64),
            (RUN_LABEL, 26, DIM, 72, 126),
            (f"590 km/h  (M 0.48)   alpha 1.8 deg   {CELLS/1e6:.2f} M cells   {ITERS} iterations", 26, DIM, 72, 164),
            (f"CdA {CDA_CFD_CM2:.1f} cm2  vs  {CDA_DESIGN_CM2:.1f} design  (+1.4 %)", 30, GREEN, 72, 960),
        ],
    )
    mp4 = OUT / "sq2_cfd_orbit.mp4"
    run_ffmpeg(
        [
            "-framerate", str(FPS), "-i", str(frames / "f%04d.png"), "-i", str(caption),
            "-filter_complex", "[0:v][1:v]overlay=0:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(mp4),
        ]
    )
    caption.unlink()
    gif = OUT / "sq2_cfd_orbit.gif"
    run_ffmpeg(
        [
            "-i", str(mp4),
            "-vf", "fps=15,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4",
            str(gif),
        ]
    )
    for f in frames.glob("f*.png"):
        f.unlink()
    frames.rmdir()
    print("wrote", mp4, gif)


FONT = "/System/Library/Fonts/Menlo.ttc"


def caption_png(name: str, items: list[tuple[str, int, str, int, int]], band: bool = False) -> Path:
    """Transparent 1920x1080 caption layer: (text, size, color, x, y). This ffmpeg lacks drawtext.
    band=True draws dark top/bottom bands first (for sources with a light background)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if band:
        d.rectangle([0, 0, W, 220], fill=(6, 8, 13, 235))
        d.rectangle([0, 920, W, H], fill=(6, 8, 13, 235))
    for text, size, color, x, y in items:
        d.text((x, y), text, font=ImageFont.truetype(FONT, size), fill=color)
    path = OUT / f"_caption_{name}.png"
    img.save(path)
    return path


# ---------------------------------------------------------------- convergence


def render_convergence() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    it, cd = cd_history()
    tail = cd[it >= ITERS - 625]
    cd_mean, cd_std = tail.mean(), tail.std()
    m = meta()
    cda_cm2 = cd_mean * m["Aref"] * 1e4  # windowed mean, same number CFD_VALIDATION.md reports

    fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.plot(it, cd, color=BLUE, lw=2.0)
    ax.axhline(cd_mean, color=GREEN, lw=1.2, ls="--")
    ax.axvspan(ITERS - 625, ITERS, color=GREEN, alpha=0.07, lw=0)
    ax.set_xlim(0, ITERS)
    ax.set_ylim(0.03, 0.09)
    for s in ax.spines.values():
        s.set_color(DIM)
    ax.tick_params(colors=DIM, labelsize=18)
    ax.grid(color="#1a1f2a", lw=0.8)
    ax.set_xlabel("iteration", color=DIM, fontsize=22, family="monospace")
    ax.set_ylabel("Cd  (on Aref 717 cm2)", color=DIM, fontsize=22, family="monospace")
    fig.text(0.07, 0.93, "SQ-2 drag coefficient vs iteration", color=FG, fontsize=34, family="monospace")
    fig.text(0.07, 0.885, RUN_LABEL + f", {CELLS/1e6:.2f} M cells", color=DIM, fontsize=19, family="monospace")
    fig.text(
        0.50, 0.72,
        f"last 625 it: Cd {cd_mean:.4f} +/- {cd_std:.5f}\n"
        f"CdA {cda_cm2:.1f} cm2  vs design {CDA_DESIGN_CM2:.1f}  (+{(cda_cm2 / CDA_DESIGN_CM2 - 1) * 100:.1f} %)\n"
        f"first 250 it clipped (startup transient, Cd to 15)",
        color=GREEN, fontsize=22, family="monospace", va="top",
    )
    fig.subplots_adjust(left=0.07, right=0.97, top=0.84, bottom=0.10)
    out = OUT / "sq2_cfd_convergence.png"
    fig.savefig(out, facecolor=BG)
    print("wrote", out, f"Cd_mean={cd_mean:.5f} std={cd_std:.5f} CdA={cda_cm2:.2f}")


# ---------------------------------------------------------------- receipt


def render_receipt() -> None:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f = lambda s: ImageFont.truetype(FONT, s)  # noqa: E731

    d.text((96, 80), "CFD receipt", font=f(56), fill=FG)
    d.text((96, 156), RUN_LABEL, font=f(26), fill=DIM)

    cols = [
        ("VALIDATION", "6:1 prolate spheroid", f"Cd {SPHEROID_CD:.4f} vs {SPHEROID_REF:.3f} ref",
         f"{(SPHEROID_CD / SPHEROID_REF - 1) * 100:+.1f} %", "Cl = 0.000 at alpha 0", GREEN),
        ("SQ-2 DRAG", "590 km/h, M 0.48, alpha 1.8 deg", f"CdA {CDA_CFD_CM2:.2f} vs {CDA_DESIGN_CM2:.2f} cm2 design",
         f"{(CDA_CFD_CM2 / CDA_DESIGN_CM2 - 1) * 100:+.1f} %", "fuselage 14.8 / pods 8.7 / struts 8.9", GREEN),
        ("MESH", "snappyHexMesh, full body", f"{ITERS} iterations, 10 ranks",
         f"{CELLS/1e6:.2f} M", f"{CELLS:,} cells, Cd std 0.00047 last 625 it", BLUE),
    ]
    x0, y0, cw, ch, gap = 96, 260, 544, 620, 48
    for i, (tag, sub, line, big, foot, color) in enumerate(cols):
        x = x0 + i * (cw + gap)
        d.rectangle([x, y0, x + cw, y0 + ch], outline="#1a1f2a", width=2)
        d.rectangle([x, y0, x + cw, y0 + 6], fill=color)
        d.text((x + 36, y0 + 44), tag, font=f(24), fill=DIM)
        d.text((x + 36, y0 + 88), sub, font=f(26), fill=FG)
        d.text((x + 36, y0 + 230), big, font=f(96), fill=color)
        d.text((x + 36, y0 + 370), line, font=f(26), fill=FG)
        d.text((x + 36, y0 + 420), foot, font=f(22), fill=DIM)

    d.text((96, 960), "Steady RANS, incompressible, k-omega SST, wall functions. External airframe drag only. "
                      "Source: speed-quad/docs/cfd/CFD_VALIDATION.md", font=f(20), fill=DIM)
    out = OUT / "sq2_cfd_receipt.png"
    img.save(out)
    print("wrote", out)


# ---------------------------------------------------------------- ken burns fallback


def render_kenburns() -> None:
    shots = ["sq2_l0_cp_iso.png", "sq2_l0_streamlines_symy.png", "sq2_l0_wallshear_iso.png"]
    per = 2.0
    nf = int(per * FPS)
    inputs, chains = [], []
    for i, name in enumerate(shots):
        inputs += ["-i", str(IMG_DIR / name)]  # one still frame; zoompan emits nf frames from it
        zoom = "if(eq(on,1),1.15,zoom+0.0015)" if i % 2 == 0 else "if(eq(on,1),1.25,zoom-0.0015)"
        chains.append(
            f"[{i}:v]scale=3840:-1,zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={nf}:s={W}x{H}:fps={FPS},setsar=1[v{i}]"
        )
    concat = "".join(f"[v{i}]" for i in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0[cat]"
    caption = caption_png(
        "kenburns",
        [
            ("SQ-2 CFD", 44, FG, 72, 64),
            (RUN_LABEL, 26, DIM, 72, 126),
            (f"590 km/h (M 0.48)  alpha 1.8 deg  {CELLS/1e6:.2f} M cells  {ITERS} it", 26, DIM, 72, 164),
            (f"CdA {CDA_CFD_CM2:.1f} cm2 vs {CDA_DESIGN_CM2:.1f} design (+1.4 %)   spheroid check -2.8 %", 30, GREEN, 72, 960),
        ],
        band=True,
    )
    ci = len(shots)
    out = OUT / "sq2_cfd_kenburns.mp4"
    run_ffmpeg(
        [*inputs, "-i", str(caption),
         "-filter_complex", ";".join(chains) + ";" + concat + f";[cat][{ci}:v]overlay=0:0[out]",
         "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", str(out)]
    )
    caption.unlink()
    print("wrote", out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    steps = {
        "convergence": render_convergence,
        "receipt": render_receipt,
        "kenburns": render_kenburns,
        "orbit": render_orbit,
    }
    for name, fn in steps.items():
        if what in ("all", name):
            fn()


if __name__ == "__main__":
    main()
