"""Intent router for FORGE Studio: one Crusoe call (Nemotron-Super, role "spec") that
turns the typed goal into {intent, edit, reply}. Keyword fallback if the JSON fails.
"""
import json
import re

from forge.llm import LLM, MODELS, parse_json

JET_WORDS = ("supersonic", "mach", "jet", "drone", "aircraft", "plane", "boom",
             "delivery", "flight", "fly", "turbine", "wing")
EDIT_WORDS = ("make", "change", "set", "paint", "color", "colour", "anodized", "hide",
              "show", "instead", "turn")
VIS_WORDS = ("hide", "show", "visible", "invisible", "unhide")

SYSTEM = (
    "You are the intent router for a CAD studio. The open Fusion 360 design is MJ-1, a "
    "supersonic RC jet. Classify the user's one-line message. Reply with STRICT JSON only:\n"
    '{"intent": "new_jet"|"new_bracket"|"edit"|"question", '
    '"edit": {"action": "appearance"|"visibility", "target": "<regex over the part names '
    'below>", "value": "<appearance words like black anodized, or show/hide>"}, '
    '"reply": "<one sentence, only for question>"}\n'
    "new_jet = design a new aircraft/jet/drone from scratch. new_bracket = design a new "
    "mounting bracket/part with loads. edit = change the existing design's look or "
    "visibility. question = anything else. For edit, target MUST be a case-insensitive "
    "regex matching the real part names, e.g. the engine is 'ENGINE_|JetCat P550'; the skin "
    "is '^Skin'. Omit edit for non-edit intents."
)


def _fallback(goal):
    g = goal.lower()
    if any(w in g for w in VIS_WORDS):
        show = ("show" in g or "unhide" in g) and "hide " not in g
        tgt = re.sub(r"\b(hide|show|the|unhide|please)\b", "", g).strip() or "skin"
        return {"intent": "edit", "edit": {"action": "visibility", "target": tgt.split()[0], "value": "show" if show else "hide"}, "reply": ""}
    if any(w in g for w in EDIT_WORDS) and ("engine" in g or "skin" in g or "wing" in g or "fin" in g or "pod" in g):
        tgt = "ENGINE_|JetCat P550" if "engine" in g else next(w for w in ("skin", "wing", "fin", "pod") if w in g)
        val = re.sub(r".*\b(make|paint|color|colour|set|turn)\b", "", g)
        val = re.sub(r"\binstead of\b.*", "", val).replace("the engine", "").strip()
        return {"intent": "edit", "edit": {"action": "appearance", "target": tgt, "value": val or "black"}, "reply": ""}
    if any(w in g for w in JET_WORDS):
        return {"intent": "new_jet", "edit": None, "reply": ""}
    if "bracket" in g or "mount" in g or " n " in g or "load" in g:
        return {"intent": "new_bracket", "edit": None, "reply": ""}
    return {"intent": "question", "edit": None, "reply": "Try: design a jet, design a bracket, or edit the open MJ-1 (e.g. make the engine black)."}


def route(goal, components, llm=None, run_dir="runs/_router"):
    """-> {intent, edit, reply, source: 'llm'|'fallback', model}."""
    names = [n for n in (components or []) if "Open CASCADE" not in n][:60]
    user = f"PART NAMES: {json.dumps(names)}\n\nMESSAGE: {goal}"
    out = None
    try:
        llm = llm or LLM(run_dir=run_dir, budget_usd=0.2)
        txt = llm.chat("spec", [{"role": "system", "content": SYSTEM},
                                {"role": "user", "content": user}],
                       temperature=0, max_tokens=300, meta=dict(agent="router"))
        got = parse_json(txt)
        if isinstance(got, dict) and got.get("intent") in ("new_jet", "new_bracket", "edit", "question"):
            out = got
            out["source"] = "llm"
    except Exception:
        out = None
    if out is None:
        out = _fallback(goal)
        out["source"] = "fallback"
    out.setdefault("edit", None)
    out.setdefault("reply", "")
    out["model"] = MODELS["spec"]
    if out["intent"] == "edit":
        e = out.get("edit") or {}
        e.setdefault("action", "appearance")
        e.setdefault("target", "ENGINE_|JetCat P550")
        e.setdefault("value", "black")
        try:
            re.compile(e["target"])
        except re.error:
            e["target"] = re.escape(e["target"])
        out["edit"] = e
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(route(" ".join(sys.argv[1:]) or "make the engine black anodized instead of silver",
                           ["ENGINE_1:1", "ENGINE_2:1", "JetCat P550-PRO-GH turbine:1", "Skin:1", "WING:1"]), indent=1))
