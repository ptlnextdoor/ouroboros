# CLAUDE.md: Ouroboros

Agent team that trains its own successor: sample → verify → LoRA fine-tune → held-out gate → promote.
Read `docs/PLAN.md` for the full design and `docs/WORKFLOW.md` for interfaces.

## Stack
- Python 3.11+, `uv`. No web framework unless node E needs one (a single static page + SSE is fine).
- Student: vLLM multi-LoRA serving `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (fallback `Qwen/Qwen3-8B`).
- Training: TRL `SFTTrainer` + PEFT LoRA, `accelerate` across 8 GPUs.
- Jury: Crusoe Managed Inference, OpenAI-compatible, `https://api.inference.crusoecloud.com/v1`, key in `CRUSOE_API_KEY`.

## Hard rules
- **Never** train on, prompt-search on, or show the jury `split == "heldout"` items.
- The student model never writes the tests it is graded on.
- Generated code runs only in the sandbox (subprocess, timeout, no network, temp dir).
- Write only to your node's files. Shared formats are frozen in `docs/WORKFLOW.md`.
- Every module has a `--selftest` that runs in under 30 s without GPUs.
- Append progress to `runs/events.jsonl`. The UI reads only that file plus `gens/*/gate.json`.
- No secrets in git. `.env` is ignored.

## Gate definition
Per held-out item i: pass rate p_i over 4 samples, for parent and child.
Δ = mean(child_i − parent_i). 95% CI from 10,000 paired bootstrap resamples over items.
Promote if `ci_low > 0`. Otherwise reject and record the reason.

## Current sprint focus
_(update at each checkpoint)_
- [ ] A serve · [ ] B exec+gate · [ ] C jury · [ ] D evolve · [ ] E UI · [ ] F fast loop
