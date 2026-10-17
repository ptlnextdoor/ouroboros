#!/usr/bin/env python3
"""Deliverable 2 + 3: drive SolidCraft to build the FORGE bracket.

`bracket_to_solidcraft(params, out_dir)` builds the bracket NATIVELY in
SolidCraft from sketch + extrude commands (no imported STEP), saves a
.solidcraft design, exports a STEP, and snapshots a PNG. It then verifies the
native solid's volume against the cadquery reference (forge.blocks.build)
within 2%.

Frame convention (from forge/blocks.py):
  plate: x in [0, t_plate], y in [-width/2, width/2], z in [0, plate_h]
  arm:   x in [0, arm_len],  z in [plate_h - t_arm, plate_h], full width
  gusset:triangle in XZ at y=0, thickness `gusset` (symmetric about y=0)
  holes: 4 wall bolts (M5, axis X) + 1 motor hole (axis Z) + lightening holes

Native plan:
  * plate  : sketch rect on YZ (y,z), extrude +X by t_plate            (new)
  * arm    : sketch rect on YZ (y,z), extrude +X by arm_len            (join)
  * gusset : triangle on XZ (x,z) at y=0, symmetric extrude by gusset  (join)
  * bolts  : 4 circles on YZ, extrude cut through_all along X
  * motor+lighten: circles on XY (x,y), extrude cut through_all along Z

Live GUI drive (deliverable 3): with --live, launch/attach to the running
SolidCraft window via `solidcraft --control PORT` and push the same command
list through `solidcraft-cli mcp --connect`, so the audience watches the
bracket appear.

Usage:
  python -m forge.solidcraft [params.json]            # headless build + verify
  python -m forge.solidcraft --live [params.json]     # build in the live GUI
"""
import json
import os
import socket
import subprocess
import sys
import time

from forge import blocks

APP = "/Applications/SolidCraft.app/Contents/MacOS/SolidCraft"
CLI = "/Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli"
DEFAULT_PARAMS = {
    "t_plate": 4, "t_arm": 4, "plate_h": 50, "width": 30, "arm_len": 90,
    "gusset": 3, "gusset_len": 40, "gusset_h": 30, "lighten_n": 2, "lighten_d": 10,
}


# --------------------------------------------------------------------------
# command-list builder (shared by headless run and live MCP drive)
# --------------------------------------------------------------------------
def bracket_commands(params):
    """Return the SolidCraft command list that builds the bracket natively."""
    p = blocks.clamp(params)
    T, A, H, W, L = p["t_plate"], p["t_arm"], p["plate_h"], p["width"], p["arm_len"]
    cmds = [{"command": "file.new", "params": {"name": "FORGE bracket"}}]

    # plate: YZ sketch, extrude +X
    cmds += [
        {"command": "sketch.create", "params": {"plane": "YZ", "name": "plate"}},
        {"command": "sketch.rectangle.two_point",
         "params": {"sketch": "plate", "p0": [-W / 2, 0], "p1": [W / 2, H]}},
        {"command": "solid.extrude",
         "params": {"sketch": "plate", "distance": T, "operation": "new",
                    "body_name": "bracket"}},
    ]
    # arm: YZ sketch over [z: H-A..H], extrude +X by L, join
    cmds += [
        {"command": "sketch.create", "params": {"plane": "YZ", "name": "arm"}},
        {"command": "sketch.rectangle.two_point",
         "params": {"sketch": "arm", "p0": [-W / 2, H - A], "p1": [W / 2, H]}},
        {"command": "solid.extrude",
         "params": {"sketch": "arm", "distance": L, "operation": "join",
                    "targets": ["bracket"]}},
    ]
    # gusset: triangle in XZ at y=0, symmetric extrude by `gusset`
    gl, gh, g = min(p["gusset_len"], L - T), min(p["gusset_h"], H - A), p["gusset"]
    if g > 0 and p["gusset_len"] > 1 and p["gusset_h"] > 1:
        a = [T, H - A]
        b = [T + gl, H - A]
        c = [T, H - A - gh]
        cmds += [
            {"command": "sketch.create", "params": {"plane": "XZ", "name": "gusset"}},
            {"command": "sketch.line", "params": {"sketch": "gusset", "points": [a, b, c], "closed": True}},
            {"command": "solid.extrude",
             "params": {"sketch": "gusset", "distance": g, "direction": "symmetric",
                        "operation": "join", "targets": ["bracket"]}},
        ]

    # wall bolts: 4 circles on YZ, cut through_all along X (M5 clearance r=2.75)
    bolt_circles = []
    for zf in (0.3, 0.7):
        z = (H - A) * zf
        for y in (-W / 4, W / 4):
            bolt_circles.append((y, z))
    cmds.append({"command": "sketch.create", "params": {"plane": "YZ", "name": "bolts"}})
    for (y, z) in bolt_circles:
        cmds.append({"command": "sketch.circle.center",
                     "params": {"sketch": "bolts", "center": [y, z], "radius": 2.75}})
    cmds.append({"command": "solid.extrude",
                 "params": {"sketch": "bolts", "through_all": True,
                            "direction": "symmetric", "operation": "cut",
                            "targets": ["bracket"]}})

    # motor + lightening holes: circles on XY, cut through_all along Z
    mx, my = blocks.motor_xy(p)
    z_holes = [(mx, my, 3.25)]
    n, d = p["lighten_n"], p["lighten_d"]
    if n > 0 and d > 1:
        x0 = T + d / 2 + 2 + (p["gusset_len"] if p["gusset"] > 0 else 0)
        x1 = mx - 6.5 - d / 2
        if x1 > x0 and d < W - 4:
            for i in range(n):
                x = x0 + (x1 - x0) * (i + 0.5) / n
                z_holes.append((x, 0.0, d / 2))
    cmds.append({"command": "sketch.create", "params": {"plane": "XY", "name": "zholes"}})
    for (x, y, r) in z_holes:
        cmds.append({"command": "sketch.circle.center",
                     "params": {"sketch": "zholes", "center": [x, y], "radius": r}})
    cmds.append({"command": "solid.extrude",
                 "params": {"sketch": "zholes", "through_all": True,
                            "direction": "symmetric", "operation": "cut",
                            "targets": ["bracket"]}})
    return cmds, p


# --------------------------------------------------------------------------
# headless build + verify
# --------------------------------------------------------------------------
def bracket_to_solidcraft(params, out_dir):
    """Build the bracket natively in SolidCraft, save/export/snapshot, verify.

    Returns a dict report with the design/step/png paths and the native vs
    cadquery volume comparison.
    """
    os.makedirs(out_dir, exist_ok=True)
    cmds, p = bracket_commands(params)

    script_path = os.path.join(out_dir, "bracket.script.json")
    design_path = os.path.join(out_dir, "bracket.solidcraft")
    step_path = os.path.join(out_dir, "bracket.step")
    png_path = os.path.join(out_dir, "bracket.png")

    script = {"commands": cmds + [
        {"command": "file.export", "params": {"path": step_path, "format": "step"}},
    ]}
    json.dump(script, open(script_path, "w"), indent=1)

    # run headless; --results prints the final measurement (volume etc.)
    r = subprocess.run([CLI, "run", script_path, "--save", design_path, "--results"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"solidcraft run failed:\n{r.stderr[-1500:]}")
    try:
        results = json.loads(r.stdout)
    except json.JSONDecodeError:
        results = None

    # snapshot
    subprocess.run([CLI, "snapshot", "--in", design_path, "--out", png_path,
                    "--view", "iso", "--width", "1100", "--height", "800"],
                   capture_output=True, text=True)

    # volume: measure the exported STEP natively (authoritative) and compare
    # to the cadquery reference.
    native_vol = measure_step_volume(step_path)
    ref_vol = blocks.build(params).Volume()
    err = abs(native_vol - ref_vol) / ref_vol if ref_vol else float("nan")

    return {
        "params": p,
        "design": design_path,
        "step": step_path,
        "png": png_path,
        "script": script_path,
        "native_volume_mm3": native_vol,
        "cadquery_volume_mm3": ref_vol,
        "rel_error": err,
        "within_2pct": err <= 0.02,
    }


def measure_step_volume(step_path):
    """Re-open the exported STEP in SolidCraft and read its total volume."""
    out = subprocess.run([CLI, "eval", step_path], capture_output=True, text=True)
    txt = out.stdout
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        # eval of a .step alone may need a trivial measure script; fall back
        tmp = step_path + ".measure.json"
        json.dump({"commands": [{"command": "inspect.measure", "params": {}}]}, open(tmp, "w"))
        out = subprocess.run([CLI, "run", tmp, "--in", step_path, "--results"],
                             capture_output=True, text=True)
        d = json.loads(out.stdout)
    if isinstance(d, dict) and "total" in d:
        return d["total"]["volume_mm3"]
    if isinstance(d, dict) and "volume_mm3" in d:
        return d["volume_mm3"]
    raise RuntimeError(f"could not read volume from eval output:\n{txt[:800]}")


# --------------------------------------------------------------------------
# live GUI drive (deliverable 3)
# --------------------------------------------------------------------------
SUPPORT = os.path.expanduser("~/Library/Application Support/SolidCraft")


def _port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _read_token(port):
    path = os.path.join(SUPPORT, "control", f"{port}.token")
    return open(path).read().strip() if os.path.exists(path) else None


def ensure_live_app(port=7878):
    """Make sure a SolidCraft window is up with its control server listening.

    Returns (status, token). Launches the GUI binary with --control if the
    control server is not already listening on the port.
    """
    if _port_open(port):
        return "already-listening", _read_token(port)
    # launch the GUI with the control server; it must be the app binary, not
    # `open -a`, so we can pass --control. The user sees the window.
    subprocess.Popen([APP, "--control", str(port)],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if _port_open(port):
            time.sleep(1.0)                      # let it write the token file
            return "launched", _read_token(port)
        time.sleep(0.5)
    raise RuntimeError(f"SolidCraft control server never came up on :{port}")


def _mcp_batch(requests, port, token, timeout=120):
    """Send a list of JSON-RPC request dicts to the connected MCP server."""
    cmd = [CLI, "mcp", "--connect", f"127.0.0.1:{port}", "--allow-any-path"]
    if token:
        cmd += ["--token", token]
    payload = "\n".join(json.dumps(r) for r in requests) + "\n"
    proc = subprocess.run(cmd, input=payload, capture_output=True, text=True, timeout=timeout)
    replies = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                replies.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return replies, proc


def drive_live(params, port=7878, out_dir=None):
    """Push the bracket into the running GUI window via `mcp --connect`.

    Launches/attaches to the SolidCraft window, replays the native bracket
    command list through the MCP `execute` tool (the user watches it build),
    and grabs a window screenshot as proof.
    """
    status, token = ensure_live_app(port)
    cmds, p = bracket_commands(params)
    if out_dir is None:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "solidcraft", "shots")
    os.makedirs(out_dir, exist_ok=True)
    shot = os.path.join(out_dir, "live_bracket_window.png")

    requests = [{
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "forge.solidcraft", "version": "1"}},
    }]
    rid = 2
    for c in cmds:
        requests.append({
            "jsonrpc": "2.0", "id": rid, "method": "tools/call",
            "params": {"name": "execute",
                       "arguments": {"command": c["command"], "params": c.get("params", {})}},
        })
        rid += 1
    # fit the view and screenshot the live window as proof
    requests.append({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                     "params": {"name": "execute",
                                "arguments": {"command": "view.apply", "params": {"view": "iso"}}}})
    rid += 1
    requests.append({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                     "params": {"name": "screenshot", "arguments": {"path": shot}}})

    replies, proc = _mcp_batch(requests, port, token)
    errors = [r for r in replies if "error" in r]
    return {
        "status": status, "port": port, "token_used": bool(token),
        "commands_sent": len(cmds), "replies": len(replies),
        "errors": errors[:5], "window_screenshot": shot if os.path.exists(shot) else None,
        "returncode": proc.returncode,
    }


# --------------------------------------------------------------------------
# live MCP session (keeps the design in the window's memory across calls)
# --------------------------------------------------------------------------
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(REPO, "solidcraft", "shots")
SQ2_DESIGN = os.path.join(REPO, "solidcraft", "designs", "sq2_v3.solidcraft")

# the 4 tilt-pod props: world centre of each (from the v3 STL meshes); the
# motor/prop spin axis is world +X.
PROPS = {
    "pod_LU_prop:1": [332.8, 109.3, 117.8],
    "pod_RU_prop:1": [332.8, -109.4, 117.8],
    "pod_LD_prop:1": [332.8, 109.1, -117.8],
    "pod_RD_prop:1": [332.8, -108.9, -117.8],
}


def _exec(cmd, params=None, _id=0):
    return {"jsonrpc": "2.0", "id": _id, "method": "tools/call",
            "params": {"name": "execute",
                       "arguments": {"command": cmd, "params": params or {}}}}


def _tool(name, args, _id=0):
    return {"jsonrpc": "2.0", "id": _id, "method": "tools/call",
            "params": {"name": name, "arguments": args}}


def mcp_session(requests, port=7878, token=None, timeout=600):
    """Run a prebuilt list of MCP requests against the live window over ONE
    persistent connection, waiting for each reply before sending the next so a
    slow command (e.g. opening the 51 MB SQ-2) never makes later ones return
    `busy`. `requests` items may omit ids. Returns {id: result_text}, proc."""
    if token is None:
        token = _read_token(port)
    cmd = [CLI, "mcp", "--connect", f"127.0.0.1:{port}", "--allow-any-path"]
    if token:
        cmd += ["--token", token]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv():
        # read until a JSON object line (skip any blanks/log lines)
        while True:
            line = proc.stdout.readline()
            if line == "":
                return None
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

    out = {}
    send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
          "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                     "clientInfo": {"name": "forge.solidcraft", "version": "1"}}})
    recv()
    rid = 2
    for r in requests:
        r = dict(r); r["id"] = rid
        send(r)
        rep = recv()
        if rep is not None:
            res = rep.get("result", {})
            cont = res.get("content", []) if isinstance(res, dict) else []
            out[rid] = cont[0].get("text", "") if cont else res
        rid += 1
    try:
        proc.stdin.close()
        proc.wait(timeout=10)
    except Exception:                                # noqa: BLE001
        proc.kill()
    return out, proc


def _gif_from_frames(frame_paths, gif_path, fps=18):
    """Assemble a GIF from PNG frame paths with Pillow."""
    from PIL import Image
    frames = [Image.open(p).convert("RGB") for p in frame_paths if os.path.exists(p)]
    if not frames:
        return None
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=int(1000 / fps), loop=0, optimize=True)
    return gif_path


# --------------------------------------------------------------------------
# deliverable: live SQ-2 demo (open + camera + explode + prop spin + clearance)
# --------------------------------------------------------------------------
def demo_sq2(port=7878, design=None, frames=24, clearance=True):
    """The money shot: drive the live window through the whole SQ-2 story and
    export an animated GIF of the prop spin + explode for the video."""
    os.makedirs(SHOTS, exist_ok=True)
    design = design or SQ2_DESIGN
    token = _read_token(port)
    frame_dir = os.path.join(SHOTS, "sq2_demo_frames")
    os.makedirs(frame_dir, exist_ok=True)
    for f in os.listdir(frame_dir):
        os.remove(os.path.join(frame_dir, f))

    iso_cam = {"target": [300, 0, 0], "yaw": 0.9, "pitch": 0.5, "distance": 1600}
    reqs = [
        _exec("doc.open", {"path": design}),
        _exec("view.save", {"name": "demo_iso", "camera": iso_cam}),
        _exec("view.apply", {"view": "demo_iso"}),
        _tool("screenshot", {"path": os.path.join(SHOTS, "sq2_demo_assembled.png"),
                             "source": "model", "width": 1280, "height": 800}),
    ]
    # prop spin: rotate all 4 props about world X a little each frame, shoot a frame
    frame_paths = []
    step_deg = 360.0 / frames
    for i in range(frames):
        for occ, ctr in PROPS.items():
            reqs.append(_exec("occurrence.move",
                              {"occurrence": occ, "space": "world", "axis": [1, 0, 0],
                               "angle": f"{step_deg} deg", "origin": ctr}))
        fp = os.path.join(frame_dir, f"spin_{i:03d}.png")
        frame_paths.append(fp)
        reqs.append(_tool("screenshot", {"path": fp, "source": "model",
                                         "width": 900, "height": 600}))
    # explode sequence (3 held frames at growing scale)
    explode_paths = []
    for j, sc in enumerate((0.6, 1.2, 2.0)):
        reqs.append(_exec("explode.create", {"name": f"blown{j}", "scale": sc}))
        reqs.append(_exec("explode.show", {"view": f"blown{j}"}))
        ep = os.path.join(frame_dir, f"explode_{j:03d}.png")
        explode_paths.append(ep)
        reqs.append(_tool("screenshot", {"path": ep, "source": "model",
                                         "width": 900, "height": 600}))
    reqs.append(_tool("screenshot", {"path": os.path.join(SHOTS, "sq2_demo_exploded.png"),
                                     "source": "model", "width": 1280, "height": 800}))
    reqs.append(_exec("explode.show", {}))  # reassemble
    # final window screenshot as proof
    reqs.append(_tool("screenshot", {"path": os.path.join(SHOTS, "sq2_demo_window.png")}))

    out, proc = mcp_session(reqs, port=port, token=token, timeout=600)

    # clearance (0.15 feature): scoped, runs on the resident design in a short
    # 2nd session so the long GIF batch isn't held up.
    clearance_report = None
    if clearance:
        try:
            cout, _ = mcp_session([
                _exec("doc.open", {"path": design}),
                _exec("inspect.clearance", {"skip_within": "component", "nearest": 1}),
            ], port=port, token=token, timeout=600)
            clearance_report = cout.get(3)
        except Exception as e:                       # noqa: BLE001
            clearance_report = f"clearance skipped: {e}"

    # assemble GIFs
    spin_gif = _gif_from_frames(frame_paths, os.path.join(SHOTS, "sq2_prop_spin.gif"), fps=18)
    all_gif = _gif_from_frames(frame_paths + explode_paths * 3,
                               os.path.join(SHOTS, "sq2_spin_explode.gif"), fps=16)
    return {
        "design": design, "frames": len(frame_paths),
        "spin_gif": spin_gif, "spin_explode_gif": all_gif,
        "assembled_png": os.path.join(SHOTS, "sq2_demo_assembled.png"),
        "exploded_png": os.path.join(SHOTS, "sq2_demo_exploded.png"),
        "window_png": os.path.join(SHOTS, "sq2_demo_window.png"),
        "clearance": (clearance_report[:1200] if isinstance(clearance_report, str)
                      else clearance_report),
        "returncode": proc.returncode,
    }


# --------------------------------------------------------------------------
# deliverable: FORGE loop -> SolidCraft (growing row of PASS/FAIL brackets)
# --------------------------------------------------------------------------
_ROW = {"n": 0}  # how many verdicts have been pushed this session (process-local)


def push_verdict(params, verdict, port=7878, index=None, pitch=70.0):
    """Push one bracket design into the live window as a new component placed
    in a growing row, coloured green for PASS and red for FAIL.

    `verdict` is a dict or string; PASS iff str(verdict).upper() contains PASS.
    `index` positions it in the row (defaults to an auto-incrementing counter).
    """
    token = _read_token(port)
    if index is None:
        index = _ROW["n"]
        _ROW["n"] += 1
    ok = "PASS" in str(verdict).upper()
    color = [60, 200, 90] if ok else [210, 60, 60]
    body = f"bracket_{index:02d}"
    comp = f"iter_{index:02d}_{'PASS' if ok else 'FAIL'}"
    shift = index * pitch

    cmds, p = bracket_commands(params)
    # route this build into its own component so brackets don't fuse together
    reqs = [_exec("component.create", {"name": comp, "activate": True})]
    for c in cmds:
        if c["command"] == "file.new":
            continue                                 # keep the running design
        pr = dict(c.get("params", {}))
        if c["command"] == "solid.extrude" and pr.get("operation") == "new":
            pr["body_name"] = body
        if "targets" in pr:
            pr["targets"] = [body]
        reqs.append(_exec(c["command"], pr))
    # slide the whole new component along +Y so it sits next to the last one
    reqs.append(_exec("solid.move", {"bodies": [body], "translate": [0, shift, 0]}))
    reqs.append(_exec("appearance.assign", {"bodies": [body], "color": color, "opacity": 1,
                                            "pbr": {"metallic": 0.0, "roughness": 0.6,
                                                    "dielectric_ior": 1.5}}))
    reqs.append(_tool("screenshot", {"path": os.path.join(SHOTS, "forge_row_window.png")}))
    out, proc = mcp_session(reqs, port=port, token=token, timeout=180)
    return {"index": index, "verdict": "PASS" if ok else "FAIL", "component": comp,
            "shift_mm": shift, "returncode": proc.returncode}


# --------------------------------------------------------------------------
def main(argv):
    args = [a for a in argv if not a.startswith("--")]

    if "--demo" in argv:
        rep = demo_sq2()
        print(json.dumps(rep, indent=1))
        return 0

    params = json.load(open(args[0])) if args else dict(DEFAULT_PARAMS)
    if "--live" in argv:
        rep = drive_live(params)
        print(json.dumps(rep, indent=1))
        return 0

    out_dir = os.path.join(REPO, "solidcraft", "forge_bracket")
    rep = bracket_to_solidcraft(params, out_dir)
    print(json.dumps(rep, indent=1))
    print(f"\nnative={rep['native_volume_mm3']:.1f}  cadquery={rep['cadquery_volume_mm3']:.1f}"
          f"  err={rep['rel_error']*100:.2f}%  within_2pct={rep['within_2pct']}")
    return 0 if rep["within_2pct"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
