# STATUS: where we actually stand (verified on disk, 2:21 PM PT, 2026-10-17)

Audit method: filesystem + `git log` + `gh pr view 1`, not agent claims. Freeze 4:00, submit 4:45.
Branch audited: `feat/forge-app` @ 22b1de0 (local), PR #1 `dev -> demo-base` OPEN (18 commits, last 14:15).
`origin/main` is 5 commits behind local HEAD, `origin/dev` 2 behind. Working tree: 10 uncommitted paths.

## Headline

The founder's 2:18 PM product ("FORGE Studio": a Cursor-style agent-manager chat docked beside Fusion 360,
parts built live through Fusion360LiveMCP) **does not exist in the repo. Zero files. Zero commits.**
`studio/` is not on disk, `git log --all | grep -i studio` returns nothing. The Fusion add-in IS alive
(TCP 9876 LISTEN by `Autodesk Fusion` pid 10959, add-in dir `~/.../API/AddIns/Fusion360LiveMCP`), but nothing
in this repo talks to it. Everything shipped so far targets **SolidCraft** and the stdlib web UI, not Fusion.

What IS real and demoable right now: the FORGE loop (`make demo`, 7m18s rehearsed), the replay fixture, the
v0-vs-v2 held-out A/B (5/6 -> 6/6, $0.06), the CalculiX review of a real SQ-2 7075 node, the SolidCraft SQ-2
v3 assembly (110 bodies), the three.js SQ-2 page, and FORGE.app.

## 1. Workstreams: claimed vs verified

| workstream | claimed | VERIFIED on disk | demo-critical? | risk |
|---|---|---|---|---|
| **studio/** agent-manager + Fusion bridge | "just started, critical path" | **NOTHING.** No `studio/` dir, no commit, no branch. Fusion 9876 is listening but unaddressed by any file here. Screenshot: n | YES (it is the pitch as of 2:18) | **RED.** 1h39m to freeze, from zero. Chat UI + Fusion MCP calls + wiring to `forge/loop.py` is not a 90-minute job with review gates. |
| solidcraft/ + forge/solidcraft.py | SQ-2 assembly, native bracket, live GUI drive | `solidcraft/designs/sq2_v3.solidcraft` (53 MB), `forge_bracket/bracket.{solidcraft,step,png}`, `forge/solidcraft.py` (13.9 KB). Commit e6afc2c 14:14. Shots: `solidcraft/shots/sq2_v3_{iso,front,side,exploded}.png`, `live_bracket_window.png`. Screenshot: **y** | Medium (CAD-app beat, but it is SolidCraft, not Fusion) | Uncommitted `.bak` files + modified bracket.png in tree. If the pitch is Fusion, this is now a side exhibit. |
| ui/sq2/ three.js showcase | hero screen, 78 STLs | `ui/sq2/index.html` (31 KB), `parts/` 79 entries, `img/cfd_*.png`. Commit 2313c35 14:13. Shots: `ui/shots/sq2_{assembled,exploded,xray}.png`. Screenshot: **y** | Low (founder: choppy render) | Done enough. Stop touching. |
| ui/index.html loop UI redesign | redesign | `ui/index.html` last commit 13:42. Only new artifacts are `ui/shots/baseline_*.png` (14:13, uncommitted). No redesign commit. Screenshot: y (baseline only) | Medium (it is the live loop surface) | Redesign not started in git. Current UI works (port 8008 LIVE now). Cut the redesign. |
| app/ FORGE.app | native shell | `app/Sources/main.swift`, `build.sh`, `FORGE.app/` built (14:18), `app/shots/forge_{live,1440x900}.png`. Commit 22b1de0 14:19 (local only, not pushed). Screenshot: **y** | No (deprioritized) | Done. Push it and stop. |
| forge/adapter.py + README results | held-out v0 vs v2, Gen-1 LoRA | `runs/heldout_1792270684/heldout.json`: v0 5/6 solved, score 330.8, mean iters 3.0; v2 **6/6**, score 582.1, mean iters **1.0**, 17 % lighter. `gens/gen1/{manifest.json,train.jsonl,val.jsonl,adapter/}` n=24 (22/2). `docs/evidence/forge-gen1_job_queued.png`. `forge/adapter.py` is **uncommitted**. README cites the run. | YES (the before/after table) | adapter.py not in git. No file on disk shows "SUCCEEDED val loss 0.262" except AGENTS.md prose; the evidence PNG is "queued". Get a SUCCEEDED screenshot into `docs/evidence/` or say "queued" on stage. |
| forge/sq2_review.py | CalculiX on real SQ-2 pod node | `forge/sq2_review.py`, `docs/evidence/SQ2_REVIEW.md`, `ui/fixture/sq2_review/{verdict.json,pod_node_vm.png,sq2_node.step,.frd.gz}`. Commit ebd3759 14:15. Screenshot: **y** (`pod_node_vm.png`) | YES (referee on a real part = the strongest honesty beat) | Done. Use it. |
| forge/topopt_live.py | topopt growth animation | `forge/topopt_live.py` (uncommitted), `ui/fixture/topopt/{live.json,pod_node_final.stl}`. **0 frames, no growth.mp4/gif, no convergence.png.** Screenshot: n | No | Half-built. Cut unless the mp4 lands by 3:00. |
| forge/cfd_viz.py | CFD clips | `forge/cfd_viz.py` (uncommitted), `ui/fixture/cfd/{sq2_cfd_kenburns.mp4,sq2_cfd_receipt.png,sq2_cfd_convergence.png}`. Screenshot: y | No | Done enough for a 5-second b-roll. Commit it. |
| core loop (`forge/loop.py`, referee, gate) | works | `runs/br02_1792268889` (solved, 1 iter, $0.0012), `ui/fixture/br02` replay, `playbook/history.jsonl` 5 records (v3 rejected). Docs/DEMO.md stage card rehearsed 13:28. | YES | Stable. This is the demo. |

## 2. Cost receipts (from `runs/**/calls.jsonl`, last `spent_usd` per run)

| run | calls | prompt tok | completion tok | spent_usd |
|---|---|---|---|---|
| gate_1792263761 (3 N+1 rounds, 9 solves) | 229 | 266,529 | 45,833 | $0.1081 |
| heldout_1792270684 (v0 vs v2, 12 solves) | 125 | 154,967 | 23,846 | $0.0597 |
| heldout_1792269579 | 94 | 119,650 | 16,958 | $0.0522 |
| heldout_1792268968 | 75 | 91,550 | 13,981 | $0.0381 |
| heldout_1792265873 | 55 | 71,799 | 10,104 | $0.0319 |
| br02_1792268889 (demo run) | 5 | 5,601 | 963 | $0.0012 |
| probes/dryrun | 4 | 132 | 14 | $0.0000 |
| **total Crusoe inference** | **587** | **710k** | **112k** | **$0.291** |

- $ per verified part: demo run **$0.0012** (1 part, 1 iter). Held-out A/B: $0.0597 / 11 physics-passed parts = **$0.0054**.
- Fine-tune cost: not in any file. Say "Crusoe credit" and nothing else. Deploy would be $22/hr (docs/BACKEND.md), not spent.
- Frontier comparison (published list price, G2 2026 guide: Claude Opus 4.8 $5 in / $25 out per MTok). Same token
  counts: demo run $0.052 (43x ours), held-out A/B $1.37 (23x ours). Caveat: token counts would differ on a
  different model; this is price-per-token only. Nemotron/DeepSeek per-token rates on Crusoe: not verified from a
  public page, so quote only the measured `spent_usd`.

## 3. Three things that MUST be true at 4:00

1. **A live, typed goal produces a part on screen with a referee verdict in under 3 min, with a labelled replay fallback.** TRUE today via `make ui` + `make demo` + `?replay=ui/fixture/br02`. FALSE for the Fusion Studio story: nothing builds a part in Fusion.
2. **The before/after table with $ exists and matches files.** TRUE: heldout.json 5/6 -> 6/6, 3.0 -> 1.0 iters, $0.06. LoRA "val loss 0.262 SUCCEEDED" has NO file behind it (only a "queued" PNG). Currently FALSE for that one claim.
3. **The repo state the judges see equals the demo state.** FALSE: HEAD is 5 ahead of origin/main, 10 uncommitted paths, PR #1 targets `demo-base` not `main`, `.bak` files and `forge/adapter.py`/`topopt_live.py`/`cfd_viz.py` untracked.

## 4. Critical path, 2:21 -> 4:00 (one path, one owner each)

- **2:21-2:30** Decide (founder, 5 min max): Studio-in-Fusion is a 2-hour build with zero on disk. Options:
  (a) ship FORGE loop UI as "the studio", SolidCraft/Fusion as a 20-second "and it lands in your CAD" beat;
  (b) bet the demo on a Fusion chat that does not exist. P(a works at 4:00) ~85 %. P(b) ~20 %.
  Recommendation: (a). Most likely way this is wrong: a judge specifically asks "is it in Fusion?" Answer: "yes, SolidCraft today, Fusion bridge is listening on 9876, next."
- **2:30-3:10** Minimum Fusion beat (one agent, hard cap 40 min): one script `forge/fusion_bridge.py` that POSTs the
  winning `part.step` from `runs/<run>/best` into Fusion via the LiveMCP add-in on 9876 and screenshots it. If not
  working by 3:10, drop it and use `solidcraft/shots/live_bracket_window.png` as the CAD beat.
- **2:30-3:00 (parallel)** Repo hygiene (one agent): commit adapter.py, cfd_viz.py, delete `.bak`, commit baseline shots,
  push `feat/forge-app`, retarget PR #1 to `main` or merge dev -> main. Get a Crusoe FT "succeeded" screenshot into
  `docs/evidence/` or change the AGENTS/README wording to "queued".
- **3:00-3:30** Rehearsal 1 with timer, full 3-min script from docs/DEMO.md, replay tab preloaded. Fix only what broke.
- **3:30-3:50** Rehearsal 2 + record the 1-min video (QuickTime). README top: one screenshot, the table, the $ line.
- **3:50-4:00** Freeze. `git tag freeze`, push main and dev.
- **CUT NOW:** ui/index.html redesign, topopt animation, any more SolidCraft work, FORGE.app polish, SQ-2 render fixes.

## 5. MecAgent positioning

- **What they do:** AI CAD copilot for mechanical engineers that models parts, generates drawings and runs automations inside SolidWorks from a sentence, spec sheet, drawing or STEP file (mecagent.com); f.inc-backed, also claims Fusion 360, CATIA, Inventor, Creo integrations, standards checks and cost estimation (f.inc portfolio page).
- **What we do differently:** every design goes through an LLM-free CalculiX referee on loads the designer never saw, with a parity gap between claimed and simulated stress; the team's memory (playbook, then LoRA weights) is kept only when it improves held-out score; runs on Nemotron via Crusoe at ~$0.001-0.005 per verified part, with the receipts in `runs/`.
- **One-line pitch:** "MecAgent draws what you ask for. FORGE proves it holds, learns from the parts that broke, and does it for half a cent on Nemotron."
