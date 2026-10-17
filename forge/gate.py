"""Version N+1: the playbook that trains its successor.

Round:
  1. Run TRAIN tasks with the current playbook. Collect failures + critic notes.
  2. playbook-editor (DeepSeek-V4-Pro) proposes ONE rule edit -> candidate v(N+1).
  3. Evaluate candidate vs current on DEV tasks (same iters/designers budget).
  4. Keep the candidate ONLY if dev score strictly improves. Log kept AND
     rejected edits with their dev scores to playbook/history.jsonl.
Final: score v0 vs the best kept playbook on HELDOUT tasks (never used to edit).

HELDOUT is never read during editing (only in `heldout` eval), mirroring the
hard rule in CLAUDE.md.

Run:  uv run python -m forge.gate --rounds 3
      uv run python -m forge.gate --heldout --playbook-a playbook/v0.md --playbook-b playbook/v2.md
"""
import argparse
import json
import os
import time

os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")

from forge import loop
from forge.llm import LLM, BudgetExceeded
from forge import agents

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYBOOK_DIR = os.path.join(ROOT, "playbook")
HISTORY = os.path.join(PLAYBOOK_DIR, "history.jsonl")


def tasks_in(split):
    out = []
    for fn in sorted(os.listdir(os.path.join(ROOT, "tasks"))):
        if not fn.endswith(".json") or fn.startswith("_"):
            continue
        t = json.load(open(os.path.join(ROOT, "tasks", fn)))
        if t.get("split") == split:
            out.append(t)
    return out


def _log_history(rec):
    with open(HISTORY, "a") as f:
        f.write(json.dumps(rec) + "\n")


def eval_playbook(playbook, tasks, *, llm, run_dir, max_iters=4, n_designers=4, tag=""):
    """Run every task; return aggregate dict. Score = sum of per-task best score."""
    total, solved, masses, iters_used = 0.0, 0, [], []
    per = {}
    for t in tasks:
        sub = os.path.join(run_dir, tag or "eval")
        best, trace = loop.solve(t, playbook, llm=llm, run_dir=sub,
                                 max_iters=max_iters, n_designers=n_designers)
        sc = best["score"] if best else 0.0
        total += sc
        if trace["solved"]:
            solved += 1
            iters_used.append(trace["iters"])
            if best["verdict"].get("mass_g"):
                masses.append(best["verdict"]["mass_g"])
        per[t["id"]] = dict(solved=trace["solved"], score=round(sc, 2),
                            iters=trace["iters"], stop=trace["stop_reason"],
                            mass_g=(best["verdict"].get("mass_g") if best else None))
    return dict(score=round(total, 2), solved=solved, n=len(tasks),
                mean_iters=round(sum(iters_used) / len(iters_used), 2) if iters_used else None,
                mean_mass=round(sum(masses) / len(masses), 1) if masses else None, per=per)


def build_failure_digest(playbook, tasks, *, llm, run_dir, max_iters=4, n_designers=4):
    """Run train tasks, collect failing attempts + critic hypotheses for the editor."""
    digest, agg = [], eval_playbook(playbook, tasks, llm=llm, run_dir=run_dir,
                                     max_iters=max_iters, n_designers=n_designers, tag="train")
    # re-read traces for failure detail
    sub = os.path.join(run_dir, "train")
    for t in tasks:
        tp = os.path.join(sub, t["id"], "trace.json")
        if not os.path.exists(tp):
            continue
        tr = json.load(open(tp))
        fails = [h for h in tr.get("history", [])
                 if isinstance(h, dict) and not loop.physics_ok(h.get("verdict"))]
        if not fails:
            continue
        f = fails[-1]
        v = f["verdict"]
        failing = "; ".join(c["name"] for c in v.get("checks", []) if not c["ok"])
        crit = next((h.get("critic") for h in reversed(tr["history"]) if h.get("critic")), None)
        digest.append(
            f"TASK {t['id']} ({t['prompt']}): solved={tr['solved']} after {tr['iters']} iters. "
            f"A failing attempt: {v.get('reason')} | failing checks: {failing} | "
            f"critic: {crit or 'n/a'}"
        )
    return ("\n".join(digest) or "No failures this round."), agg


def round_once(n, current_path, train, dev, *, llm, run_dir, max_iters, n_designers):
    """One N+1 round. Returns (kept, new_path, info)."""
    current = open(current_path).read()
    print(f"[round {n}] current={os.path.relpath(current_path, ROOT)}")

    digest, train_agg = build_failure_digest(current, train, llm=llm,
                                             run_dir=os.path.join(run_dir, f"r{n}_cur"),
                                             max_iters=max_iters, n_designers=n_designers)
    print(f"[round {n}] train score {train_agg['score']} ({train_agg['solved']}/{train_agg['n']} solved)")

    summary, new_pb, raw = agents.playbook_editor(llm, current, digest)
    if not new_pb or len(new_pb) < 50:
        print(f"[round {n}] editor produced no usable playbook, skipping")
        _log_history(dict(ts=time.time(), round=n, action="skip", reason="empty_edit",
                          summary=summary))
        return False, current_path, dict(summary=summary, kept=False)

    cand_path = os.path.join(PLAYBOOK_DIR, f"v{n}_candidate.md")
    open(cand_path, "w").write(new_pb)
    print(f"[round {n}] candidate edit: {summary}")

    # DEV gate: current vs candidate on dev tasks, same budget
    dev_cur = eval_playbook(current, dev, llm=llm, run_dir=os.path.join(run_dir, f"r{n}_devcur"),
                            max_iters=max_iters, n_designers=n_designers, tag="dev")
    dev_new = eval_playbook(new_pb, dev, llm=llm, run_dir=os.path.join(run_dir, f"r{n}_devnew"),
                            max_iters=max_iters, n_designers=n_designers, tag="dev")
    improved = dev_new["score"] > dev_cur["score"]
    print(f"[round {n}] DEV current={dev_cur['score']} ({dev_cur['solved']}/{dev_cur['n']})  "
          f"candidate={dev_new['score']} ({dev_new['solved']}/{dev_new['n']})  -> "
          f"{'KEEP' if improved else 'REJECT'}")

    rec = dict(ts=time.time(), round=n, summary=summary, kept=bool(improved),
               dev_current=dev_cur, dev_candidate=dev_new, train_score=train_agg["score"],
               base=os.path.relpath(current_path, ROOT))
    if improved:
        kept_path = os.path.join(PLAYBOOK_DIR, f"v{n}.md")
        open(kept_path, "w").write(new_pb)
        rec["kept_path"] = os.path.relpath(kept_path, ROOT)
        os.remove(cand_path)
        _log_history(rec)
        return True, kept_path, rec
    os.rename(cand_path, os.path.join(PLAYBOOK_DIR, f"v{n}_rejected.md"))
    rec["rejected_path"] = f"playbook/v{n}_rejected.md"
    _log_history(rec)
    return False, current_path, rec


def run_rounds(rounds, *, start="playbook/v0.md", budget=3.0, max_iters=4, n_designers=4):
    run_dir = os.path.join(ROOT, "runs", f"gate_{int(time.time())}")
    llm = LLM(run_dir=run_dir, budget_usd=budget)
    train, dev = tasks_in("train"), tasks_in("dev")
    current_path = os.path.join(ROOT, start)
    best_path = current_path
    try:
        for n in range(1, rounds + 1):
            kept, new_path, info = round_once(n, current_path, train, dev, llm=llm,
                                              run_dir=run_dir, max_iters=max_iters,
                                              n_designers=n_designers)
            if kept:
                current_path = best_path = new_path
    except BudgetExceeded as e:
        print(f"BUDGET STOP: {e}")
    print(f"\nbest playbook: {os.path.relpath(best_path, ROOT)}  spent ${llm.spent:.4f}")
    print(f"history: {os.path.relpath(HISTORY, ROOT)}  run: {os.path.relpath(run_dir, ROOT)}")
    return best_path, llm.spent


def heldout_eval(path_a, path_b, *, budget=3.0, max_iters=4, n_designers=4):
    """Final: score two playbooks on HELDOUT (never used for editing)."""
    run_dir = os.path.join(ROOT, "runs", f"heldout_{int(time.time())}")
    llm = LLM(run_dir=run_dir, budget_usd=budget)
    heldout = tasks_in("heldout")
    pa, pb = open(os.path.join(ROOT, path_a)).read(), open(os.path.join(ROOT, path_b)).read()
    a = eval_playbook(pa, heldout, llm=llm, run_dir=os.path.join(run_dir, "a"),
                      max_iters=max_iters, n_designers=n_designers, tag="a")
    b = eval_playbook(pb, heldout, llm=llm, run_dir=os.path.join(run_dir, "b"),
                      max_iters=max_iters, n_designers=n_designers, tag="b")
    print(f"\nHELDOUT ({a['n']} tasks, never used for editing):")
    print(f"  {path_a}: score {a['score']}  solved {a['solved']}/{a['n']}  "
          f"mean_iters {a['mean_iters']}  mean_mass {a['mean_mass']} g")
    print(f"  {path_b}: score {b['score']}  solved {b['solved']}/{b['n']}  "
          f"mean_iters {b['mean_iters']}  mean_mass {b['mean_mass']} g")
    out = dict(ts=time.time(), kind="heldout", a=dict(path=path_a, **a),
               b=dict(path=path_b, **b), spent=round(llm.spent, 4))
    json.dump(out, open(os.path.join(run_dir, "heldout.json"), "w"), indent=2)
    _log_history(out)
    print(f"  spent ${llm.spent:.4f}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--start", default="playbook/v0.md")
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--max-iters", type=int, default=4)
    ap.add_argument("--n-designers", type=int, default=4)
    ap.add_argument("--heldout", action="store_true", help="run final heldout A/B instead of rounds")
    ap.add_argument("--playbook-a", default="playbook/v0.md")
    ap.add_argument("--playbook-b", default=None)
    args = ap.parse_args()
    os.makedirs(PLAYBOOK_DIR, exist_ok=True)
    if args.heldout:
        assert args.playbook_b, "--heldout needs --playbook-b"
        heldout_eval(args.playbook_a, args.playbook_b, budget=args.budget,
                     max_iters=args.max_iters, n_designers=args.n_designers)
    else:
        run_rounds(args.rounds, start=args.start, budget=args.budget,
                   max_iters=args.max_iters, n_designers=args.n_designers)


if __name__ == "__main__":
    main()
