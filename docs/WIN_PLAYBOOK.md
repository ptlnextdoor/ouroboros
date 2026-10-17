# WIN PLAYBOOK: Parts Agent, Recursive Agents Hackathon (2026-10-17)

Written 09:45 PT, 20-minute research sprint. Sources: the five winner READMEs linked in
`cv_winners_audit.json` (Ripple NYC, MongoMation, LabRat, SplatForge, CAD Sandboxes), the
NemoClaw / OpenShell / nemoclaw-community READMEs and the nvidia.com NemoClaw page, plus
`WINNER_AUDIT.md` and `HARVESTED_SKILLS.md`. Odds are stated as numbers. No fluff.

**Bottom line:** the parts agent is the right pick (physical 1.59x, sim 1.56x, 3D 1.44x, all three
lifts stack; pure evaluator 0.66x so the *referee must never be the headline*). Claim **Version N+1**
as primary, **Done Means Done** as the mechanism, Shared Brain as a one-line footnote. Stack the
Nemotron prize by making Nemotron the *designer* (the model that gets better), and the NemoClaw
prize by running the designer inside an OpenShell sandbox whose network policy is the proof it
never saw the hidden load cases.

P(top 6): 50 to 60%. P(1st): 20 to 30%. P(Nemotron side prize): 30 to 40%. P(NemoClaw prize): 15 to 25%
(only if the sandbox install works by 12:30, otherwise drop it).

---

## 1. How the winners structured their 3-minute demos (what actually repeats)

| Winner | Headline artifact | Hidden check | Self-improvement claim | Honesty move |
|---|---|---|---|---|
| **Ripple** (1st NYC) | Circuit board from plain English | `checks/` dir "agents never read" | harness redesigns itself from failures, **0/4 → 3/4** | README is 700 bytes, DESIGN.md + AGENTS.md. Tiny repo, one number. |
| **MongoMation** (1st SF, last week) | PLC code on a *real* OpenPLC + Factory I/O rig | "pure grader... hidden tests the model never sees", `npm run verify:isolation` fails if agents can reach hidden tests | meta-agent behind "guardrails and a benchmark gate" | Results table with run times and $ cost. Then: **"No harness change has been kept by the gate yet."** They won 1st *saying their self-improvement produced nothing*. |
| **LabRat** (2nd SF) | Real bench, two arms, CNC pipette | digital twin dry-run, human approves | colour model refit from measured results | predicted vs measured per beaker |
| **SplatForge** (1st AIEWF) | Phone scan → splat → MuJoCo robot | VLM critic | success curve 40% → 85% | "overnight run is replayed, labeled as such" |
| **CAD Sandboxes** (1st Astra) | CAD + live JLC3DP quote | real vendor price | none | the artifact was physical-money real |

**The repeating structure (copy it exactly):**
1. **One-line input typed live** (10 to 20 s). Plain English → engineering artifact.
2. **Something visual appears inside 60 s** (board render, 3D twin, the plant running). For us: the STL rendering in a 3D viewer.
3. **A referee the agent cannot read says FAIL with a measured number** (not an LLM opinion).
4. **One table: before vs after, hidden set, with a cost/time column.** MongoMation's table had 5 columns and judges quoted it.
5. **An honest limitation sentence.** Every 1st place README says what did *not* work. Judges at CV events reward this; it's the Q&A inoculation.
6. **Isolation is demonstrable, not asserted.** MongoMation shipped `npm run verify:isolation`. We ship `make verify-isolation` (greps the agent tree for imports of `referee/hidden/`, and the OpenShell policy denies the path).

**What they did NOT do:** no slides past one title card, no architecture diagram talk in the first 90 s, no dashboard tour. Dashboards are banned as main feature anyway.

## 2. Side prize stacking

### Best Use of NemoClaw & OpenShell
What the stack is (from the READMEs): NemoClaw = blueprint composing **Model + Harness + OpenShell**. OpenShell = kernel-enforced sandbox with **per-agent filesystem/network/process policy**, credentials injected only for approved endpoints, "formally verified policy changes" flagged for human review. Supported harnesses: OpenClaw (default), Hermes, LangChain Deep Agents. nvidia.com use cases literally list **"Transform Product Design and Manufacturing: automate geometry iteration, thermal design"** and **"Operate 3D Design and Simulation Tools... inside governed sandboxes."** Our project is their marketing copy.

"Best use" means the sandbox does something *load-bearing*, not decorative. Three load-bearing uses, pick in order:
1. **Policy as proof of hidden-check isolation.** Designer agent runs in an OpenShell sandbox. Policy: read/write `work/`, deny `referee/hidden/`, network egress only to `api.inference.crusoecloud.com`. Show the policy file on stage (10 s): "the agent *cannot* read the hidden load cases, enforced in the kernel, not by a prompt."
2. **Always-on loop.** The playbook-evolution loop runs unattended in the sandbox during the demo; the judge sees an iteration tick over live.
3. **Policy-change review as a drift catch.** If a playbook rewrite tries to add a new tool that needs new network access, OpenShell flags it. That is "catch drift" for Done Means Done, for free.

Install path: `curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh && openshell sandbox create --name designer` (macOS Apple Silicon is supported, needs Docker/Podman). Skills: `npx skills add NVIDIA/OpenShell`. **Hard rule: Krish times-boxes this to 45 min starting 11:00. Not working by 11:45 → drop it, say "Docker policy fallback" in Q&A if asked.** Don't bother with full NemoClaw installer (OpenClaw/Hermes harness) - OpenShell alone with our own harness is enough and the community README confirms "when to use NemoClaw versus OpenShell alone" is a recognised split. Mention NemoClaw by name in README as the blueprint we follow (Model: Nemotron on Crusoe, Harness: ours, OpenShell: policy).

### Best Use of Nemotron (RTX 5090)
Which role makes it obviously "best use": **the designer, the thing that improves.** Not the referee, not the auditor. If Nemotron is only a juror, the prize story is "we used it as one of three graders" = weak. If **Nemotron-3-Super-120B (or nemotron-3.5-lightning-30b-a3b for speed) writes the CadQuery code and its playbook is what goes v1 → v2**, the headline number *is* a Nemotron number. Use a second family (DeepSeek-V4-Pro or GLM-5.3) as the spec-to-checks writer and gpt-oss-120b as auditor so "no model grades itself" survives. Say the phrase "Nemotron went from X/10 to Y/10 on unseen parts" out loud. That sentence wins the prize or nothing does.

Fallback: if Nemotron-Super CadQuery quality is bad in the first 30 min of testing (11:15 checkpoint), use nemotron-3.5-lightning-30b as designer and keep the gap story: a small open model that *learns its playbook* beats its own v1.

## 3. Track choice

**Primary: Version N+1.** Its rubric ("keeps changes only if measurably better, before/after on unseen tasks") is literally our held-out gate. Secondary: **Done Means Done** (agent writes its own measurable checks from the one-liner, the referee catches drift, loop detector on repeated identical failures). Shared Brain: one sentence, "the playbook is the shared memory; its quality is measured on the held-out set", do not build anything extra for it.

How one build hits all three:
- The **spec → checks** step (agent writes "mass < 40 g, max von Mises < 0.5 σ_yield at 2 kg × 1.5 g-factor, deflection < 0.5 mm, all 4 bolt holes present") = Done Means Done definition of done.
- The **referee with hidden load cases** (e.g. side load 20 N the spec never mentioned, 3× g drop, mounting-face flatness) = catches drift between "what the agent checked" and "what the part must actually survive".
- The **playbook rewrite → held-out 10 parts → keep iff score improves** = Version N+1.
- **Parity gap** |agent voxel claim − CalculiX| is the Shared Brain "measurable quality" and the Done Means Done "verify" number in one.

Pick ONE sentence for the title card: *"Agents that design real parts, grade themselves against physics they can't see, and only keep the lessons that hold up on parts they've never seen."*

## 4. Judge Q&A attacks and crisp answers

| Attack | Answer (≤ 15 s) |
|---|---|
| "Isn't this just prompt tuning?" | "The thing that changes is a playbook of engineering rules the agent wrote from its own failures. Kept only if held-out score rises. Prompt tuning has no referee and no held-out set; this has both, and here's a rewrite the gate *rejected*." (Have one rejected rewrite in the log. If none got rejected, say so and show the gate code.) |
| "How do you know the agent didn't see the hidden load cases?" | "Three ways: separate directory the agent tree can't import (`make verify-isolation` fails the build if it does), the OpenShell policy denies the path at the kernel, and the hidden cases are only applied by CalculiX, a solver the agent never calls." |
| "Voxel FEA vs CalculiX, aren't both just sims?" | "Yes, and that's the point: the gap between the agent's fast sim and the independent high-fidelity solver is the sim-to-real stand-in. We validated the voxel kernel against the analytic cantilever (PL³/3EI) before trusting it. The parity gap shrinking from v1 to v2 means the agent learned to design parts its own model predicts correctly." |
| "n=10 unseen parts, is that significant?" | "No, and we won't claim it is. 10 parts × 3 hidden cases = 30 binary checks; we report the paired delta and say the CI. The mechanism is the result; the number is the evidence it runs." |
| "What's pre-existing?" | "CadQuery, gmsh, CalculiX, numpy: tools. Methods from our prior aero work, listed in PROVENANCE.md. Every line of agent, referee, and gate code was committed after 10:45 today." |
| "Why Crusoe?" | "All four model roles are Crusoe Managed Inference: Nemotron designs, DeepSeek writes checks, gpt-oss audits. Different families so no model grades itself." |
| "Where does this go?" | "Every spec'd bracket, mount, and housing in a hardware company. The referee becomes a real test rig (load cell + 3D printer), the parity gap becomes sim-to-real. Same loop." |
| "Did the agent reward-hack?" | Have one example ready: e.g. agent thickened everything to pass stress, failed mass cap; or claimed 0 stress on a mesh failure. "Yes, here, and the referee caught it because mesh failure is an explicit FAIL, never a skip." |

## 5. Three-minute demo script (with fallbacks)

Pre-stage: terminal + 3D viewer (trimesh/pyvista window or a simple three.js page) side by side. All v1/v2 artifacts cached on disk. Phone hotspot on. Two terminals: one live, one `cat`-ing cached output if live dies.

| t | Beat | Live or cached | Fallback |
|---|---|---|---|
| 0:00 | Title card, one sentence (above). "Hardware teams spec parts in one line. Agents turn it into geometry nobody has verified." | | |
| 0:15 | Type live: `bracket holds 2 kg motor 80 mm off wall, <40 g`. Agent emits its definition of done: 5 numeric checks appear. | **Live** (Crusoe call, ~5 s) | cached checks.json, say "cached, same call" |
| 0:40 | CadQuery runs, STL appears in viewer, rotates. Mass printed. | Live (geometry gen ~10 s) | cached STL |
| 1:00 | Referee: CalculiX von Mises plot, and the hidden side-load case: **FAIL, 310 MPa vs 150 allowed**. "The agent never saw this load. The policy file says so." Flash OpenShell policy 5 s. | cached ccx result (ccx takes 30 to 90 s) | same |
| 1:30 | The table. v1 vs v2 on 10 unseen parts: pass count, mean parity gap, mean mass margin, $/part. Point at one row where v2 failed too. | cached | |
| 1:55 | Playbook diff: 3 rules v2 learned ("fillet the wall junction", "check side load even if unspecified", "mass = ρV from the STEP, not from your estimate"). Then the gate log: one rewrite **rejected** because held-out dropped. | cached | |
| 2:25 | Hot path: run v2 on the same bracket, hidden case now PASS, parity gap 8% vs 41%. | Live if ccx cached for this exact part; else cached | |
| 2:45 | Close: "Nemotron designed every part. It went from X/10 to Y/10 on parts it never saw, and the referee never let it grade itself." Honest line: "n is 10; the mechanism is what we're showing." | | |

Rehearse ×3 with a timer at 4:15. If any live step exceeds 15 s, flip to cached and say so. Judges reward a labelled cache over a stall (SplatForge did exactly this and won).

## 6. Build timeline 10:45 → 5:00, 2 humans + coding agents

Interfaces frozen at 10:55 so everything runs in parallel: `spec.txt` → `checks.json` → `part.py` (CadQuery) → `part.step/.stl` → `agent_claim.json` → `referee.json {pass:[], fail:[], parity_gap, mass}` → `playbook.md` versions → `gate.json {v, heldout_score, kept}`.

| Time | Aayu (mech/aero, CAD + FEA) | Krish (Rust/agents, orchestration) | Coding agents |
|---|---|---|---|
| 10:45 | `git init`, first commit, README with title sentence + PROVENANCE.md. Freeze interfaces (10 min). | Crusoe key, `curl /v1/models`, confirm Nemotron-Super + DeepSeek + gpt-oss IDs. | |
| 11:00 | Referee: STEP → gmsh → ccx wrapper, hidden load cases file, mesh-fail = FAIL. Analytic cantilever self-check for voxel FEA. | OpenShell install + sandbox + policy (**45 min cap, kill at 11:45**). | A1: voxel FEA kernel (numpy) with self-check. A2: spec → checks prompt + schema. |
| 12:00 | **Checkpoint 1.** One bracket end-to-end by hand: spec → CadQuery → ccx verdict. If not, cut voxel FEA, use ccx only. | Agent loop: designer (Nemotron) → CadQuery exec in sandbox → self-sim → claim. Loop detector (same code hash 3× → stop). | A3: 20 spec corpus (10 dev, 10 held-out), varied: brackets, mounts, clips, standoffs. |
| 1:00 | Run v1 on 10 dev parts. Collect failures. | Playbook rewrite agent (DeepSeek or GLM reads failures, proposes rule diff). Gate: run held-out, keep iff score up. | A4: `verify-isolation` script, results table generator. |
| 2:00 | **Checkpoint 2 (hard).** v1 held-out score exists. If no playbook loop yet: ship v1 + referee + one manual playbook edit scored on held-out. | Run gate loop: aim 3 to 5 rewrites, expect 1 to 2 kept, ≥1 rejected. | A5: 3D viewer page (trimesh → three.js or pyvista screenshots). |
| 3:00 | Cache every demo artifact. Pick the demo bracket (one that v1 fails and v2 passes; if none, pick the biggest parity-gap improvement). | Auditor pass (gpt-oss) over v2 code for reward hacks; log findings. | A6: README results table, honest limits section. |
| 4:00 | **Feature freeze.** | Record 1-min video (screen capture of the demo path). | |
| 4:15 | Rehearse ×3 with timer. Fix only what breaks the demo. | | |
| 4:45 | Final commit, public repo, submission form. | | |

Cut points: 11:45 OpenShell (drop); 12:00 voxel FEA (drop, ccx only); 2:00 automated playbook loop (manual edit, still gated); 3:00 anything not in the demo table.

## 7. Five most likely ways we lose, and the mitigation

| # | Loss mode | P | Mitigation |
|---|---|---|---|
| 1 | **CadQuery/ccx pipeline eats the afternoon** (OCC booleans, gmsh failures, FreeCAD unit mN·mm bug). No v2 by 2:00. | 40% | Aayu owns this alone from 11:00, stays on a *single* primitive family (box + holes + fillets). Mesh fail is a verdict, not a crash. Hard cut at 2:00 to manual playbook edit. |
| 2 | **v1 → v2 gain is zero or noise.** | 35% | This is survivable if framed as MongoMation did ("gate kept nothing yet"). Show the rejected rewrites and the parity-gap trend. Pre-seed with easy wins: v1 playbook deliberately has no "check unspecified side load" rule, so hidden case 1 is a near-certain v2 learnable. |
| 3 | **Judges read it as an evaluator project** (0.66x lift). | 30% | First 60 s is the part appearing and rotating. Referee enters only as the villain at 1:00. Title sentence leads with "design real parts." Never say "eval harness" on stage. |
| 4 | **Live demo stalls** (Crusoe latency, wifi, ccx 90 s). | 25% | Only two live calls (checks, geometry), each with cached twin and a spoken label. ccx never runs live. Hotspot. Rehearsed ×3. |
| 5 | **Side-prize work dilutes core** (OpenShell install rabbit hole, model shopping). | 25% | 45-min cap on OpenShell, 30-min cap on Nemotron quality test. Krish decides at 11:45 and 11:15 respectively; no revisiting. |

Most likely way this whole playbook is wrong: judges at this specific event weight "recursive" novelty over artifact tangibility, and a pure weight-training team out-flashes a bracket. Counter: say "the playbook is the weights of an engineering team" and show that the rules are legible, which weight updates never are.
