"""Tier-3 (weights) distiller: harvest referee-verified designs -> LoRA fine-tune.

Walks runs/**/trace.json, keeps every history attempt whose SAFETY checks all
passed (forge.loop.physics_ok) on a TRAIN-split task, and turns each into one
chat example whose turns match the serving path EXACTLY:

  system    = forge.agents._prefix(playbook_text)["content"]   (playbook PINNED to v2)
  user      = the string forge.agents.designer() builds for that attempt
  assistant = json.dumps({"params": <clamped>, "claim": <claim>, "rationale": ...})

Data discipline (docs/BACKEND.md §2 tier-3): train split ONLY (refuse dev/heldout,
asserted), dedupe by clamped-params hash, cap 4 examples per task, prefer the
lightest passes. The adapter and the playbook version travel together, so the
pinned playbook path is recorded in gens/gen1/manifest.json.

CLI:
  python -m forge.distill --selftest      build 1 synthetic example, validate schema, no network
  python -m forge.distill --dry-run       harvest + write jsonl + print stats, no upload
  python -m forge.distill --launch        upload + create the fine-tuning job
  python -m forge.distill --status <id>   poll the job once
"""
import argparse
import glob
import hashlib
import json
import os

os.environ.setdefault("FREECAD_BIN", "/Applications/FreeCAD.app/Contents/Resources/bin")

from forge import agents, blocks, loop

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAYBOOK_REL = "playbook/v2.md"            # PINNED: this adapter is trained against v2
GEN_DIR = os.path.join(ROOT, "gens", "gen1")
TRAIN_PATH = os.path.join(GEN_DIR, "train.jsonl")
VAL_PATH = os.path.join(GEN_DIR, "val.jsonl")
MANIFEST_PATH = os.path.join(GEN_DIR, "manifest.json")

BASE_MODEL = "ftmodel-6c22bf52-fb65-4bd5-94c4-736f0a7d33f0"  # crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16
CRUSOE_FT_BASE_URL = "https://api.intelligence.crusoecloud.com/v1"
CONSOLE_URL = "https://console.crusoecloud.com/foundry/fine-tuning/jobs"
CAP_PER_TASK = 4


# ---------------------------------------------------------------------------
# env (tiny copy of forge.llm._load_env, scoped to the key we need)
# ---------------------------------------------------------------------------
def _load_env():
    key = os.environ.get("CRUSOE_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")          # .env value is quote-wrapped
            os.environ.setdefault(k.strip(), v)
        key = os.environ.get("CRUSOE_API_KEY")
    return (key or "").strip().strip('"').strip("'") or None


# ---------------------------------------------------------------------------
# prompt reconstruction (same code path as the serving agents)
# ---------------------------------------------------------------------------
def _designer_user(task, spec, history_before):
    """Replicate the user string forge.agents.designer() builds for an attempt.

    Literal copy of agents.designer's f-string; history is rendered by the same
    agents._history_text helper the agent uses, so the turn is byte-identical to
    what the model saw at serving time for this attempt.
    """
    return (
        f"GOAL: {task['prompt']}\n"
        f"Required reach {task['reach_mm']} mm  ->  arm_len must be {task['arm_len']} mm.\n"
        f"Material {task['material']}, safety factor {task['fos']}, "
        f"mass limit {task['mass_limit_g']} g, deflection limit {task['defl_limit_mm']} mm.\n"
        f"Definition of done: {json.dumps(spec.get('done_means', []))}\n\n"
        + agents._history_text(history_before) +
        "\nChoose parameters that pass ALL checks and are as light as possible. "
        "Reply with STRICT JSON:\n"
        '{"params":{"t_plate":..,"t_arm":..,"plate_h":..,"width":..,"arm_len":'
        f'{task["arm_len"]}'
        ',"gusset":..,"gusset_len":..,"gusset_h":..,"lighten_n":..,"lighten_d":..},'
        '"claim":{"sigma_MPa":..,"mass_g":..},"rationale":"one sentence"}'
    )


def _assistant_text(rec):
    """The designer's output format: clamped params + claim + rationale."""
    clamped = rec.get("clamped") or blocks.clamp(rec.get("params") or {})
    return json.dumps({
        "params": clamped,
        "claim": rec.get("claim") or {},
        "rationale": rec.get("rationale") or "",
    })


def _example(system, user, rec):
    return {"messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
        {"role": "assistant", "content": _assistant_text(rec)},
    ]}


# ---------------------------------------------------------------------------
# harvest
# ---------------------------------------------------------------------------
def harvest(playbook_text):
    system = agents._prefix(playbook_text)["content"]
    # cache task + spec loads
    task_cache, spec_cache = {}, {}

    def load_task(tid):
        if tid not in task_cache:
            task_cache[tid] = json.load(open(os.path.join(ROOT, "tasks", f"{tid}.json")))
        return task_cache[tid]

    def load_spec(trace_path):
        # checks.json sits next to trace.json; it is the spec's done_means
        p = os.path.join(os.path.dirname(trace_path), "checks.json")
        if p not in spec_cache:
            spec_cache[p] = json.load(open(p)) if os.path.exists(p) else {}
        return spec_cache[p]

    # per task: hash -> best (lowest-mass) candidate example dict
    by_task = {}  # tid -> {hash: (mass, example)}

    for tp in sorted(glob.glob(os.path.join(ROOT, "runs", "**", "trace.json"), recursive=True)):
        trace = json.load(open(tp))
        tid = trace.get("task")
        if not tid:
            continue
        task = load_task(tid)
        # Tier-3 data discipline: train split ONLY. dev/heldout traces live in
        # runs/ too (gate A/B + heldout eval) -> skip them, never train on them.
        if task.get("split") != "train":
            continue
        history = trace.get("history", [])
        if not history:
            continue
        spec = load_spec(tp)
        for i, rec in enumerate(history):
            if not loop.physics_ok(rec.get("verdict")):
                continue
            # REFUSE anything that is not a train-split task (hard guard on the
            # emit path; always holds because we skipped non-train above).
            assert task.get("split") == "train", (
                f"distill refuses non-train trace: {tid} split={task.get('split')!r} ({tp})"
            )
            mass = rec.get("verdict", {}).get("mass_g")
            mass = float(mass) if mass is not None else float("inf")
            h = loop.params_hash(rec.get("params") or {})
            user = _designer_user(task, spec, history[:i])
            ex = _example(system, user, rec)
            slot = by_task.setdefault(tid, {})
            if h not in slot or mass < slot[h][0]:
                slot[h] = (mass, ex)

    # dedupe already done per hash; now prefer lightest, cap per task
    examples = []
    per_task_counts = {}
    for tid in sorted(by_task):
        cands = sorted(by_task[tid].values(), key=lambda t: t[0])[:CAP_PER_TASK]
        per_task_counts[tid] = len(cands)
        examples.extend(ex for _, ex in cands)
    return examples, per_task_counts


def token_estimate(examples):
    chars = sum(len(m["content"]) for ex in examples for m in ex["messages"])
    return chars // 4


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------
def _write_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def write_dataset(examples, playbook_text):
    os.makedirs(GEN_DIR, exist_ok=True)
    n = len(examples)
    val = []
    train = examples
    if n >= 20:
        n_val = max(1, n // 10)           # 10% val split
        val = examples[:n_val]
        train = examples[n_val:]
    _write_jsonl(TRAIN_PATH, train)
    if val:
        _write_jsonl(VAL_PATH, val)
    elif os.path.exists(VAL_PATH):
        os.remove(VAL_PATH)
    manifest = {
        "playbook_path": PLAYBOOK_REL,
        "playbook_sha1": hashlib.sha1(playbook_text.encode()).hexdigest(),
        "base_model": BASE_MODEL,
        "n_examples": n,
        "n_train": len(train),
        "n_val": len(val),
        "token_estimate": token_estimate(examples),
    }
    json.dump(manifest, open(MANIFEST_PATH, "w"), indent=2)
    return len(train), len(val)


# ---------------------------------------------------------------------------
# schema validation (used by --selftest and before upload)
# ---------------------------------------------------------------------------
def validate_jsonl(path):
    n = 0
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)                       # must be valid JSON
        msgs = row["messages"]
        roles = [m["role"] for m in msgs]
        assert roles == ["system", "user", "assistant"], f"bad roles {roles} in {path}"
        for m in msgs:
            assert isinstance(m["content"], str) and m["content"], "empty content"
        payload = json.loads(msgs[2]["content"])     # assistant must be valid JSON
        assert set(payload) >= {"params", "claim", "rationale"}, f"assistant keys {set(payload)}"
        assert isinstance(payload["params"], dict) and payload["params"], "params not a dict"
        n += 1
    assert n > 0, f"no rows in {path}"
    return n


# ---------------------------------------------------------------------------
# crusoe client + launch / status
# ---------------------------------------------------------------------------
def _client():
    from openai import OpenAI
    key = _load_env()
    if not key:
        raise RuntimeError("CRUSOE_API_KEY missing (checked env and .env)")
    return OpenAI(api_key=key, base_url=CRUSOE_FT_BASE_URL)


def launch():
    validate_jsonl(TRAIN_PATH)
    has_val = os.path.exists(VAL_PATH)
    if has_val:
        validate_jsonl(VAL_PATH)
    client = _client()

    with open(TRAIN_PATH, "rb") as f:
        train_file = client.files.create(file=f, purpose="fine-tune")
    print(f"uploaded train file: {train_file.id}")
    val_file = None
    if has_val:
        with open(VAL_PATH, "rb") as f:
            val_file = client.files.create(file=f, purpose="fine-tune")
        print(f"uploaded val file:   {val_file.id}")

    kwargs = dict(
        model=BASE_MODEL,
        training_file=train_file.id,
        suffix="forge-gen1",
        method={"type": "supervised", "supervised": {"hyperparameters": {
            "n_epochs": 3,
            "batch_size": "auto",
            "learning_rate_multiplier": "auto",
            "lora_rank": 16,
        }}},
    )
    if val_file:
        kwargs["validation_file"] = val_file.id
    job = client.fine_tuning.jobs.create(**kwargs)
    print(f"\njob id:  {job.id}")
    print(f"status:  {job.status}")
    print(f"console: {CONSOLE_URL}")
    return job


def status(job_id):
    client = _client()
    job = client.fine_tuning.jobs.retrieve(job_id)
    print(f"job id:  {job.id}")
    print(f"status:  {job.status}")
    if getattr(job, "fine_tuned_model", None):
        print(f"model:   {job.fine_tuned_model}")
    if getattr(job, "trained_tokens", None):
        print(f"trained_tokens: {job.trained_tokens}")
    if getattr(job, "error", None):
        print(f"error:   {job.error}")
    # checkpoint metrics if any
    try:
        ckpts = client.fine_tuning.jobs.checkpoints.list(job_id)
        for c in ckpts.data:
            metrics = getattr(c, "metrics", None)
            print(f"checkpoint {getattr(c, 'step_number', '?')}: {metrics}")
    except Exception as e:
        print(f"(no checkpoint metrics: {e})")
    return job


# ---------------------------------------------------------------------------
# selftest: one synthetic example, validate schema, no network
# ---------------------------------------------------------------------------
def selftest():
    playbook_text = "SELFTEST PLAYBOOK"
    system = agents._prefix(playbook_text)["content"]
    task = dict(id="selftest", prompt="hold 1 kg at 60 mm, aluminium, 3 g",
                reach_mm=60, arm_len=70.0, material="al6061", fos=1.5,
                mass_limit_g=45.0, defl_limit_mm=1.0, split="train")
    spec = {"done_means": ["holds 1 kg", "under 45 g"]}
    rec = dict(
        params={"t_plate": 3.5, "t_arm": 4.5, "plate_h": 45.0, "width": 28.0,
                "arm_len": 70.0, "gusset": 0.0, "gusset_len": 0.0, "gusset_h": 0.0,
                "lighten_n": 2, "lighten_d": 8.0},
        clamped=blocks.clamp({"t_plate": 3.5, "t_arm": 4.5, "plate_h": 45.0, "width": 28.0,
                              "arm_len": 70.0, "lighten_n": 2, "lighten_d": 8.0}),
        claim={"sigma_MPa": 85.0, "mass_g": 38.8},
        rationale="light arm, no gusset needed at 60 mm",
        verdict={"mass_g": 38.8},
    )
    user = _designer_user(task, spec, [])
    ex = _example(system, user, rec)

    tmp = os.path.join(GEN_DIR, "_selftest.jsonl")
    _write_jsonl(tmp, [ex])
    try:
        n = validate_jsonl(tmp)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    assert n == 1
    assert json.loads(ex["messages"][2]["content"])["params"]["t_arm"] == 4.5
    print(f"selftest ok: 1 synthetic example, schema valid, "
          f"~{token_estimate([ex])} tokens")
    return True


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------
def _harvest_and_write():
    playbook_text = open(os.path.join(ROOT, PLAYBOOK_REL)).read()
    examples, per_task = harvest(playbook_text)
    n = len(examples)
    print(f"harvested {n} examples from {len(per_task)} train task(s) (cap {CAP_PER_TASK}/task)")
    for tid in sorted(per_task):
        print(f"  {tid}: {per_task[tid]}")
    print(f"token estimate (chars/4): ~{token_estimate(examples)}")
    if n == 0:
        print("no examples harvested; nothing written.")
        return n
    n_train, n_val = write_dataset(examples, playbook_text)
    print(f"wrote {TRAIN_PATH} ({n_train} rows)")
    if n_val:
        print(f"wrote {VAL_PATH} ({n_val} rows)")
    print(f"wrote {MANIFEST_PATH}")
    validate_jsonl(TRAIN_PATH)
    if n_val:
        validate_jsonl(VAL_PATH)
    print("schema validation: ok")
    return n


def main():
    ap = argparse.ArgumentParser(description="FORGE tier-3 distiller")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--launch", action="store_true")
    ap.add_argument("--status", metavar="JOB_ID")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return
    if args.status:
        status(args.status)
        return
    if args.dry_run:
        _harvest_and_write()
        return
    if args.launch:
        _harvest_and_write()
        launch()
        return
    ap.print_help()


if __name__ == "__main__":
    main()
