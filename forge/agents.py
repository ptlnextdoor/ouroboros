"""The agents: spec (Nemotron-Super), designer (Lightning xN), critic + playbook
editor (DeepSeek-V4-Pro).

Each agent is a thin wrapper around forge.llm.LLM. The SYSTEM prefix + playbook
are sent as message[0] so the backend can cache them across calls.

Important: the referee's numeric load cases are derived deterministically in
forge.loop (never here). The spec agent's checks.json is for the UI / human
"definition of done", it does not drive the physics. Agents never see hidden
case names (enforced by make verify-isolation).
"""
import json

from forge import blocks
from forge.llm import parse_json

SYSTEM = (
    "You are an engineering agent in FORGE. You design wall-mounted brackets by "
    "choosing numbers for a fixed parametric part family. You never write CAD code. "
    "You reply with STRICT JSON only, no prose, no code fences.\n\n"
    "PART FRAME: wall at x=0, arm extends +x, +z up, y across, units mm. The load "
    "hole sits 10 mm in from the arm tip, so arm_len = reach_mm + 10.\n\n"
    "PARAMETERS (name: min..max):\n" + blocks.describe()
)


def _prefix(playbook):
    return {"role": "system", "content": SYSTEM + "\n\n=== PLAYBOOK ===\n" + playbook}


# ---------------------------------------------------------------------------
# Spec agent: one-line goal -> checks.json (definition of done, human-readable)
# ---------------------------------------------------------------------------
def spec_agent(llm, task, playbook):
    user = (
        "Turn this one-line bracket goal into a definition-of-done spec.\n"
        f"GOAL: {task['prompt']}\n"
        f"Known numbers: load {task['load_kg']} kg, reach {task['reach_mm']} mm, "
        f"material {task['material']}, g-factor {task['g_factor']}, "
        f"safety-factor {task['fos']}, deflection limit {task['defl_limit_mm']} mm, "
        f"mass limit {task['mass_limit_g']} g.\n\n"
        "Reply with JSON:\n"
        '{"visible_loads":[{"name":"weight","F_N":[0,0,-9.8]},...],'
        '"mass_limit_g":<n>,"defl_limit_mm":<n>,"material":"<al6061|petg>",'
        '"fos":<n>,"done_means":["plain English check", ...]}\n'
        "visible_loads are the obvious static + g-rated down loads only. "
        "done_means is a short plain-words checklist a human can read."
    )
    msgs = [_prefix(playbook), {"role": "user", "content": user}]
    txt = llm.chat("spec", msgs, temperature=0.4, max_tokens=1024,
                   meta=dict(agent="spec", task=task["id"]))
    spec = parse_json(txt) or {}
    # fill defaults from the task so downstream never crashes on a bad reply
    spec.setdefault("mass_limit_g", task["mass_limit_g"])
    spec.setdefault("defl_limit_mm", task["defl_limit_mm"])
    spec.setdefault("material", task["material"])
    spec.setdefault("fos", task["fos"])
    spec.setdefault("done_means", [
        f"holds {task['load_kg']} kg at {task['reach_mm']} mm reach",
        f"survives {task['g_factor']}x g down-load",
        f"stays under {task['mass_limit_g']} g",
        f"tip deflection under {task['defl_limit_mm']} mm",
        "survives realistic side and pull-off loads it was not told about",
    ])
    return spec, txt


# ---------------------------------------------------------------------------
# Designer: playbook + spec + history -> {params, claim, rationale}
# ---------------------------------------------------------------------------
def _history_text(history, limit=3):
    if not history:
        return "No previous attempts.\n"
    lines = ["Previous attempts (most recent last):"]
    for h in history[-limit:]:
        v = h["verdict"]
        fails = "; ".join(c["name"] for c in v.get("checks", []) if not c["ok"]) or "passed"
        lines.append(
            f"- params={json.dumps(h['params'])} -> {v.get('reason', '?')} "
            f"(mass {v.get('mass_g', '?')} g; failing: {fails})"
        )
        if h.get("critic"):
            lines.append(f"  critic: {h['critic']}")
    return "\n".join(lines) + "\n"


def designer(llm, task, spec, playbook, history, *, k=0, temperature=0.9, seed=None):
    user = (
        f"GOAL: {task['prompt']}\n"
        f"Required reach {task['reach_mm']} mm  ->  arm_len must be {task['arm_len']} mm.\n"
        f"Material {task['material']}, safety factor {task['fos']}, "
        f"mass limit {task['mass_limit_g']} g, deflection limit {task['defl_limit_mm']} mm.\n"
        f"Definition of done: {json.dumps(spec.get('done_means', []))}\n\n"
        + _history_text(history) +
        "\nChoose parameters that pass ALL checks and are as light as possible. "
        "Reply with STRICT JSON:\n"
        '{"params":{"t_plate":..,"t_arm":..,"plate_h":..,"width":..,"arm_len":'
        f'{task["arm_len"]}'
        ',"gusset":..,"gusset_len":..,"gusset_h":..,"lighten_n":..,"lighten_d":..},'
        '"claim":{"sigma_MPa":..,"mass_g":..},"rationale":"one sentence"}'
    )
    msgs = [_prefix(playbook), {"role": "user", "content": user}]
    txt = llm.chat("designer", msgs, temperature=temperature, top_p=0.95, seed=seed,
                   max_tokens=1024, meta=dict(agent="designer", task=task["id"], k=k))
    out = parse_json(txt) or {}
    params = out.get("params") or {}
    params.setdefault("arm_len", task["arm_len"])  # enforce reach
    claim = out.get("claim") or {}
    return dict(params=params, claim=claim, rationale=out.get("rationale", ""), raw=txt)


# ---------------------------------------------------------------------------
# Critic: failed verdicts -> hypothesis of WHY + what to change next
# ---------------------------------------------------------------------------
def critic(llm, task, spec, playbook, attempts):
    """attempts: list of {params, verdict}. Returns a short string hypothesis."""
    blocks_txt = []
    for a in attempts[-3:]:
        v = a["verdict"]
        cases = "; ".join(
            f"{c['name']}{'(hidden)' if c.get('hidden') else ''}: "
            f"sigma {c.get('sigma_MPa', '?')}/{c.get('allow_MPa', '?')} MPa, "
            f"defl {c.get('defl_mm', '?')} mm, ok={c['ok']}"
            for c in v.get("cases", [])
        )
        blocks_txt.append(
            f"params={json.dumps(a['params'])}\n  verdict: {v.get('reason')}  "
            f"mass {v.get('mass_g')} g\n  cases: {cases}"
        )
    user = (
        f"GOAL: {task['prompt']}  (arm_len {task['arm_len']} mm, {task['material']}, "
        f"mass limit {task['mass_limit_g']} g)\n\n"
        "A designer agent keeps failing the physics referee. Here are the attempts:\n\n"
        + "\n\n".join(blocks_txt) +
        "\n\nYou are the engineering critic. In 2-3 sentences: WHY is it failing "
        "(which load direction / which check), and the SPECIFIC parameter changes "
        "to try next (name params and rough magnitudes). Be concrete. Plain text, "
        "no JSON."
    )
    msgs = [_prefix(playbook), {"role": "user", "content": user}]
    txt = llm.chat("critic", msgs, temperature=0.5, max_tokens=512,
                   meta=dict(agent="critic", task=task["id"]))
    return txt.strip()


# ---------------------------------------------------------------------------
# Playbook editor: failures + critic notes -> proposed rule diff (new playbook)
# ---------------------------------------------------------------------------
def playbook_editor(llm, current_playbook, failure_digest):
    user = (
        "You maintain the shared design PLAYBOOK below. Designer agents read it "
        "before every design. Here is a digest of recent FAILURES and the critic's "
        "hypotheses across several tasks:\n\n"
        + failure_digest +
        "\n\n=== CURRENT PLAYBOOK ===\n" + current_playbook +
        "\n\nPropose ONE focused improvement: add or sharpen a small number of "
        "GENERAL design rules (not task-specific numbers) that would have prevented "
        "these failures (e.g. about side/off-axis loads, gussets on long arms, "
        "minimum width). Reply with STRICT JSON:\n"
        '{"summary":"one line describing the edit",'
        '"new_playbook":"<the FULL new playbook markdown>"}'
    )
    msgs = [
        {"role": "system", "content": "You are a careful engineering playbook editor. "
                                       "Reply with STRICT JSON only."},
        {"role": "user", "content": user},
    ]
    txt = llm.chat("editor", msgs, temperature=0.6, max_tokens=4096,
                   meta=dict(agent="editor"))
    out = parse_json(txt) or {}
    return out.get("summary", "(no summary)"), out.get("new_playbook", ""), txt
