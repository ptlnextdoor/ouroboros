# Provenance: what existed before the hackathon vs built during it

Rule: *"Your demo must only highlight the specific features, code, and functionality that your team built during the hackathon."*
Hacking started **10:45 AM PT, 2026-10-17**. `git log --since="2026-10-17 10:45"` lists everything built today.

## Before 10:45 (planning only, no project code)
| what | where |
|---|---|
| Ideas, research, plans, winner audit, judge notes | `docs/PLAN.md`, `RESEARCH.md`, `WINNER_AUDIT.md`, `ALTERNATIVES.md`, `WORKFLOW.md`, `SPEC.md`, `JUDGES.md`, `WIN_PLAYBOOK.md`, `SIDE_PRIZES.md`, `HARVESTED_SKILLS.md`, `brief/` |
| Toolchain smoke test (environment check, script not kept) | `docs/evidence/REFEREE_SMOKE_TEST.md` |
| Repo scaffolding | `LICENSE`, `.gitignore`, `.env.example`, `CLAUDE.md` |
| Krish's thermal proposal (alternative idea, not built) | branch `thermal-research-factory` |

## Built during the hackathon
`forge/` (blocks, LLM client, agents, loop, gate), `referee/` (FEA referee, hidden cases), `tasks/`, `playbook/`,
`ui/`, `Makefile`, `assets/banner.svg` (FORGE version), `README.md` (FORGE version), and all `runs/` artifacts.

## Pre-existing third-party tools (not our work)
- CadQuery 2.8 / OpenCascade (geometry), gmsh (meshing), CalculiX `ccx` (FEA solver). gmsh and ccx ship inside FreeCAD.app.
- Models on Crusoe Managed Inference: NVIDIA Nemotron-3-Super, Nemotron-3.5-Lightning, DeepSeek-V4-Pro.
- Python libraries: numpy, openai client.

## Prior personal work used only as *method* (no code copied)
Lessons from the team's earlier drone and jet projects (SQ-2, MJ-1) shaped the referee checks: validate the
solver against beam theory, treat mesh failure as a FAIL, check symmetry, hash the solved geometry. The
negative-drag result quoted in the pitch comes from that earlier project's optimizer log, dated 2026-10-16.
Listed in `docs/HARVESTED_SKILLS.md`. None of that code is in this repo.
