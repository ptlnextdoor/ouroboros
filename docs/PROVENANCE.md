# Provenance: what existed before the hackathon vs built during it

The hackathon rules say: *"Your demo must only highlight the specific features, code, and functionality
that your team built during the hackathon."* This file lists exactly what existed before
**10:45 AM PT, 2026-10-17** and what we built after.

## Before hacking started (planning only, no code)

Created the evening of 2026-10-16:

| File | What it is |
|---|---|
| `README.md` | project description, target interface (no implementation) |
| `assets/banner.svg` | header graphic |
| `docs/PLAN.md` | design, budget, pre-mortem, demo script |
| `docs/RESEARCH.md` | literature review generated with Consensus |
| `docs/SETUP.md` | environment checklist (installing libraries, downloading weights) |
| `docs/WORKFLOW.md` | how the team will work |
| `docs/ALTERNATIVES.md` | rejected ideas |
| `CLAUDE.md`, `.gitignore`, `.env.example`, `LICENSE` | repo scaffolding |

Environment prep (not in the repo): installing vLLM/TRL/PEFT, downloading model weights and
public datasets, checking cluster access. No project source code was written before 10:45.

## Third-party components (not our work)

- Model weights: NVIDIA Nemotron-3-Nano-30B-A3B, Qwen3-8B (fallback)
- Hosted models via Crusoe Managed Inference
- Libraries: vLLM, Hugging Face Transformers / TRL / PEFT, PyTorch
- Datasets: TACO, APPS, LiveCodeBench, HumanEval+/MBPP+

## Built during the hackathon

Everything under `src/` and every commit timestamped after 10:45 AM PT on 2026-10-17.
`git log --since="2026-10-17 10:45" --stat` shows the full list.
