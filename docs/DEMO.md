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
