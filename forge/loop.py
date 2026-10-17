"""The solve loop: spec -> N designers in parallel -> referee -> critic -> repeat.

solve(task, playbook, ...) -> (best, trace). Emits one JSON per line to
runs/<run>/events.jsonl for the UI, and writes a part STL per verdict to
runs/<run>/<task>/<iter>_<k>.stl.

The referee's load cases come from the task deterministically (visible_cases)
plus referee.hidden_cases(task_id). Only this file touches the hidden set, and
only inside the referee call path, so the agents never see hidden loads.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import threading
import time

os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")

from forge import agents, blocks
from forge.llm import LLM, BudgetExceeded
from referee import referee
from tasks.build_tasks import visible_cases  # deterministic visible loads

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------
class Events:
    # class-level lock: eval_playbook runs tasks in parallel threads, each with
    # its own Events instance pointing at the same tag/events.jsonl. Serialize
    # all appends globally so concurrent writes don't interleave.
    _lock = threading.Lock()

    def __init__(self, run_dir):
        self.path = os.path.join(run_dir, "events.jsonl")
        os.makedirs(run_dir, exist_ok=True)

    def emit(self, kind, **payload):
        rec = dict(ts=time.time(), kind=kind, payload=payload)
        with Events._lock:
            with open(self.path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        return rec


def params_hash(p):
    pc = blocks.clamp(p)
    key = json.dumps({k: round(float(pc[k]), 3) for k in sorted(pc)}, sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def load_task(task_id):
    return json.load(open(os.path.join(ROOT, "tasks", f"{task_id}.json")))


def referee_cases(task):
    """Visible (deterministic) + hidden (referee-only) cases for this task."""
    vis = visible_cases(task)
    hid = referee.hidden_cases(task["id"])  # [{name,F,hidden:True}]
    return vis, hid


# ---------------------------------------------------------------------------
# one design -> build + referee verdict
# ---------------------------------------------------------------------------
def evaluate_design(task, params, claim, vis, hid, stl_path=None):
    try:
        pc = blocks.clamp(params)
        solid = blocks.build(pc)
    except Exception as e:
        return dict(ok=False, reason=f"FAIL: build error {e}"[:300], checks=[], cases=[],
                    mass_g=None), None
    v = referee.evaluate(
        solid, blocks.motor_xy(pc), arm_top_z=pc["plate_h"], cases=vis + hid,
        material=task["material"], fos=task["fos"], defl_limit=task["defl_limit_mm"],
        mass_limit=task["mass_limit_g"], claim=claim or None,
    )
    if stl_path and v.get("mass_g"):
        try:
            import cadquery as cq
            cq.exporters.export(cq.Workplane().add(solid), stl_path)
        except Exception:
            pass
    return v, pc


def physics_ok(verdict):
    """Design is sound if every SAFETY check passes. Parity (agent claim vs
    referee) is reported as the sim-to-real metric but does not gate solved:
    a design is correct even if the agent mis-estimated its own stress."""
    if not verdict:
        return False
    checks = verdict.get("checks", [])
    if not checks:
        return False
    return all(c["ok"] for c in checks if not c["name"].startswith("parity"))


def score(verdict, iters, mass_limit):
    """Higher is better. Passing dominates; then FEWER iterations (the playbook's
    real value: get it right sooner); then lighter. iters is 0-based here."""
    if not physics_ok(verdict):
        return 0.0
    mass = verdict.get("mass_g") or mass_limit
    mass_frac = max(0.0, min(1.0, mass / mass_limit)) if mass_limit else 1.0
    return 100.0 - 15.0 * iters - 5.0 * mass_frac


# ---------------------------------------------------------------------------
# solve
# ---------------------------------------------------------------------------
def solve(task, playbook, *, llm=None, run_dir=None, max_iters=6, n_designers=4,
          ev=None, save_stl=True):
    tid = task["id"]
    run_dir = run_dir or os.path.join(ROOT, "runs", f"adhoc_{int(time.time())}")
    llm = llm or LLM(run_dir=run_dir)
    ev = ev or Events(run_dir)
    task_dir = os.path.join(run_dir, tid)
    os.makedirs(task_dir, exist_ok=True)
    vis, hid = referee_cases(task)

    ev.emit("spec", task=tid, prompt=task["prompt"], status="start")
    spec, spec_raw = agents.spec_agent(llm, task, playbook)
    json.dump(spec, open(os.path.join(task_dir, "checks.json"), "w"), indent=2)
    ev.emit("spec", task=tid, done_means=spec.get("done_means"),
            mass_limit_g=spec.get("mass_limit_g"))
    ev.emit("cost", spent_usd=round(llm.spent, 5), calls=llm.calls)

    history = []        # [{params, verdict, critic}]
    best = None         # dict(params, verdict, iter, k, score)
    iter_best_hashes = []  # best clamped-hash per iteration (across-iter loop detect)
    no_improve = 0
    stop_reason = "max_iters"

    for it in range(max_iters):
        temps = [0.5, 0.8, 1.0, 1.1][:n_designers] or [0.9]
        seeds = [100 + it * 10 + k for k in range(n_designers)]
        ev.emit("design", task=tid, iter=it, n=n_designers, status="start")

        # N designers in parallel threads, different temperatures/seeds
        designs = [None] * n_designers
        with cf.ThreadPoolExecutor(max_workers=n_designers) as ex:
            futs = {ex.submit(agents.designer, llm, task, spec, playbook, history,
                              k=k, temperature=temps[k % len(temps)], seed=seeds[k]): k
                    for k in range(n_designers)}
            for fut in cf.as_completed(futs):
                k = futs[fut]
                try:
                    designs[k] = fut.result()
                except BudgetExceeded:
                    raise
                except Exception as e:
                    designs[k] = dict(params={}, claim={}, rationale=f"error {e}", raw="")

        # referee each design (sequential: ccx is the bottleneck, ~0.7s each)
        iter_best = None
        for k, d in enumerate(designs):
            if d is None:
                continue
            ev.emit("design", task=tid, iter=it, k=k, params=d["params"],
                    claim=d["claim"], rationale=d["rationale"])
            stl = os.path.join(task_dir, f"{it}_{k}.stl") if save_stl else None
            v, pc = evaluate_design(task, d["params"], d["claim"], vis, hid, stl)
            h = params_hash(d["params"]) if pc else f"bad{it}{k}"
            ev.emit("verdict", task=tid, iter=it, k=k, ok=v["ok"], reason=v.get("reason"),
                    mass_g=v.get("mass_g"), parity_gap=v.get("parity_gap"),
                    checks=v.get("checks"), cases=v.get("cases"), phash=h,
                    stl=os.path.relpath(stl, run_dir) if (stl and os.path.exists(stl)) else None)
            rec = dict(params=d["params"], clamped=pc, claim=d["claim"], verdict=v,
                       iter=it, k=k, phash=h, critic=None)
            history.append(rec)
            sc = score(v, it, task["mass_limit_g"])
            if iter_best is None or sc > iter_best["score"]:
                iter_best = dict(rec, score=sc)
        ev.emit("cost", spent_usd=round(llm.spent, 5), calls=llm.calls)

        # track global best + improvement
        if iter_best and (best is None or iter_best["score"] > best["score"]):
            improved = best is None or iter_best["score"] > best["score"] + 1e-6
            best = iter_best
            no_improve = 0 if improved else no_improve + 1
        else:
            no_improve += 1
        if iter_best:
            iter_best_hashes.append(iter_best["phash"])

        if best and physics_ok(best["verdict"]):
            stop_reason = "solved"
            ev.emit("gate", task=tid, iter=it, status="solved",
                    mass_g=best["verdict"].get("mass_g"), score=round(best["score"], 2))
            break

        # loop detector: iter-best lands on the same clamped params two iters
        # running (agents stuck), or 3 iterations with no score improvement.
        stuck_repeat = (len(iter_best_hashes) >= 2 and
                        iter_best_hashes[-1] == iter_best_hashes[-2])
        if stuck_repeat:
            stop_reason = "loop_repeat_params"
            ev.emit("gate", task=tid, iter=it, status="stuck", reason=stop_reason)
            break
        if no_improve >= 3:
            stop_reason = "no_improvement_3"
            ev.emit("gate", task=tid, iter=it, status="stuck", reason=stop_reason)
            break

        # critic: why did it fail + what to change -> fed into next designers
        if it < max_iters - 1:
            failed = [a for a in history if not physics_ok(a["verdict"])]
            if failed:
                try:
                    hyp = agents.critic(llm, task, spec, playbook, failed)
                except BudgetExceeded:
                    raise
                except Exception as e:
                    hyp = f"(critic error {e})"
                history[-1]["critic"] = hyp
                ev.emit("critic", task=tid, iter=it, hypothesis=hyp)
                ev.emit("cost", spent_usd=round(llm.spent, 5), calls=llm.calls)

    trace = dict(task=tid, playbook_len=len(playbook), iters=(best["iter"] + 1 if best else max_iters),
                 solved=bool(best and physics_ok(best["verdict"])), stop_reason=stop_reason,
                 best=best, history=history, spent_usd=round(llm.spent, 5), calls=llm.calls)
    json.dump(trace, open(os.path.join(task_dir, "trace.json"), "w"), indent=2, default=str)
    ev.emit("gate", task=tid, status="done", solved=trace["solved"],
            iters=trace["iters"], stop_reason=stop_reason,
            mass_g=(best["verdict"].get("mass_g") if best else None),
            score=round(best["score"], 2) if best else 0.0)
    return best, trace


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--playbook", default="playbook/v0.md")
    ap.add_argument("--max-iters", type=int, default=6)
    ap.add_argument("--n-designers", type=int, default=4)
    ap.add_argument("--budget", type=float, default=3.0)
    ap.add_argument("--run-dir", default=None)
    args = ap.parse_args()

    task = load_task(args.task)
    playbook = open(os.path.join(ROOT, args.playbook)).read()
    run_dir = args.run_dir or os.path.join(ROOT, "runs", f"{args.task}_{int(time.time())}")
    llm = LLM(run_dir=run_dir, budget_usd=args.budget)
    print(f"solving {args.task} with {args.playbook} (budget ${args.budget})")
    try:
        best, trace = solve(task, playbook, llm=llm, run_dir=run_dir,
                            max_iters=args.max_iters, n_designers=args.n_designers)
    except BudgetExceeded as e:
        print(f"BUDGET STOP: {e}")
        return
    print(f"solved={trace['solved']} iters={trace['iters']} stop={trace['stop_reason']} "
          f"spent=${trace['spent_usd']:.4f}")
    if best:
        print(f"best mass {best['verdict'].get('mass_g')} g, reason {best['verdict'].get('reason')}")
    print(f"run dir: {run_dir}")


if __name__ == "__main__":
    main()
