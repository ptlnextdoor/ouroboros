"""Partial demo reel for Krish (not the final video).

Every frame is a real artifact from this repo or mj1/speed-quad. Captions are drawn with PIL
(the installed ffmpeg has no drawtext filter), then ffmpeg stitches the segments.
Run: /opt/miniconda3/bin/python3 docs/evidence/partial/make_reel.py
"""
import os
import subprocess

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
R = "/Users/aayu/Workspace/developer/recursive-agents-hack"
M = "/Users/aayu/Workspace/developer/mj1/docs/img/kc_build"
SEG = os.path.join(HERE, "seg")
BG, INK, DIM, GREEN = (6, 8, 13), (232, 238, 245), (138, 148, 163), (46, 230, 166)
W, H, BAR = 1920, 1080, 100
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def frame_from(src, caption):
    canvas = Image.new("RGB", (W, H), BG)
    if src:
        im = Image.open(src).convert("RGB")
        im.thumbnail((W, H - BAR))
        canvas.paste(im, ((W - im.width) // 2, (H - BAR - im.height) // 2))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, H - BAR, W, H], fill=BG)
    d.text((60, H - BAR + 32), caption, font=font(36), fill=INK)
    return canvas


def title_card(lines):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    for text, size, color, bold, y in lines:
        f = font(size, bold)
        tw = d.textlength(text, font=f)
        d.text(((W - tw) / 2, y), text, font=f, fill=color)
    return canvas


def ff(args):
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", *args], check=True)


def still_seg(img, seconds, out):
    png = out.replace(".mp4", ".png")
    img.save(png)
    ff(["-loop", "1", "-t", str(seconds), "-i", png, "-vf", "fps=30,format=yuv420p", out])


def clip_seg(src, seconds, caption, out):
    bar = frame_from(None, caption).crop((0, H - BAR, W, H))
    bar_png = out.replace(".mp4", "_bar.png")
    bar.save(bar_png)
    ff(["-t", str(seconds), "-i", src, "-i", bar_png, "-an", "-filter_complex",
        f"[0:v]scale={W}:{H - BAR}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:0:color=0x06080d[v];[v][1:v]overlay=0:{H - BAR},fps=30,format=yuv420p",
        out])


def main():
    os.makedirs(SEG, exist_ok=True)
    segs = []

    def add(name):
        p = os.path.join(SEG, name)
        segs.append(p)
        return p

    still_seg(title_card([
        ("FORGE", 140, GREEN, True, 380),
        ("an AI hardware engineer", 44, INK, False, 560),
        ("partial cut for the video, not the final demo", 30, DIM, False, 630),
    ]), 3, add("00.mp4"))
    stills = [
        (f"{R}/docs/evidence/fusion/fusion_mj1_current.png", 4,
         "MJ-1 supersonic RC jet, open in Fusion 360, captured by the agent through the Fusion bridge"),
        (f"{R}/docs/evidence/fusion/mj1_skinoff.png", 4,
         "Skin off: airframe designed around parts the agent sourced (JetCat P550 turbine, servos, FC, fuel)"),
        (f"{M}/vendor_sheet.png", 4,
         "23 sourced parts, each with a datasheet or drawing source, tagged REAL or STAND-IN"),
        (f"{M}/final_cutaway.png", 3,
         "Cutaway: CNC engine frames, carbon rods, laser-cut plates, avionics stack"),
        (f"{R}/docs/evidence/fusion/fusion_sq2_jet_current.png", 4,
         "SQ-2: 590 km/h electric quad, same agent stack, 78 CAD parts, rendered in Fusion"),
    ]
    for i, (src, sec, cap) in enumerate(stills, start=1):
        still_seg(frame_from(src, cap), sec, add(f"{i:02d}.mp4"))
    clip_seg(f"{R}/ui/fixture/cfd/sq2_cfd_orbit.mp4", 5,
             "CFD: OpenFOAM RANS, 3.55 M cells, drag within 1.4 % of the design value", add("06.mp4"))
    still_seg(frame_from(f"{R}/ui/fixture/sq2_review/pod_node_vm.png",
                         "Referee: CalculiX FEA on the real 7075 pod node, 20 g pod-down case"), 3, add("07.mp4"))
    clip_seg(f"{R}/ui/fixture/topopt/growth.mp4", 4,
             "Topology optimization: 154 g billet to a 15 g node", add("08.mp4"))
    still_seg(frame_from(f"{R}/ui/shots/loop_1920x1080.png",
                         "The loop: Crusoe agents design, a physics referee checks hidden loads, the playbook keeps only what works"),
              5, add("09.mp4"))
    still_seg(title_card([
        ("on held-out parts it never saw", 40, DIM, False, 330),
        ("v0  5 of 6 solved      v2  6 of 6 first try, 17 % lighter", 56, GREEN, True, 420),
        ("587 Crusoe calls today  ·  $0.29 total  ·  about half a cent per verified part", 40, INK, False, 560),
    ]), 4, add("10.mp4"))

    listfile = os.path.join(SEG, "list.txt")
    with open(listfile, "w") as f:
        f.writelines(f"file '{p}'\n" for p in segs)
    out = os.path.join(HERE, "FORGE_partial_reel.mp4")
    ff(["-f", "concat", "-safe", "0", "-i", listfile, "-c:v", "libx264", "-crf", "22",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", out])
    print(out)


if __name__ == "__main__":
    main()
