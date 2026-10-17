# Winner audit: what wins at Cerebral Valley hackathons

Data: 4,280 projects from 61 Cerebral Valley hackathon galleries (the organizer of this event), 331 of them
award winners, 155 of those in San Francisco. Scraped 2026-10-17 from the public JSON-LD on each gallery.
Raw data: `cv_winners_audit.json`.

## Theme lift (share of winners with the theme ÷ share of non-winners with it)

| theme | lift | read |
|---|---|---|
| robot / physical / hardware | **1.59** | tangible artifacts win |
| RL env / simulation | **1.56** | |
| visual / 3D / game | **1.44** | demo-able |
| voice | 1.49 | not our track |
| train weights / fine-tune | 1.08 | neutral |
| self-improving (generic) | 1.03 | neutral by itself |
| memory | 0.89 | crowded |
| science research | 0.87 | |
| multi-agent | 0.76 | crowded |
| **eval / verifier / judge (alone)** | **0.66** | a pure "referee" pitch loses |
| finance | 0.38 | |

## Closest analogs (recent, same organizer, same "recursive / self-improving" framing)

| event | place | project | pattern |
|---|---|---|---|
| MongoDB NYC, 2026-09-26 | **1st** | Ripple | plain English → circuit board, **hidden checks**, harness evolves from failures, 0/4 → 3/4 |
| MongoDB SF, 2026-10-11 | **1st** | MongoMation | autonomous PLC engineer, real hardware |
| MongoDB SF, 2026-10-11 | 2nd | LabRat | self-improving harness for a physical lab robot |
| MongoDB SF, 2026-10-11 | 3rd | Recursive Harness Scientist | AI scientist must replicate gains on unseen data (≈ thermal idea) |
| GPT-6 Astra SF, 2026-09-08 | **1st** | CAD Sandboxes | agents driving CAD |
| AIEWF 2026 | **1st** | SplatForge | robot agent trains itself in reconstructed worlds |
| OpenEnv SF | **1st** | Kube SRE Gym | small model self-improves via RL env |

**Winning formula:** an agent that makes a *physical engineering artifact*, is graded by *hidden checks*,
improves its *own harness* from failures, and shows *before/after on unseen tasks*.
The verifier is the mechanism. The artifact is the headline.
