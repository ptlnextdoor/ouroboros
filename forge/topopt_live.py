"""Live capture + animation of the SQ-2 pod-node topology optimisation.

Runs the real, validated 3D SIMP optimiser from speed-quad (sq2.topopt) without
editing any speed-quad file: it monkeypatches FE.solve to snapshot the physical
density field at every iteration, reconstructs it from the penalised stiffness
(Ee = Emin + xp**p * (1 - Emin)  ->  xp = ((Ee - Emin)/(1 - Emin))**(1/p)),
then renders the material "growing" into the optimal shape.

Outputs (ui/fixture/topopt/):
  frames/iter_###.png   per-iteration iso-surface render (dark bg, green material)
  growth.mp4, growth.gif animation stitched with ffmpeg
  convergence.png       compliance + grey fraction vs iteration
  pod_node_final.stl    thresholded final shape (for SolidCraft)
  live.json             history + headline numbers (mass, compliance, vm_max)

Run: python3 forge/topopt_live.py --h 1.5 --vf 0.12 --iters 40 --every 2
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SPEED_QUAD = "/Users/aayu/Workspace/developer/speed-quad"
OUT = os.path.join(REPO, "ui/fixture/topopt")

# material / colours (AGENTS.md house style)
BG = "#06080d"
GREEN = "#2ee6a6"
BLUE = "#4aa8ff"
RHO_ALSI = 2.68e-3   # g/mm^3, AlSi10Mg (envelope/mass comparison)


def _load_topopt():
    """Import sq2.topopt with speed-quad on the path, read-only."""
    if SPEED_QUAD not in sys.path:
        sys.path.insert(0, SPEED_QUAD)
    from sq2 import topopt as T
    return T


def run_capture(h, vf, iters, penal=3.0):
    """Run the real optimiser, capturing the physical density every iteration."""
    T = _load_topopt()
    frames: list[np.ndarray] = []
    orig_solve = T.FE.solve
    Emin = 1e-6

    def solve_hook(self, Ee_scaled, Fs, x0s=None, tol=1e-8):
        # optimise() calls fe.solve(Ee * E_AL, ...) each iteration; invert to xp
        Ee = np.asarray(Ee_scaled) / T.E_AL
        xp = np.clip((Ee - Emin) / (1 - Emin), 0.0, 1.0) ** (1.0 / penal)
        frames.append(xp.copy())
        return orig_solve(self, Ee_scaled, Fs, x0s, tol)

    T.FE.solve = solve_hook
    try:
        dom, fe, lcs, meta, Fs, xp_final, hist = T.optimise(
            h=h, vf=vf, iters=iters, penal=penal, log=lambda s: print(s, flush=True))
    finally:
        T.FE.solve = orig_solve  # restore before check() re-solves on the binary design

    rep = T.check(dom, fe, lcs, Fs, xp_final)
    stl_path = os.path.join(OUT, "pod_node_final.stl")
    rep.update(T.export_stl(dom, xp_final, stl_path))
    return dict(T=T, dom=dom, frames=frames, hist=hist, xp_final=xp_final,
                report=rep, lcs=lcs, meta=meta)


def _surface(xp, dom, thr=0.5):
    """Marching-cubes iso-surface of a density grid, in part coordinates (mm)."""
    from skimage.measure import marching_cubes
    g = np.pad(xp.reshape(dom.nx, dom.ny, dom.nz), 1)
    if g.max() < thr:
        return None, None
    v, f, _, _ = marching_cubes(g, level=thr, spacing=(dom.h,) * 3)
    v = v - dom.h + np.array([dom.h / 2, dom.h / 2 - dom.R_in, dom.h / 2 - dom.R_in])
    return v, f


def render_frames(run, every):
    """Render each captured density field as an iso-surface PNG, fixed camera."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    dom = run["dom"]
    frames = run["frames"]
    hist = run["hist"]
    fdir = os.path.join(OUT, "frames")
    os.makedirs(fdir, exist_ok=True)
    for old in os.listdir(fdir):
        if old.endswith(".png"):
            os.remove(os.path.join(fdir, old))

    Lx, W = dom.Lx, 2 * dom.R_in
    idxs = list(range(0, len(frames), every))
    if idxs[-1] != len(frames) - 1:
        idxs.append(len(frames) - 1)          # always render the converged frame
    png_paths = []
    for n, i in enumerate(idxs):
        v, f = _surface(frames[i], dom)
        fig = plt.figure(figsize=(8, 8), dpi=120)
        fig.patch.set_facecolor(BG)
        ax = fig.add_subplot(111, projection="3d")
        ax.set_facecolor(BG)
        if v is not None:
            mesh = Poly3DCollection(v[f], alpha=1.0)
            mesh.set_facecolor(GREEN)
            mesh.set_edgecolor((0, 0, 0, 0.12))
            mesh.set_linewidth(0.15)
            ax.add_collection3d(mesh)
        ax.set_xlim(0, Lx); ax.set_ylim(-W / 2, W / 2); ax.set_zlim(-W / 2, W / 2)
        ax.set_box_aspect((Lx, W, W))
        ax.view_init(elev=22, azim=-58)
        ax.set_axis_off()
        c = hist[i]["c"]; grey = hist[i]["grey"]
        ax.text2D(0.04, 0.95, f"iteration {hist[i]['it']:02d}", transform=ax.transAxes,
                  color="#e8eef5", fontsize=15, family="monospace")
        ax.text2D(0.04, 0.90, f"compliance {c:8.1f} N mm", transform=ax.transAxes,
                  color=GREEN, fontsize=12, family="monospace")
        ax.text2D(0.04, 0.865, f"grey fraction {grey:.2f}", transform=ax.transAxes,
                  color=BLUE, fontsize=11, family="monospace")
        p = os.path.join(fdir, f"iter_{n:03d}.png")
        fig.savefig(p, facecolor=BG, bbox_inches="tight", pad_inches=0.2)
        plt.close(fig)
        png_paths.append(p)
        print(f"  rendered frame {n+1}/{len(idxs)} (iter {hist[i]['it']})", flush=True)
    return fdir, png_paths


def convergence_plot(run):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hist = run["hist"]
    it = [d["it"] for d in hist]
    c = [d["c"] for d in hist]
    grey = [d["grey"] for d in hist]
    fig, ax1 = plt.subplots(figsize=(9, 5), dpi=130)
    fig.patch.set_facecolor(BG); ax1.set_facecolor(BG)
    ax1.plot(it, c, color=GREEN, lw=2.2, marker="o", ms=3, label="compliance")
    ax1.set_xlabel("iteration", color="#e8eef5", family="monospace")
    ax1.set_ylabel("compliance (N mm)", color=GREEN, family="monospace")
    ax1.tick_params(colors="#9fb0c3")
    for s in ax1.spines.values():
        s.set_color("#243041")
    ax2 = ax1.twinx()
    ax2.plot(it, grey, color=BLUE, lw=1.8, ls="--", label="grey fraction")
    ax2.set_ylabel("grey fraction", color=BLUE, family="monospace")
    ax2.tick_params(colors="#9fb0c3")
    ax2.set_ylim(0, max(0.05, max(grey) * 1.2))
    ax1.set_title("pod-node SIMP convergence", color="#e8eef5", family="monospace")
    p = os.path.join(OUT, "convergence.png")
    fig.tight_layout()
    fig.savefig(p, facecolor=BG)
    plt.close(fig)
    print(f"  wrote {p}", flush=True)
    return p


def stitch(fdir):
    """Stitch PNG frames to MP4 + GIF with ffmpeg (hold last frame a beat)."""
    mp4 = os.path.join(OUT, "growth.mp4")
    gif = os.path.join(OUT, "growth.gif")
    pattern = os.path.join(fdir, "iter_%03d.png")
    # mp4: 6 fps, pad to even dims for yuv420p
    subprocess.run([
        "ffmpeg", "-y", "-framerate", "6", "-i", pattern,
        "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-pix_fmt", "yuv420p", mp4],
        check=True, capture_output=True)
    # gif via palette for clean colour
    palette = os.path.join(fdir, "_palette.png")
    subprocess.run(["ffmpeg", "-y", "-framerate", "6", "-i", pattern,
                    "-vf", "palettegen", palette], check=True, capture_output=True)
    subprocess.run(["ffmpeg", "-y", "-framerate", "6", "-i", pattern, "-i", palette,
                    "-lavfi", "paletteuse", gif], check=True, capture_output=True)
    os.remove(palette)
    print(f"  wrote {mp4}\n  wrote {gif}", flush=True)
    return mp4, gif


def headline(run, args):
    """Honest headline numbers: envelope solid vs optimized, compliance, vm_max."""
    dom = run["dom"]
    rep = run["report"]
    envelope_mm3 = float(dom.Lx * (2 * dom.R_in) ** 2)   # bounding box
    envelope_mass = envelope_mm3 * RHO_ALSI
    # optimized mass from the watertight mesh volume, same density as the envelope
    opt_mass = rep["stl_volume_mm3"] * RHO_ALSI
    cases = rep["cases"]
    vm_body = max(v["vm_max_body"] for v in cases.values())
    vm_all = max(v["vm_max_all"] for v in cases.values())
    c_first = run["hist"][0]["c"]
    c_last = run["hist"][-1]["c"]
    ccx_path = os.path.join(SPEED_QUAD, "sq2/out/pod_node_ccx_thrust.json")
    ccx = json.load(open(ccx_path)) if os.path.exists(ccx_path) else {}
    return dict(
        grid=[dom.nx, dom.ny, dom.nz], h_mm=dom.h, vf=args.vf, iters_run=len(run["hist"]),
        envelope_mm3=envelope_mm3, envelope_mass_g=envelope_mass,
        optimized_mass_g=opt_mass, mass_reduction_pct=100 * (1 - opt_mass / envelope_mass),
        compliance_first=c_first, compliance_final=c_last,
        vm_max_body_mpa=vm_body, vm_max_all_mpa=vm_all,
        min_MS_body=min(v["MS_body"] for v in cases.values()),
        rho_g_cc=RHO_ALSI * 1e3, material="AlSi10Mg LPBF",
        calculix_check=ccx, report=rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--h", type=float, default=1.5)
    ap.add_argument("--vf", type=float, default=0.12)
    ap.add_argument("--iters", type=int, default=40)
    ap.add_argument("--every", type=int, default=2, help="render every Nth captured iter")
    ap.add_argument("--no-render", action="store_true")
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    print(f"[topopt_live] running real sq2.topopt  h={args.h} vf={args.vf} iters={args.iters}")
    run = run_capture(args.h, args.vf, args.iters)
    print(f"[topopt_live] captured {len(run['frames'])} iterations")

    head = headline(run, args)
    json.dump(head, open(os.path.join(OUT, "live.json"), "w"), indent=1, default=float)
    print(f"[topopt_live] mass: envelope {head['envelope_mass_g']:.1f} g -> "
          f"optimized {head['optimized_mass_g']:.1f} g "
          f"({head['mass_reduction_pct']:.1f}% lighter)")
    print(f"[topopt_live] compliance {head['compliance_first']:.1f} -> "
          f"{head['compliance_final']:.1f} N mm   vm_max_body {head['vm_max_body_mpa']:.1f} MPa")

    if not args.no_render:
        fdir, _ = render_frames(run, args.every)
        convergence_plot(run)
        stitch(fdir)
    print("[topopt_live] done")


if __name__ == "__main__":
    main()
