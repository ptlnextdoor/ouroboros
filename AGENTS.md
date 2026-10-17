# AGENTS.md: shared memory for every FORGE worker (read before you write code)

Updated 2026-10-17 14:10 PT. Freeze 4:00 PM. Working demo target 2:30 PM.

## What we are building (one sentence)
FORGE: an AI hardware engineer. One sentence in, a manufacturable part out, every claim checked by physics
it can't see inside, and it only keeps lessons (playbook, then LoRA weights) that win on parts it never saw.

## THE PITCH (founder, 2:38 PM, overrides older notes)
FORGE is the tool. The VISION (from a judge's feedback): hardware abundance, where one person with a $200
subscription can build what used to take a $20M team. A supersonic Zipline (blood and organ delivery to
hospitals) is ONE example of a startup someone could build with FORGE, not the product itself. Lead with the
tool; use the supersonic-delivery idea as the "imagine what you could build" moment. The hero vehicle on
screen is **MJ-1**, our Boom-Prize supersonic RC jet
(/Users/aayu/Workspace/developer/mj1). STOP leading with the bracket: "any Opus or GPT-6 Astra can make a
bracket." The bracket loop is only the proof that the referee + self-improvement works (held-out 5/6 -> 6/6).
What is impressive and must be on screen: SOURCING real parts (JetCat P550-PRO turbine, KST servos, Matek FC,
GNSS, airspeed, fuel system: mj1/cad/kc_vendor.py, 23 parts, each with datasheet source and REAL vs STAND-IN
tag), reading datasheets/drawings, vendor STEP files, and designing the airframe AROUND them (Fusion stage
scripts mj1/cad/fusion_mj1_kc/, MJ1_KC.f3d), then physics: mj1.sizing (8 architectures vs Mach 1.05),
calibrated turbojet deck, area rule from the real STEP (E_WD 7.1 -> 3.06).
MJ-1 honesty: a design, not flown. Best area-ruled layout is ~10 % short of thrust for M1.05 at the nominal
engine model. No 2 kg payload bay exists yet ("payload bay sizing: next"). Twin-P400 closes nominally,
P(M1.05) 0.68 in Monte Carlo, fails the pessimistic band. SQ-2 (590 km/h quad, NOT supersonic) is the
second vehicle, also designed by this agent stack.

## Why this wins (from docs/WIN_PLAYBOOK.md + docs/WINNER_AUDIT.md research, condensed)
- Repeat winners: one-line input typed live, something visual inside 60 s, a referee that says FAIL with a
  number, one before/after table on a hidden set with a $ column, one honest limitation sentence,
  isolation that is demonstrable (`make verify-isolation`).
- Lifts measured on past CV winners: physical artifact 1.59x, simulation 1.56x, 3D 1.44x. Pure evaluator 0.66x,
  so the referee is the villain in the story, never the headline. The PART is the headline.
- Judge feedback today: lead with the VISION (hardware abundance; a high-schooler with a $200 subscription
  doing what took $20M), then the COMPARISON (raw GPT-Astra makes a cylinder labeled "drone"; our stack
  designed SQ-2), then show the codebase / data flow briefly.
- Judges reward honesty. MongoMation won 1st saying their gate kept nothing. Rejected edits stay visible.

## Honesty rules (a judge with the PDF will check; violating these loses)
- SQ-2 is a 590 km/h electric quadcopter (Mach 0.48), aimed at the 657.59 km/h record, 10 % short per its
  own report. NEVER "supersonic", NEVER "Mach 1-2". Tip Mach 0.84.
- SQ-2 CFD: OpenFOAM RANS 3.55 M cells, CdA 32.4 vs 31.9 cm2 design (+1.4 %), method validated -2.8 % on a spheroid.
- SQ-2 CAD: 74 STEP parts from 130 optimizer params, 82 automated checks, min MS +0.48, 2997 g, ~$3,100.
  Independent audit: v3.1 about 15 % buildable as drawn; v3.2 fix pass in progress. Show this, it's a strength.
- SQ-2 was designed by agents (Claude Opus + jcode stack) in 48 h of git history (10-14 20:08 to 10-16 15:49).
- FORGE numbers only from files: playbook/history.jsonl, runs/**/calls.jsonl, heldout.json, docs/evidence/.
  If a number has no file behind it, don't print it.

## Compute and memory decisions (docs/BACKEND.md)
- Crusoe Managed Inference for all agents (Nemotron-Super spec, Nemotron-Lightning designers x4, DeepSeek-V4 critic/editor).
- Crusoe Serverless Fine-Tuning for tier-3 memory: Gen-1 LoRA SUCCEEDED, model ftmodel-503f6289-c017-4e66-8351-ee8919f19c3f,
  val loss 0.262, 24 referee-verified train designs. Deploy = Fused LoRA 4xH100 $22/hr (only if we decide to).
- 8xA100 cluster stays parked: bottleneck is CalculiX (CPU), not GPUs. Crusoe CPU instances ($0.04/vCPU-hr)
  are the right scale-out for a referee farm if we ever need it.
- Memory tiers: notebook (trace.json) -> playbook (gated on dev) -> weights (gated on held-out).

## How you work (mandatory process, every worker)
1. IDEATE like a SpaceX engineer (elon-musk-skill): question the requirement, delete before optimizing,
   simplify, then accelerate. Smallest diff that ships the demo beat. State P(success) for risky choices.
2. PLAN with GSD discipline (gsd skill): write your todo list, atomic commits, verify each step.
3. BUILD with superpowers discipline: verification-before-completion. Run the real thing, look at the
   screenshot, read the output. Never report done on an unrun path.
4. Before EVERY commit, self-review the diff against three skills:
   - thermo-nuclear-review (correctness/security: wrong numbers, broken paths, secrets, crashes),
   - thermo-nuclear-code-quality-review (giant files, spaghetti conditions, dead code),
   - deslop (AI slop in code and copy: filler comments, generic UI text, hype words, emoji, em dashes).
   Fix what they find, then commit. Mention "reviewed: thermo + quality + deslop" in the commit body.
5. Git: work on a branch named `feat/<your-label>`, push it, open a PR to main with `gh pr create`
   (title = what the demo gains, body = what/why/how verified + screenshot paths). Push commits as you go
   so Krish sees it develop. Never force-push main. Never commit runs/ (except small ui/fixture copies) or .env.
6. Own only your files. If you must touch a shared file, say so in the PR body.

## UI taste (the user hated vibe-coded UI)
MANDATORY for any UI work: load and follow these skills (installed in ~/.claude/skills/ from
github.com/42nights/ui-bundle): `impeccable` (product register: reference/product.md), `interface-design`,
`emil-design-eng`, `taste-skill`. Run impeccable's critique on your own screenshot before you report.
Layout must be fluid (1280-2560 wide, no clipping, no dead gaps); test at 1440x900, 1600x1000, 1920x1080.
Dark #06080d, green #2ee6a6 = physics passed, red #ff5f6d = referee said no, blue #4aa8ff accent,
mono labels, real numbers only. No gradients-for-decoration, no emoji, no "AI-powered", no lorem.
Model framed and centered, nothing overlapping, legible at 1920x1080. Reference look: Fusion 360 + Apple keynote.

## Paths
PY=/opt/miniconda3/bin/python3   FREECAD_BIN=/Applications/FreeCAD.app/Contents/Resources/bin
SQ-2 source: /Users/aayu/Workspace/developer/speed-quad (read-only)   SolidCraft CLI: /Applications/SolidCraft.app/Contents/MacOS/solidcraft-cli
