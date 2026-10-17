"""FORGE sourcing tool: turn a requirements dict into a resolved bill of materials.

The hard, real part of hardware engineering is sourcing: reading datasheets, getting
vendor STEP (or building an accurate stand-in from a dimensioned drawing), and checking
that the number in the drawing is the number in the CAD. This module does that for MJ-1
(the supersonic RC jet in ~/Workspace/developer/mj1) against its real vendor registry.

Two steps, honest about which is which:
  1. LLM step (Crusoe, role "spec" = Nemotron-Super): given requirements (thrust class,
     mass budget, avionics needs) it proposes the part list BY CATEGORY. It never invents
     part numbers or dimensions; it only says what categories the airframe needs.
  2. Deterministic step: resolve every category to the real registry in
     mj1/cad/kc_vendor.py (the @part table) and to the STEP file on disk. Each resolved
     part carries name, vendor, mass, dims measured live from the STEP bounding box
     (cadquery importStep -> BoundingBox), kind (REAL / STAND-IN / GENERATED), the
     datasheet/source string, the STEP path, and whether the dimension quoted in the
     builder docstring matches the measured bbox within 2 mm.

Then: a mass roll-up against the MJ-1 MTOW budget, and a datasheet citation check that
opens the JetCat P550 and KST X20 PDFs and asserts the extracted numbers match the
registry.

CLI:  python -m forge.sourcing --mj1
  prints the BOM + checks, writes ui/fixture/sourcing/bom.json and bom.png.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MJ1 = os.path.join(os.path.dirname(ROOT), "mj1")
MTOW_BUDGET_G = 25_000.0  # Boom Prize rule s3: fixed-wing MTOW <= 25 kg incl. fuel
BBOX_TOL_MM = 2.0

# AGENTS.md palette (dark studio look)
BG, GREEN, RED, BLUE, FG, DIM = "#06080d", "#2ee6a6", "#ff5f6d", "#4aa8ff", "#e6e9ef", "#7b8494"


# --------------------------------------------------------------------------- data model
@dataclass
class Part:
    name: str
    vendor: str            # registry category (jetcat, kst, matek, ...)
    function: str          # functional bucket the resolver assigned
    qty: int
    mass_g: float
    kind: str              # REAL | STAND-IN | GENERATED
    source: str            # datasheet / source string
    step: str              # path to the STEP on disk (relative to repo root if possible)
    dims_bbox_mm: list[float] | None        # measured from the STEP bounding box
    dims_declared_mm: list[float] | None    # body envelope quoted in the datasheet/registry
    dims_status: str | None                 # match | encloses | undersized | None (no envelope)
    dims_deltas_mm: list[float] | None      # bbox - body per axis (sorted desc)
    note: str = ""

    @property
    def total_mass_g(self) -> float:
        return self.mass_g * self.qty


# --------------------------------------------------------------------------- registry access
def _load_registry():
    """Import the MJ-1 vendor registry and return its @part metadata list.

    kc_vendor only builds geometry under __main__, so importing it is cheap and side
    effect free apart from making a couple of output dirs.
    """
    if MJ1 not in sys.path:
        sys.path.insert(0, MJ1)
    cad_dir = os.path.join(MJ1, "cad")
    if cad_dir not in sys.path:
        sys.path.insert(0, cad_dir)
    import kc_vendor  # noqa: E402

    return kc_vendor


# Functional bucket for each registry builder. The LLM proposes functional categories;
# this table is the deterministic ground truth the resolver maps them onto.
FUNCTION = {
    "jetcat_p550": "turbojet engine",
    "jetcat_pro_interface": "engine ECU interface",
    "jetcat_fuel_pump": "fuel system",
    "jetcat_hopper": "fuel system",
    "fuel_bag_3l": "fuel system",
    "kst_x20": "control servo",
    "matek_h743_wing": "flight controller",
    "matek_m10q": "GNSS + compass",
    "matek_aspd4525": "airspeed sensor",
    "pitot_tube": "airspeed sensor",
    "runcam_racer_nano3": "FPV camera",
    "runcam2_4k": "onboard camera",
    "crsf_nano_rx": "RC receiver",
    "vtx_58": "video transmitter",
    "lipo_4s_3300": "avionics battery",
    "shcs_m3x8": "fasteners",
    "shcs_m3x12": "fasteners",
    "shcs_m4x10": "fasteners",
    "bhcs_m3x6": "fasteners",
    "csk_m3x8": "fasteners",
    "insert_m3": "fasteners",
    "insert_m4": "fasteners",
    "nyloc_m3": "fasteners",
}


def _step_path(kc, meta):
    """Resolve the on-disk STEP for a registry part. Prefer the vendor STEP; the REAL
    parts keep their original filename rather than <builder>.step."""
    builder = meta["builder"]
    cat_dir = os.path.join(kc.VEND, meta["category"])
    if meta["kind"] == "REAL":
        # builder imports a specific file; recover it from the source string tail
        base = os.path.basename(meta["source"].split("(")[0].strip().rsplit("/", 1)[-1])
        base = base.replace("_step.zip", ".step")
        cand = os.path.join(cat_dir, base)
        if os.path.exists(cand):
            return cand
    cand = os.path.join(cat_dir, f"{builder}.step")
    if os.path.exists(cand):
        return cand
    placed = os.path.join(kc.OUT, f"{builder}_placed.step")
    return placed if os.path.exists(placed) else cand


# --------------------------------------------------------------------------- dims
_DIM3 = re.compile(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)")
_CYL = re.compile(r"\bd\s*(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)", re.I)
_OAL = re.compile(r"OAL\s*(\d+(?:\.\d+)?)", re.I)
_DIA = re.compile(r"(?:engine\s+)?dia(?:meter)?\s*(\d+(?:\.\d+)?)", re.I)


def declared_envelope(source: str, note: str, kind: str = "") -> list[float] | None:
    """Parse the part's BODY envelope (overall L x W x H in mm, sorted descending) from the
    registry source + docstring. Returns None when there is no clean envelope to check.

    Standard fasteners (GENERATED) are quoted as ISO head/socket parameters, not an
    envelope, so they are skipped. Among several quoted `A x B x C` groups the largest by
    volume wins (the overall body, never a hole pattern or sub-feature). Falls back to the
    `OAL ... dia` form (JetCat drawing) and then a `dD x L` cylinder.
    """
    if kind == "GENERATED":
        return None
    text = f"{source}  {note}"
    groups = [[float(g) for g in m.groups()] for m in _DIM3.finditer(text)]
    if groups:
        env = max(groups, key=lambda d: d[0] * d[1] * d[2])
        return sorted(env, reverse=True)
    oal, dia = _OAL.search(text), _DIA.search(text)
    if oal and dia:
        o, d = float(oal.group(1)), float(dia.group(1))
        return sorted([o, d, d], reverse=True)
    m = _CYL.search(text)
    if m:
        d, length = float(m.group(1)), float(m.group(2))
        return sorted([length, d, d], reverse=True)
    return None


def _bbox_mm(step_path: str) -> list[float] | None:
    try:
        import cadquery as cq

        shape = cq.importers.importStep(step_path)
        bb = shape.val().BoundingBox()
        return [round(bb.xlen, 1), round(bb.ylen, 1), round(bb.zlen, 1)]
    except Exception:
        return None


def dims_compare(declared, bbox, tol=BBOX_TOL_MM) -> dict | None:
    """Compare the declared body envelope against the measured STEP bounding box.

    The check is directional: a correct model's bbox ENCLOSES the quoted body (mounting
    ears, clamps, leads and connectors stick out past the bare body, so overshoot is
    expected and fine). The only real fault is an UNDERSIZED model whose bbox is smaller
    than the datasheet body by more than `tol` on some axis.

    status:
      match     -> every axis within tol (tight faithful envelope)
      encloses  -> bbox >= body on every axis, some axis larger (features protrude)
      undersized-> some axis is smaller than the quoted body by > tol (real fault)
    """
    if not declared or not bbox:
        return None
    d = sorted(declared, reverse=True)
    b = sorted(bbox, reverse=True)
    n = min(len(d), len(b))
    deltas = [round(b[i] - d[i], 1) for i in range(n)]
    min_delta = min(deltas)
    max_abs = max(abs(x) for x in deltas)
    if min_delta < -tol:
        status = "undersized"
    elif max_abs <= tol:
        status = "match"
    else:
        status = "encloses"
    return dict(status=status, deltas=deltas,
                max_overshoot=round(max(deltas), 1), min_delta=round(min_delta, 1))


# --------------------------------------------------------------------------- LLM step
SPEC_SYSTEM = (
    "You are the sourcing agent in FORGE, an AI hardware engineer. Given the requirements "
    "for one airframe you list the part CATEGORIES it needs to be buildable. You never "
    "invent part numbers, vendors, masses or dimensions: a deterministic resolver looks "
    "those up in a real vendor registry afterwards. Reply with STRICT JSON only, no prose, "
    "no code fences."
)


def propose_categories(requirements: dict, llm) -> tuple[list[dict], str]:
    """LLM step: propose the part list by category. Returns (categories, raw_reply)."""
    user = (
        "Requirements for this airframe:\n"
        + json.dumps(requirements, indent=2)
        + "\n\nList every functional part CATEGORY this airframe needs to fly the mission "
        "(propulsion, fuel system, flight control, navigation, air data, radio link, "
        "video, power, airframe fasteners). For each give a short 'need' reason and a "
        "quantity hint. Reply as JSON: "
        '{"parts": [{"category": "...", "need": "...", "qty": 1}, ...]}.'
    )
    from forge.llm import parse_json

    txt = llm.chat(
        "spec",
        [{"role": "system", "content": SPEC_SYSTEM}, {"role": "user", "content": user}],
        temperature=0.2,
        max_tokens=900,
        meta={"stage": "sourcing.propose_categories"},
    )
    obj = parse_json(txt) or {}
    parts = obj.get("parts", []) if isinstance(obj, dict) else []
    cats = [p for p in parts if isinstance(p, dict) and p.get("category")]
    return cats, txt


_STOP = {"and", "the", "a", "an", "for", "with", "of", "to", "system", "sensor", "module",
         "unit", "control", "onboard", "link"}


def _match_function(proposed_category: str, functions: set[str]) -> str | None:
    """Map an LLM-proposed category to a registry functional bucket by token overlap."""
    pw = {w for w in re.findall(r"[a-z0-9]+", proposed_category.lower()) if w not in _STOP}
    best, best_score = None, 0
    for fn in functions:
        fw = {w for w in re.findall(r"[a-z0-9]+", fn.lower()) if w not in _STOP}
        score = len(pw & fw)
        if score > best_score:
            best, best_score = fn, score
    return best if best_score else None


# --------------------------------------------------------------------------- resolve
def source_parts(requirements: dict, llm) -> list[Part]:
    """Resolve requirements to a bill of materials of real registry parts.

    LLM proposes categories; the deterministic resolver returns the full MJ-1 registry as
    resolved Part rows, each tagged with the proposed category it satisfies (or
    'not-proposed-by-agent' when the agent missed it). Every row's dimensions are measured
    live from its STEP file.
    """
    proposed, _ = propose_categories(requirements, llm)
    kc = _load_registry()

    functions = set(FUNCTION.values())
    # map each proposed category onto a functional bucket
    proposed_for_fn: dict[str, str] = {}
    for p in proposed:
        fn = _match_function(p["category"], functions)
        if fn and fn not in proposed_for_fn:
            proposed_for_fn[fn] = p["category"]

    out: list[Part] = []
    for meta in kc.PARTS:
        builder = meta["builder"]
        fn = FUNCTION.get(builder, meta["category"])
        step = _step_path(kc, meta)
        bbox = _bbox_mm(step) if os.path.exists(step) else None
        declared = declared_envelope(meta.get("source", ""), meta.get("note", ""), meta["kind"])
        cmp = dims_compare(declared, bbox)
        agent_tag = proposed_for_fn.get(fn, "not-proposed-by-agent")
        out.append(
            Part(
                name=meta["part"],
                vendor=meta["category"],
                function=fn,
                qty=int(meta.get("qty", 1)),
                mass_g=float(meta["mass_g"]),
                kind=meta["kind"],
                source=meta.get("source", ""),
                step=os.path.relpath(step, os.path.dirname(ROOT)) if os.path.exists(step) else step,
                dims_bbox_mm=bbox,
                dims_declared_mm=declared,
                dims_status=cmp["status"] if cmp else None,
                dims_deltas_mm=cmp["deltas"] if cmp else None,
                note=f"agent category: {agent_tag}",
            )
        )
    return out


# --------------------------------------------------------------------------- mass roll-up
def mass_rollup(parts: list[Part]) -> dict:
    by_fn: dict[str, float] = {}
    for p in parts:
        by_fn[p.function] = by_fn.get(p.function, 0.0) + p.total_mass_g
    total = sum(by_fn.values())
    return {
        "by_function_g": {k: round(v, 1) for k, v in sorted(by_fn.items(), key=lambda kv: -kv[1])},
        "total_g": round(total, 1),
        "mtow_budget_g": MTOW_BUDGET_G,
        "fraction_of_mtow": round(total / MTOW_BUDGET_G, 4),
        "note": "BOM covers bought-in parts (engine, avionics, servos, battery, fuel system, "
                "fasteners). Airframe structure and fuel load are sized separately in mj1/sizing.py.",
    }


# --------------------------------------------------------------------------- datasheet checks
def _pdftotext(pdf_path: str) -> str | None:
    if not os.path.exists(pdf_path):
        return None
    try:
        r = subprocess.run(["pdftotext", "-layout", pdf_path, "-"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return r.stdout
    except Exception:
        pass
    try:  # fallback: pypdf
        from pypdf import PdfReader

        return "\n".join((pg.extract_text() or "") for pg in PdfReader(pdf_path).pages)
    except Exception:
        return None


def _find_line(text: str, pattern: str):
    rx = re.compile(pattern, re.I)
    for line in text.splitlines():
        if rx.search(line):
            return line.strip()
    return None


def datasheet_check_p550(text: str) -> dict:
    """Extract thrust / mass / diameter from the JetCat P550 datasheet and compare to the
    registry values (550 N, 4900 g, 175 mm OD)."""
    checks = []

    def add(field_, expect, extracted_val, line, tol=0):
        ok = extracted_val is not None and abs(extracted_val - expect) <= tol
        checks.append(dict(field=field_, expected=expect, extracted=extracted_val,
                           ok=ok, evidence=line))

    m = re.search(r"Thrust range:\s*\d+\s*-\s*(\d+)\s*N", text, re.I)
    add("thrust_N", 550, float(m.group(1)) if m else None, _find_line(text, r"Thrust range"))
    m = re.search(r"Weight:\s*(\d+)\s*g", text, re.I)
    add("mass_g", 4900, float(m.group(1)) if m else None, _find_line(text, r"Weight:"))
    m = re.search(r"Diameter engine:\s*(\d+)\s*mm", text, re.I)
    add("diameter_mm", 175, float(m.group(1)) if m else None, _find_line(text, r"Diameter engine"))
    return dict(part="JetCat P550-PRO-GH turbine", checks=checks,
                ok=all(c["ok"] for c in checks))


def datasheet_check_kst(text: str) -> dict:
    """Extract case dimensions / mass from the KST X20 servo datasheet and compare to the
    registry values (40 x 20 x 40 mm case, 80 g)."""
    checks = []

    def add(field_, expect, extracted_val, line, tol=0):
        ok = extracted_val is not None and abs(extracted_val - expect) <= tol
        checks.append(dict(field=field_, expected=expect, extracted=extracted_val,
                           ok=ok, evidence=line))

    m = re.search(r"(\d+)\s*mm\s*\*\s*(\d+)\s*mm\s*\*\s*(\d+)\s*mm", text)
    dims = sorted((float(m.group(1)), float(m.group(2)), float(m.group(3))), reverse=True) if m else None
    line = _find_line(text, r"Case Dimensions")
    add("case_L_mm", 40, dims[0] if dims else None, line)
    add("case_H_mm", 40, dims[1] if dims else None, line)
    add("case_W_mm", 20, dims[2] if dims else None, line)
    m = re.search(r"Weight\s*\n?\s*(\d+)\s*g", text, re.I) or re.search(r"(\d+)\s*g\s*±", text)
    add("mass_g", 80, float(m.group(1)) if m else None, _find_line(text, r"Weight") or _find_line(text, r"80g"))
    return dict(part="KST X20-7.4-M-830 servo", checks=checks, ok=all(c["ok"] for c in checks))


def datasheet_checks() -> list[dict]:
    out = []
    jc = os.path.join(MJ1, "cad", "vendor", "jetcat", "P550-PRO-Datasheet.pdf")
    txt = _pdftotext(jc)
    if txt:
        out.append(datasheet_check_p550(txt))
    kst = os.path.join(MJ1, "cad", "vendor", "kst", "X20-7.4-M-830.pdf")
    txt = _pdftotext(kst)
    if txt:
        out.append(datasheet_check_kst(txt))
    return out


# --------------------------------------------------------------------------- reporting
def _mj1_requirements() -> dict:
    """Requirements the agent is handed, pulled from the MJ-1 mission (Boom Prize)."""
    return {
        "mission": "fixed-wing RC jet, accelerate M0.8 -> M1.05 in level flight, 5 s dash, land and refly",
        "thrust_class_N": "400-550 per engine (transonic acceleration of a ~20 kg airframe)",
        "mtow_budget_kg": 25,
        "avionics": ["flight controller", "GNSS", "airspeed/pitot", "RC link", "video", "FPV camera"],
        "actuation": "2+ high-torque metal-gear servos for elevon/control",
        "power": "avionics battery (engine is self-powered via its generator)",
        "fuel": "kerosene, ~3 L soft bag",
    }


def _dims_label(p: "Part") -> str:
    """One-cell summary of the envelope check for a part."""
    if p.dims_status is None:
        return "n/a"
    if p.dims_status == "match":
        return "match"
    over = max(p.dims_deltas_mm) if p.dims_deltas_mm else 0
    if p.dims_status == "encloses":
        return f"encl +{over:.0f}"
    return f"UNDER {min(p.dims_deltas_mm):.0f}"


def print_bom(parts: list[Part], rollup: dict, ds_checks: list[dict]):
    print("\nMJ-1 BILL OF MATERIALS  (resolved from mj1/cad/kc_vendor.py)\n")
    hdr = f"{'part':40s} {'vendor':10s} {'qty':>3s} {'mass g':>7s} {'kind':9s} {'bbox mm':>18s} {'envelope':>9s}"
    print(hdr)
    print("-" * len(hdr))
    for p in parts:
        bbox = "x".join(f"{d:.0f}" for d in p.dims_bbox_mm) if p.dims_bbox_mm else "?"
        print(f"{p.name[:40]:40s} {p.vendor:10s} {p.qty:>3d} {p.total_mass_g:>7.1f} "
              f"{p.kind:9s} {bbox:>18s} {_dims_label(p):>9s}")
    print("-" * len(hdr))
    print(f"{'TOTAL (bought-in parts)':40s} {'':10s} {'':>3s} {rollup['total_g']:>7.1f} g  "
          f"= {rollup['fraction_of_mtow'] * 100:.1f}% of the {MTOW_BUDGET_G / 1000:.0f} kg MTOW budget")

    print("\nmass by function (g):")
    for fn, g in rollup["by_function_g"].items():
        print(f"  {fn:26s} {g:8.1f}")

    under = [p for p in parts if p.dims_status == "undersized"]
    print(f"\nENVELOPE CHECK  (datasheet body dims vs live STEP bbox, tol {BBOX_TOL_MM:.0f} mm):")
    match_n = sum(1 for p in parts if p.dims_status == "match")
    encl_n = sum(1 for p in parts if p.dims_status == "encloses")
    na_n = sum(1 for p in parts if p.dims_status is None)
    print(f"  {match_n} tight match, {encl_n} bbox encloses body (mounts/leads protrude, expected), "
          f"{len(under)} undersized, {na_n} no body envelope quoted")
    if under:
        for p in under:
            print(f"  UNDERSIZED {p.name}: body {p.dims_declared_mm} vs bbox {p.dims_bbox_mm} "
                  f"(deltas {p.dims_deltas_mm} mm)")
    else:
        print("  no model is undersized vs its datasheet body: every STEP contains its part")

    print("\nDATASHEET CITATION CHECK:")
    for dc in ds_checks:
        print(f"  {dc['part']}: {'PASS' if dc['ok'] else 'FAIL'}")
        for c in dc["checks"]:
            flag = "ok " if c["ok"] else "XX "
            print(f"    {flag}{c['field']:14s} expect {c['expected']}  extracted {c['extracted']}")
            if c["evidence"]:
                print(f"        <- {c['evidence']}")


def write_bom_json(parts, rollup, ds_checks, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = dict(
        bom=[asdict(p) for p in parts],
        rollup=rollup,
        datasheet_checks=ds_checks,
        undersized_parts=[
            dict(name=p.name, body=p.dims_declared_mm, bbox=p.dims_bbox_mm, deltas_mm=p.dims_deltas_mm)
            for p in parts if p.dims_status == "undersized"
        ],
    )
    with open(path, "w") as f:
        json.dump(data, f, indent=1)
    print(f"\nwrote {os.path.relpath(path, ROOT)}")


def write_bom_png(parts, rollup, ds_checks, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = []
    status_col = {"match": GREEN, "encloses": BLUE, "undersized": RED, None: DIM}
    for p in parts:
        bbox = " x ".join(f"{d:.0f}" for d in p.dims_bbox_mm) if p.dims_bbox_mm else "-"
        dchk = _dims_label(p)
        dcol = status_col.get(p.dims_status, DIM)
        rows.append((p.name, p.vendor, p.qty, p.total_mass_g, p.kind, bbox, dchk, dcol))

    n = len(rows)
    fig_h = 2.0 + 0.34 * n
    fig, ax = plt.subplots(figsize=(15.5, fig_h), dpi=130)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_axis_off()

    ax.text(0.012, 0.975, "MJ-1  BILL OF MATERIALS", color=FG, fontsize=20,
            family="monospace", weight="bold", transform=ax.transAxes, va="top")
    frac = rollup["fraction_of_mtow"] * 100
    ax.text(0.012, 0.93,
            f"resolved from mj1/cad/kc_vendor.py   total {rollup['total_g']:.0f} g = "
            f"{frac:.1f}% of {MTOW_BUDGET_G / 1000:.0f} kg MTOW",
            color=DIM, fontsize=12, family="monospace", transform=ax.transAxes, va="top")

    cols = [("part", 0.012, "l"), ("vendor", 0.40, "l"), ("qty", 0.545, "r"),
            ("mass g", 0.625, "r"), ("kind", 0.66, "l"), ("bbox mm", 0.80, "l"), ("envelope", 0.995, "r")]
    y0, dy = 0.875, (0.86 / max(n + 2, 1))
    for label, x, align in cols:
        ax.text(x, y0, label, color=BLUE, fontsize=11, family="monospace",
                transform=ax.transAxes, va="top", ha={"l": "left", "r": "right"}[align])
    ax.plot([0.012, 0.995], [y0 - dy * 0.55] * 2, color=DIM, lw=0.8, transform=ax.transAxes)

    kind_col = {"REAL": GREEN, "STAND-IN": BLUE, "GENERATED": DIM}
    for i, (name, vendor, qty, mass, kind, bbox, dchk, dcol) in enumerate(rows):
        y = y0 - dy * (i + 1.4)
        ax.text(0.012, y, name[:40], color=FG, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top")
        ax.text(0.40, y, vendor, color=DIM, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top")
        ax.text(0.545, y, str(qty), color=FG, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top", ha="right")
        ax.text(0.625, y, f"{mass:.1f}", color=FG, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top", ha="right")
        ax.text(0.66, y, kind, color=kind_col.get(kind, FG), fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top")
        ax.text(0.80, y, bbox, color=DIM, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top")
        ax.text(0.995, y, dchk, color=dcol, fontsize=10.5, family="monospace",
                transform=ax.transAxes, va="top", ha="right")

    yb = y0 - dy * (n + 1.7)
    ax.plot([0.012, 0.995], [yb + dy * 0.4] * 2, color=DIM, lw=0.8, transform=ax.transAxes)
    ax.text(0.012, yb, f"TOTAL  {rollup['total_g']:.0f} g", color=FG, fontsize=12,
            family="monospace", weight="bold", transform=ax.transAxes, va="top")
    ds_line = "  ".join(f"{d['part'].split()[0]} {'PASS' if d['ok'] else 'FAIL'}" for d in ds_checks)
    ax.text(0.47, yb, "datasheet: " + ds_line, color=GREEN if all(d["ok"] for d in ds_checks) else RED,
            fontsize=11, family="monospace", transform=ax.transAxes, va="top")

    fig.savefig(path, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"wrote {os.path.relpath(path, ROOT)}")


# --------------------------------------------------------------------------- CLI
def run_mj1(write=True):
    from forge.llm import LLM

    llm = LLM(run_dir="runs/sourcing_mj1", budget_usd=0.5)
    req = _mj1_requirements()
    print("requirements:")
    print(json.dumps(req, indent=2))
    parts = source_parts(req, llm)
    rollup = mass_rollup(parts)
    ds = datasheet_checks()
    print_bom(parts, rollup, ds)
    print(f"\nllm spend ${llm.spent:.4f} over {llm.calls} call(s)")
    if write:
        out_dir = os.path.join(ROOT, "ui", "fixture", "sourcing")
        write_bom_json(parts, rollup, ds, os.path.join(out_dir, "bom.json"))
        write_bom_png(parts, rollup, ds, os.path.join(out_dir, "bom.png"))
    return parts, rollup, ds


def selftest():
    """Offline checks: no network, no LLM. Validates the deterministic machinery."""
    # envelope parsing: pick the largest body, skip fasteners, handle OAL/dia + cylinders
    assert declared_envelope("", "case 40 x 20 x 40 (L x W x H), ears 55") == [40.0, 40.0, 20.0]
    assert declared_envelope("54 x 36 x 13 mm, 30.5 x 30.5 d4 mount", "") == [54.0, 36.0, 13.0]
    assert declared_envelope("", "OAL 427, engine dia 175, nozzle d108 x 108") == [427.0, 175.0, 175.0]
    assert declared_envelope("d30 x 72 body, 4 mm barbs", "") == [72.0, 30.0, 30.0]
    assert declared_envelope("ISO 4762: dk 5.5, k 3", "", "GENERATED") is None
    assert declared_envelope("", "no dimensions here") is None
    # directional compare: body fully inside bbox -> encloses; tight -> match; short -> undersized
    assert dims_compare([40.0, 40.0, 20.0], [55.0, 46.5, 20.1])["status"] == "encloses"
    assert dims_compare([54.0, 36.0, 13.0], [54.0, 36.3, 12.7])["status"] == "match"
    assert dims_compare([50.0, 40.0, 20.0], [40.0, 20.0, 10.0])["status"] == "undersized"
    assert dims_compare(None, [1, 2, 3]) is None
    assert _match_function("flight controller", set(FUNCTION.values())) == "flight controller"
    assert _match_function("GNSS navigation", set(FUNCTION.values())) == "GNSS + compass"
    assert _match_function("something unrelated", set(FUNCTION.values())) is None
    print("sourcing selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    elif "--mj1" in sys.argv:
        run_mj1(write="--no-write" not in sys.argv)
    else:
        print("usage: python -m forge.sourcing --mj1 [--no-write] | --selftest")
