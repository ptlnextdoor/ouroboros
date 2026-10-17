# STAGE CARD (read this, nothing else, when nervous)

Rehearsed 2026-10-17 13:28 PT. `make demo TASK=br02 PLAYBOOK=playbook/v2.md` took **7 m 18 s** wall
(solved in 1 iteration, best 26.5 g, $0.0012). Run dir: `runs/br02_1792268889`. Cached copy: `ui/fixture/br02`.

## Live (two terminals, start the UI first)
```
# terminal 1  (UI, leave running)
cd ~/Workspace/developer/recursive-agents-hack && make ui
# terminal 2  (the run; UI auto-switches to it the moment it starts writing)
cd ~/Workspace/developer/recursive-agents-hack && make demo TASK=br02 PLAYBOOK=playbook/v2.md
```
Browser: **http://localhost:8008/**

## Replay (zero network, open in a second tab BEFORE you start)
**http://localhost:8008/?replay=ui/fixture/br02&speed=8**   (real run; `&speed=1` = real pacing, `&speed=40` = instant)

Fallback for the fallback: `python3 ui/serve.py` only needs stdlib; no conda, no FreeCAD, no key.

## What you will see, and when (live, ~7 min)
| t | event |
|---|---|
| 0:07 | spec: 5 done-means checklist chips |
| 0:15 | designer-0 params + grey part; referee runs (30-90 s per design, CalculiX) |
| 0:46 | verdict d0: FAIL (81.6 g, over mass) · red |
| 2:22 | verdict d1: ccx **timed out at 90 s** (thin 1.5 mm plate meshes badly). Shows as FAIL with the timeout reason. Say: "the referee refuses to guess." |
| 5:32 | verdict d2: **PASS · parity gap** (physics ok incl. 3 HIDDEN loads; agent claimed 88 MPa, FEA says 24, gap 270 %). Green. |
| 7:14 | d3: timeout. Then SOLVED / DONE · 1 iters. UI focuses the winning part. |

Referee panel: scroll shows `weight`, `g_load` (visible) then `side_knock`, `pull_off`, `overload_2x` (HIDDEN badge).
Playbook panel: latest gate round from `playbook/history.jsonl` (v3 REJECTED, dev 385.9 -> 384.4) with the diff.

## Flaky, with workaround
- **ccx 90 s timeouts** on thin designs (2 of 4 here). Expected, not a bug; they count as FAIL. If all 4 time out the loop goes to iter 1 (adds ~7 min): switch to replay.
- **Port 8008 in use** (`Address already in use`): `pkill -f ui/serve.py` then `make ui`, or `python3 ui/serve.py --port 8009`.
- The UI tails the *newest* `runs/**/events.jsonl`. If another agent kicks off a gate/heldout run during the demo the live tab will switch to it. Pin with `http://localhost:8008/?run=runs/br02_<ts>` (ts printed by the run) or stop other runs.
- Thumbnails/3D part need `ui/vendor/three` (vendored, no network). If the part is a PNG fallback, it is fine, keep going.
- HELD-OUT bars say "appears after first gate" until a `kind:heldout` record lands in `playbook/history.jsonl` (`make heldout` writes it). Not needed for the demo beat; say the numbers from the slide.

---

# Demo script (3 min) + 1-min video storyboard

## Live demo, 3:00 (rehearse ×3 with a timer at 4:15)
Setup: laptop on HDMI, `python3 ui/serve.py` open in a browser. A second tab has `?replay=runs/<best_run>` loaded as the fallback. Phone hotspot on.

| t | say (short) | screen |
|---|---|---|
| 0:00 | "Last night our own design optimizer picked a part with **negative drag** as its best result. Nothing caught it. Agents fill vague goals with assumptions and report success." | title / banner |
| 0:15 | "FORGE turns one line of engineering into a real part. Watch." *type:* `hold a 2 kg motor 80 mm off a wall, under 40 g` | goal box |
| 0:25 | "Nemotron writes its own definition of done: 3 g load, factor of safety 1.5, mass under 40 g, deflection limit." | checklist appears |
| 0:40 | "Four Nemotron-Lightning designers work in parallel. They pick engineering parameters, not raw CAD, because every model we tried failed 6 of 6 times at writing raw CAD." | 4 thumbnails, 3D part rotating |
| 1:00 | "Each one claims a stress. The referee is CalculiX, real FEA with **no LLM**, validated against beam theory at 0.18 %. It also runs loads the agents were never told about." | referee panel, HIDDEN rows |
| 1:20 | "This one passed everything it was told about, and failed a hidden side load. The parity gap shows the agent thought 40 MPa, physics says X. Done doesn't mean done until the referee says so." | red row, parity number |
| 1:40 | "The critic, a different model family, writes a hypothesis: stress concentrates at the corner, add a gusset. The next designs test it." | critic text |
| 2:00 | "After each run the team rewrites its playbook. Here's a rule it **kept**, because the dev score went up. Here's one the gate **rejected**." | playbook diff, kept/rejected |
| 2:25 | "On held-out parts it never saw, v0 vs vN: pass rate X→Y, iterations X→Y, at Z cents per verified part on Crusoe." | bar chart + $ meter |
| 2:45 | "Every number is checked by physics it can't fool. Run 100 beats run 1. Repo, replay and isolation proof are all public." | end card |

Rule: if any live step takes more than 15 s, say "switching to the recorded run from 2 PM" and use the replay tab.

## Q&A (one-liners)
- **Just prompt tuning?** The playbook is kept only if held-out score improves, and the referee is physics. Here's a rejected edit.
- **Could agents see the hidden loads?** No. `make verify-isolation` checks it, and hidden cases are applied only inside CalculiX.
- **n is small?** Yes. It's 6 held-out parts × 2–3 hidden cases each. The mechanism is the result, and the numbers are evidence it runs.
- **Why Crusoe?** Four parallel designers plus a critic per iteration at about $0.001 per design. The cost meter is live.
- **What's pre-existing?** CadQuery, gmsh, CalculiX and the models. Everything else was committed after 10:45 today.
- **Future?** Swap the referee for a test rig (load cell plus 3D printer) and the parity gap becomes a sim-to-real gap. Kept playbooks become fine-tuning data for Crusoe's customization service.

## 1-minute video (record at ~4:00 with QuickTime screen recording + voice)
| t | shot |
|---|---|
| 0:00–0:08 | banner + the negative-drag line |
| 0:08–0:20 | type the goal, the checklist appears |
| 0:20–0:35 | parallel designs, a referee FAIL on a hidden load, critic hypothesis |
| 0:35–0:48 | playbook kept/rejected + v0 vs vN on held-out |
| 0:48–0:60 | "Built today on Crusoe Managed Inference with Nemotron. github.com/ptlnextdoor/ouroboros" |
