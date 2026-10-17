"""Edit tools for the open Fusion design (MJ-1): list parts, recolor, show/hide.

All calls go through studio.fusion._exec (module lock + retry), serially.
"""
import json
import re

from studio import fusion

_WALK = '''
import adsk.core, adsk.fusion, json, re
app = adsk.core.Application.get()
des = adsk.fusion.Design.cast(app.activeProduct)
root = des.rootComponent
def walk(occs, out, depth=0):
    for i in range(occs.count):
        oc = occs.item(i)
        out.append((oc, depth))
        walk(oc.childOccurrences, out, depth + 1)
    return out
ALL = walk(root.occurrences, [])
'''


def list_occurrences():
    """Names of every occurrence in the active design (STEP translator noise dropped)."""
    code = _WALK + '''
names = [oc.name for oc, d in ALL if "Open CASCADE" not in oc.name]
json.dumps({"doc": app.activeDocument.name, "names": names})
'''
    r = fusion._exec(code, 90.0)
    return json.loads(r) if isinstance(r, str) else r


_COLOURS = {  # name -> RGB 0-255; "dark"/"darker"/"light" adjust brightness
    "black": (18, 18, 20), "white": (240, 240, 240), "silver": (192, 196, 200), "grey": (110, 112, 116),
    "gray": (110, 112, 116), "red": (200, 30, 30), "orange": (232, 112, 38), "yellow": (240, 200, 40),
    "green": (40, 160, 80), "blue": (40, 90, 200), "gold": (200, 160, 60), "bronze": (150, 100, 50),
    "titanium": (135, 135, 140), "carbon": (30, 30, 32), "copper": (184, 115, 51),
}


def _rgb_finish(words):
    """'darker orange' -> ((r,g,b), finish). finish picks the library base like stage8_integrate."""
    w = words.lower()
    rgb = next((v for k, v in _COLOURS.items() if k in w), (128, 128, 128))
    f = 1.0
    if "darker" in w or "dark" in w:
        f = 0.62 if "darker" in w else 0.75
    elif "lighter" in w or "light" in w:
        f = 1.25
    rgb = tuple(max(0, min(255, int(c * f))) for c in rgb)
    if any(k in w for k in ("anodi", "metal", "alumin", "satin", "brushed", "titanium", "chrome")):
        finish = "metal"
    elif "matte" in w or "carbon" in w:
        finish = "matte"
    else:
        finish = "glossy"
    return rgb, finish


def set_appearance(target_regex, words):
    """Recolour every occurrence matching target_regex (and its subtree bodies).

    Same method the MJ-1 build used (mj1/cad/fusion_mj1_kc/stage8_integrate.py): copy a base
    appearance from the Fusion Appearance Library ('Paint - Enamel Glossy', 'Aluminum - Satin',
    'Paint - Enamel Matte'), then set its first ColorProperty to the requested RGB.
    Returns {appearance, count, targets, rgb}."""
    rgb, finish = _rgb_finish(words)
    code = _WALK + f'''
pat = re.compile({target_regex!r}, re.I)
rgb = {list(rgb)!r}
finish = {finish!r}
lib = app.materialLibraries.itemByName("Fusion Appearance Library")
def base_ap(kw):
    for i in range(lib.appearances.count):
        a = lib.appearances.item(i)
        if kw.lower() in a.name.lower():
            return a
    return None
name = "FORGE_%s_%d_%d_%d" % (finish, rgb[0], rgb[1], rgb[2])
appe = des.appearances.itemByName(name)
if appe is None:
    kw = {{"glossy": "Paint - Enamel Glossy", "metal": "Aluminum - Satin", "matte": "Paint - Enamel Matte"}}[finish]
    b = base_ap(kw) or base_ap("Paint - Enamel Glossy")
    appe = des.appearances.addByCopy(b, name)
    for k in range(appe.appearanceProperties.count):
        pr = appe.appearanceProperties.item(k)
        if isinstance(pr, adsk.core.ColorProperty):
            pr.value = adsk.core.Color.create(rgb[0], rgb[1], rgb[2], 255)
            break
targets, n, seen = [], 0, set()
# remember each body's ORIGINAL appearance once (first edit wins), so "revert" can restore it
attr_grp = "forge"
for oc, d in ALL:
    if not pat.search(oc.name) or oc.fullPathName in seen:
        continue
    subtree = [oc] + [c for c, dd in walk(oc.childOccurrences, [])]
    for o in subtree:
        seen.add(o.fullPathName)
        for bi in range(o.bRepBodies.count):
            b = o.bRepBodies.item(bi)
            try:
                if b.attributes.itemByName(attr_grp, "orig_appearance") is None:
                    cur = b.appearance.name if b.appearance else ""
                    b.attributes.add(attr_grp, "orig_appearance", cur)
                b.appearance = appe; n += 1
            except Exception:
                pass
    targets.append(oc.name)
json.dumps({{"appearance": appe.name, "count": n, "targets": targets, "rgb": rgb}})
'''
    r = fusion._exec(code, 120.0)
    out = json.loads(r) if isinstance(r, str) else (r or {})
    if isinstance(out, dict) and "appearance" not in out and isinstance(out.get("result"), str):
        out = json.loads(out["result"])
    return out


def revert_appearance(target_regex=".*"):
    """Restore every body's original appearance (saved on first edit) and delete the FORGE_*
    appearances that are no longer used. Returns {count, removed}."""
    code = _WALK + f'''
pat = re.compile({target_regex!r}, re.I)
n = 0
for oc, d in ALL:
    if not pat.search(oc.name):
        continue
    for bi in range(oc.bRepBodies.count):
        b = oc.bRepBodies.item(bi)
        a = b.attributes.itemByName("forge", "orig_appearance")
        if a is None:
            continue
        try:
            orig = des.appearances.itemByName(a.value) if a.value else None
            b.appearance = orig
            a.deleteMe(); n += 1
        except Exception:
            pass
removed = []
for i in range(des.appearances.count - 1, -1, -1):
    ap = des.appearances.item(i)
    if ap.name.startswith("FORGE_"):
        try:
            if ap.isUsed:
                continue
            nm = ap.name
            if ap.deleteMe():
                removed.append(nm)
        except Exception:
            pass
json.dumps({{"count": n, "removed": removed}})
'''
    r = fusion._exec(code, 120.0)
    out = json.loads(r) if isinstance(r, str) else (r or {})
    if isinstance(out, dict) and "count" not in out and isinstance(out.get("result"), str):
        out = json.loads(out["result"])
    return out


def set_visibility(target_regex, show):
    code = _WALK + f'''
pat = re.compile({target_regex!r}, re.I)
targets = []
for oc, d in ALL:
    if pat.search(oc.name):
        try: oc.isLightBulbOn = {bool(show)!r}; targets.append(oc.name)
        except Exception: pass
try: app.activeViewport.fit()
except Exception: pass
json.dumps({{"count": len(targets), "targets": targets, "visible": {bool(show)!r}}})
'''
    r = fusion._exec(code, 90.0)
    return json.loads(r) if isinstance(r, str) else r


def capture(view="iso"):
    return fusion.render_png(view=view, width=2400, height=1500)


if __name__ == "__main__":
    import sys
    print(json.dumps(list_occurrences(), indent=1))
    if "--black" in sys.argv:
        print(set_appearance(r"JetCat P550|^ENGINE", "black anodized"))
