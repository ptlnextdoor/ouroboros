# FORGE backend: harness, memory, compute

Decided 2026-10-17 1:10 PM PT, from measured numbers (every figure below has a run or a curl behind it).
This answers three questions: what harness the agents run in, what memory structure they use, and
where the compute goes (Crusoe $200 credit vs Krish's 8×A100).

---

## 1. The harness

**We built our own. It is `forge/loop.py` and it stays.** No LangChain, no OpenClaw, no framework.
Rationale: the winner audit (WIN_PLAYBOOK §1) shows every repeat winner shipped a thin loop they
fully understood; MongoMation's "harness" was a state machine plus a grader. Ours is:

```
spec agent ──> N designers (parallel threads, temp/seed spread)
                   │ params JSON (never CAD code)
                   v
             blocks.build()  → STEP/STL          [deterministic CAD]
                   v
             referee (gmsh + CalculiX, visible + HIDDEN cases)   [no LLM]
                   v
             verdict ──> critic (different model family) ──> next iteration
                   v
             events.jsonl (append-only) ──> UI / gate / distiller
```

Harness properties that make it defensible in Q&A:
- **Frozen interfaces** (SPEC.md): `task.json → checks.json → params → part.step → verdict.json →
  trace.json → events.jsonl`. Every stage is a file; every file is replayable.
- **Hard budget cap** in `forge/llm.py` (BudgetExceeded at $N per run); every call logged with cost.
- **Loop detector**: repeated clamped-params hash or 3 iters without score improvement → stop, re-plan.
- **Isolation is enforceable, not asserted**: `make verify-isolation`; only `loop.py`'s referee call
  path touches `referee/hidden/`.
- **One concession to OpenShell** (side prize, timeboxed, currently dropped): the harness runs fine
  inside a sandbox whose policy allow-lists `work/` and never mentions `referee/hidden`. If Krish
  gets 30 free minutes, wrap `blocks.build()` exec in it; otherwise the Makefile guard is the proof.

## 2. Memory structure (the actual answer to "what memory would hardware agents use")

Three tiers, mirroring how a real engineering team remembers. **Every tier is gated by the same
physics referee; nothing is "remembered" because it sounds right.**

| tier | lives in | what it stores | write path | gate |
|---|---|---|---|---|
| 1 · notebook (episodic) | `trace.json` history, last 3 fed to designers | attempts: params → verdict → critic hypothesis | automatic, per task | none (raw experience) |
| 2 · playbook (semantic, the Shared Brain) | `playbook/vN.md` + `history.jsonl` | general design rules in English ("gusset any arm > 50 mm") | editor agent proposes ONE edit per round | kept only if dev-split score improves; rejects logged (`v1_rejected.md`, `v3_rejected.md` exist) |
| 3 · weights (procedural intuition) | LoRA adapter on Nemotron via Crusoe Serverless Fine-Tuning | referee-verified (goal → params) pairs distilled into the designer | `forge/distill.py` harvests train-split passes | same held-out A/B as the playbook; promote only if held-out score rises |

Why this structure wins the argument:
- Tier 2 is **legible** memory: judges can read the diff between v0 and v2 and see engineering
  rules an agent wrote from its own failures. Weight updates can never show that.
- Tier 3 is the **recursive** memory: the model that designs tomorrow is trained on what survived
  physics today. "The playbook is the team's notebook; the adapter is its trained hands."
- Both tiers share one promotion rule (score on tasks never used for editing/training), so the
  Version N+1 story is a single sentence: *memory is only memory if it transfers.*

Tier-3 data discipline (from PLAN.md research, still applies):
- train **only** on `split == "train"` traces, never dev/heldout (`distill.py` refuses otherwise);
- dedupe by clamped-params hash, cap 4 examples per task to avoid easy-task overtraining;
- the assistant turn is exactly the designer's output JSON; the system prefix at training time is
  **verbatim** the serving prefix (playbook pinned per adapter: adapter and playbook version together).

## 3. Compute: Crusoe, not the A100s. Numbers:

Measured today:
- A full 3-round playbook-gate run (229 LLM calls: 42 spec / 169 designer / 15 critic / 3 editor)
  cost **$0.108** on Crusoe Managed Inference. Designer p50 latency 1.8 s.
- The bottleneck is the **referee**, not GPUs: ~6 s per verdict (gmsh+ccx) on this Mac,
  sequential. LLM time is already overlapped away by threads.
- Crusoe **Serverless Fine-Tuning** works with our key (`api.intelligence.crusoecloud.com`,
  verified: model list + empty jobs list). Catalog includes
  `crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16` at **$0.40 / 1M training tokens**, OpenAI-
  compatible (`client.fine_tuning.jobs.create`, `lora_rank`, `learning_rate`, `n_epochs`,
  early stopping). LoRA adapter checkpoints are downloadable; deployable via Self-Serve
  Deployments (H100 $6.30/GPU-hr) or hot-loadable on our own vLLM.

Budget plan for the $200:
| item | est |
|---|---|
| all inference for remaining rounds + heldout + demo reruns | < $5 |
| Gen-1 LoRA job (≈100–300 verified trajectories × ~800 tok × 3 epochs ≈ 0.5–1 M tok) | ≈ $0.40–2 |
| Self-Serve Deployment of the adapter for the demo window (Fused LoRA, 4×H100 throughput profile, $22/hr, billed per second; ~1 h) | ≈ $22 |
| headroom | > $170 |

**A100 cluster verdict: keep it parked.** Using it means rebuilding the OUROBOROS stack (vLLM
multi-LoRA + TRL + accelerate) that we explicitly abandoned at kickoff; the risky item on the
tonight-checklist (hybrid Mamba-MoE LoRA in vLLM/PEFT, rated 30% failure) is exactly what Crusoe's
managed recipe does for us for ~$2. The cluster's one legitimate use today: **a parallel referee
farm** (ccx is CPU-bound; 8 nodes × N cores would cut gate rounds from ~8 min to ~1 min), and even
that is a nice-to-have, not a blocker. Q&A line: "we have 8×A100 on standby; we chose the managed
path because our bottleneck is physics, not FLOPs."

## 4. Tonight's-checklist triage (what still continues)

| item | status |
|---|---|
| `vllm serve Nemotron --enable-lora` on cluster | **dropped** — Crusoe Serverless FT replaces it (managed LoRA, same Nemotron family, zero ops) |
| PEFT LoRA 10-step smoke on Nemotron-Nano | **dropped** — same reason; Crusoe's per-model recipe is their problem |
| Download TACO/APPS/LiveCodeBench | **dropped** — tasks are brackets with an FEA referee, not code |
| `curl /v1/models` with key | **done** — both `api.inference` (jury/designers) and `api.intelligence` (fine-tune) verified today |
| Tailscale to cluster from hotspot | **optional** — only matters if we spin up the referee farm |
| Skills /interview, trim MCPs | **done** at kickoff (SPEC.md frozen) |
| Sleep | consumed |

## 5. The demo beats this unlocks (vision cut, per judge feedback)

1. Vision (15 s): "I'm a high-schooler at Boom Supersonic. A $200 AI subscription is what a
   $20M engineering team used to be — for software. FORGE brings that to hardware." Cut to the
   SQ2 supersonic-quad dossier as the lived example.
2. Comparison (30 s): GPT-Astra's drone = a cylinder labeled "drone," no materials, no
   manufacturability. FORGE's part = CNC-millable, material chosen, and **every claim checked by a
   solver it can't see inside, on loads it was never told about** (show a hidden-case FAIL).
3. Memory (30 s): the three tiers on screen: notebook → playbook diff (one kept, one rejected) →
   the LoRA job running live in the Crusoe console ("the team is training its own successor right
   now; it gets promoted only if it wins on parts it has never seen").
4. Receipt: held-out table v0 vs vN + $ column. Honest line: n = 6 held-out parts; the mechanism
   is the result.

Codebase beat (judge asked): 10 s on the data-flow diagram in §1 — every arrow is a file on disk,
`runs/` is replayable. SolidCraft (`/Applications/SolidCraft.app`) can open the STEP live if we
want a "real CAD tool" moment; the three.js viewer in `ui/` is the rehearsed default.

## 6. Open risks

- Fine-tune job wall-clock (~30 min on sample data per Crusoe's guide) may not finish before
  freeze. Mitigation: the *job itself* (real data, real console) is the demo artifact; deploy only
  if it lands by 3:30.
- Adapter inference needs a Self-Serve Deployment (console-verified 13:40: Fused LoRA on Nemotron 3.5
  Lightning, 4×H100 $22/hr or 8×H100 $44/hr). The FT base `crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16`
  is what the console labels "Nemotron 3.5 Lightning 30B A3B", i.e. the same model our designers already
  call, so the adapter is a drop-in designer upgrade. Deploy only after the job succeeds; tear down right
  after the demo. Fallback: show the gate against the base model, labeled "Gen 1 pending."
- Design/visual work (banner, slide card) routes to the Gemini account, not Claude, to save
  Anthropic quota for builders.
