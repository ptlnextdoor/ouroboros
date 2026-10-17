"""MJ-1 Fusion bridge: show the real jet, not a hand-built part.

The MJ-1 and SQ-2 designs already live as Fusion documents (built earlier by the
agent stack over this same :9876 socket). The Studio demo's job is to *show*
them: activate the right document, set a clean view, optionally hide the skin so
the vendor parts + skeleton read, and pull back a high-res viewport PNG.

We never claim MJ-1 has flown or hit Mach 1. The numbers we surface come from
mj1.sizing and tools.area_rule run live; the honest verdict (best area-ruled
layout is ~10 % short of thrust for M1.05) is carried through verbatim.
"""
import base64
import json
import os

from studio import fusion  # reuse call/_exec/render plumbing

MJ1_REPO = "/Users/aayu/Workspace/developer/mj1"


def _activate(doc_prefix):
    code = f'''
import adsk.core, json
app = adsk.core.Application.get()
target = None
for i in range(app.documents.count):
    d = app.documents.item(i)
    if d.name.startswith({doc_prefix!r}):
        target = d; break
if target is not None and app.activeDocument is not target:
    target.activate()
json.dumps({{"active": app.activeDocument.name}})
'''
    return fusion._exec("import json\n" + code, 90.0)


def _set_skin_visible(visible, patterns=("SKIN", "Skin")):
    """Show/hide skin-like occurrences in the active MJ1 design so the vendor
    parts + skeleton are visible. Best effort, returns what it toggled."""
    code = f'''
import adsk.core, adsk.fusion, json
app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent
want = {visible!r}
pats = {list(patterns)!r}
touched = []
def walk(occs):
    for i in range(occs.count):
        oc = occs.item(i)
        nm = oc.component.name
        if any(p.lower() in nm.lower() for p in pats):
            try:
                oc.isLightBulbOn = want
                touched.append(nm)
            except Exception:
                pass
        try:
            walk(oc.childOccurrences)
        except Exception:
            pass
walk(root.occurrences)
json.dumps({{"touched": touched, "visible": want}})
'''
    return fusion._exec("import json\n" + code, 90.0)


def capture(doc_prefix, view="iso", width=2400, height=1500, hide_skin=False,
            save_path=None):
    """Activate a doc, optionally hide its skin, fit, and return base64 PNG."""
    _activate(doc_prefix)
    toggled = None
    if hide_skin:
        toggled = _set_skin_visible(False)
    png = fusion.render_png(view=view, width=width, height=height)
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f:
            f.write(base64.b64decode(png))
    return dict(image_base64=png, toggled=toggled, saved=save_path)


def show_mj1(view="iso", hide_skin=False, width=2400, height=1500):
    return capture("MJ1", view=view, width=width, height=height, hide_skin=hide_skin)


def show_sq2(view="iso", width=2400, height=1500):
    return capture("Jet", view=view, width=width, height=height)


def components():
    """Component occurrences of the active (MJ1) design, for the 'in Fusion' note."""
    code = '''
import adsk.core, adsk.fusion, json
app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent
names = [root.occurrences.item(i).component.name for i in range(root.occurrences.count)]
json.dumps({"active": app.activeDocument.name, "components": names})
'''
    raw = fusion._exec("import json\n" + code, 90.0)
    return json.loads(raw) if isinstance(raw, str) else raw


if __name__ == "__main__":
    import sys
    if "--capture-evidence" in sys.argv:
        ev = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "evidence", "fusion"))
        print("MJ1 iso       ->", capture("MJ1", "iso", save_path=os.path.join(ev, "mj1_iso.png"))["saved"])
        print("MJ1 skin off  ->", capture("MJ1", "iso", hide_skin=True, save_path=os.path.join(ev, "mj1_skinoff.png"))["saved"])
        print("SQ-2 iso      ->", capture("Jet", "iso", save_path=os.path.join(ev, "sq2_iso.png"))["saved"])
    elif "--selftest" in sys.argv:
        print(json.dumps(components(), indent=2))
