"""Build-history timelapse: how the agent stack designed MJ-1 and SQ-2, stage by stage, in the
order it actually happened. Every frame is a render the agents committed; the caption is the
real commit message and time from git. Crossfades between frames.

Run: /opt/miniconda3/bin/python3 docs/evidence/demo/make_history.py
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
MJ1 = "/Users/aayu/Workspace/developer/mj1"
SQ = "/Users/aayu/Workspace/developer/speed-quad"
W, H, BAR = 1920, 1080, 150
BG, INK, DIM, GREEN = (6, 8, 13), (232, 238, 245), (138, 148, 163), (46, 230, 166)
SANS = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
HOLD, FADE, FPS = 1.6, 0.4, 30

# (repo, image, step label). Caption time + message come from git.
STEPS = [
    (MJ1, "docs/img/kc_build/stage1_iso.png", "1  Outer mould line from reference images"),
    (MJ1, "docs/img/kc_build/stage4_engine_fit.png", "2  JetCat P550 turbine fitted from its datasheet"),
    (MJ1, "docs/img/kc_build/stage5_layout_iso.png", "3  16 sourced vendor parts placed"),
    (MJ1, "docs/img/kc_build/stage3a_engine_frames.png", "4  CNC engine frames cut around the parts"),
    (MJ1, "docs/img/kc_build/stage2_skin_iso.png", "5  Printable skin, split into sections"),
    (MJ1, "docs/img/kc_build/stage6_hero.png", "6  304 screw holes along every seam"),
    (MJ1, "docs/img/kc_build/stage3_skeleton_full.png", "7  Carbon + laser-cut skeleton, mass roll-up"),
    (MJ1, "docs/img/kc_build/final_cutaway.png", "8  Final cutaway"),
    (MJ1, "docs/img/kc_build/FINAL_vs_KingChaser.png", "9  Checked against the reference aircraft"),
    (MJ1, "docs/img/kc_build/stage2_exploded.png", "10 26 print sections, 335 screws, 266 inserts"),
    (SQ, "docs/img/sq2/render_iso.png", "SQ-2  first conceptual layout"),
    (SQ, "docs/img/progress/pod_node.png", "SQ-2  topology-optimised pod node, 10 g, CalculiX-checked"),
    (SQ, "docs/img/sq2/v3/fusion_v3_iso.png", "SQ-2  v3 in Fusion with vendor motors, ESCs, camera"),
    (SQ, "docs/img/cfd/sq2_l0_cp_iso.png", "SQ-2  full-body CFD, drag within 1.4 % of design"),
]


def git_caption(repo, path):
    r = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ad|%s",
                        "--date=format:%a %b %d %H:%M", "--", path],
                       capture_output=True, text=True)
    when, _, msg = r.stdout.strip().partition("|")
    if len(msg) > 120:
        msg = msg[:117].rstrip() + "..."
    return when, msg


def frame(src, label, when, msg):
    canvas = Image.new("RGB", (W, H), BG)
    im = Image.open(src).convert("RGB")
    im.thumbnail((W - 80, H - BAR - 40))
    canvas.paste(im, ((W - im.width) // 2, 20 + (H - BAR - 40 - im.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, H - BAR, W, H], fill=BG)
    d.text((60, H - BAR + 22), label, font=ImageFont.truetype(BOLD, 44), fill=INK)
    d.text((60, H - BAR + 82), f"{when}   ·   commit: {msg}", font=ImageFont.truetype(SANS, 24), fill=DIM)
    d.text((W - 430, 26), "designed by our agent stack", font=ImageFont.truetype(SANS, 26), fill=GREEN)
    return canvas


def main():
    seg = os.path.join(OUT_DIR, "history_seg")
    os.makedirs(seg, exist_ok=True)
    pngs = []
    for i, (repo, rel, label) in enumerate(STEPS):
        src = os.path.join(repo, rel)
        if not os.path.exists(src):
            continue
        when, msg = git_caption(repo, rel)
        p = os.path.join(seg, f"{i:02d}.png")
        frame(src, label, when, msg).save(p)
        pngs.append(p)
    # crossfade chain with xfade
    inputs, filt = [], []
    for p in pngs:
        inputs += ["-loop", "1", "-t", str(HOLD + FADE), "-i", p]
    prev = "[0:v]"
    offset = HOLD
    for i in range(1, len(pngs)):
        out = f"[v{i}]"
        filt.append(f"{prev}[{i}:v]xfade=transition=fade:duration={FADE}:offset={offset:.2f}{out}")
        prev = out
        offset += HOLD
    out = os.path.join(OUT_DIR, "FORGE_build_history.mp4")
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filt),
                    "-map", prev, "-r", str(FPS), "-c:v", "libx264", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", out], check=True)
    print(out, len(pngs), "frames")


if __name__ == "__main__":
    main()
