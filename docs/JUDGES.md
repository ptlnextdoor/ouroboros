# Judges (from the kickoff slides, 2026-10-17)

## Final round (top 6 on stage, all criteria 25%)
| judge | role | what they'll reward |
|---|---|---|
| **Emmanuel Acheampong** | Sr. Manager, Crusoe (DevRel lead; wrote `pi-crusoe`, the Crusoe provider for the Pi coding agent) | real agent harness on Crusoe, model routing, reasoning-effort use, things devs would copy |
| **Connor Guerrero** | DevRel & ML Engineer, Crusoe | clean technical story, Nemotron and open models used well, reproducible repo |
| **Piyush Kadam** | Group Product Manager, Crusoe | a product Crusoe customers would run on Managed Inference: cost per result, scale, "walk away" |
| **Sako Mammadov** | Staff Back End Engineer, You.com | robust backend, retries and failure handling, You.com search used for a real purpose |

## First round (15, split across rooms)
| judge | org | lens |
|---|---|---|
| Janaki Ram Goteti | Crusoe, Sr Staff SWE | systems depth |
| Hemant Sethi | Crusoe, Staff SWE | systems depth |
| George Gulabyan | Crusoe, Sr PM | product, Crusoe fit |
| Shubham Amilkanthwar | Crusoe, Sr Data Eng | data, evals |
| Martin Cala | Crusoe, Staff Solutions Eng | customer use case |
| Rohit Kalmankar | Crusoe, Sr Staff Solutions Eng | customer use case |
| Sanjana Somayajula | NVIDIA, PM | Nemotron and NemoClaw use |
| Abhinav Balasubramanian | NVIDIA, Staff AI Eng | model and agent technicality |
| Didi Kamalova | NVIDIA, System Software Eng | infra and sandboxing (OpenShell) |
| Christina Lucey | You.com, Product Lead | You.com integration |
| George Kalangi | Apple, TPM | polish, clarity |
| Raj Jagiasi | Elite, Founder | startup potential |
| Pranay Periwal | Color, Founding PM | product story |
| Kaan Yigit | Stoa, Co-founder & CTO | technicality |
| Michelle Julia N. | Blue, Founder | startup potential |

## What this changes
- **Judges are software and infra people, not mechanical engineers.** They can't grade FEA depth, so make the physics legible: red → green stress, "the referee caught it", a parity number.
- **10 of 19 judges are from Crusoe.** Show Crusoe-native engineering on screen:
  - parallel sub-agents on `nemotron-3.5-lightning`
  - a **live $ cost meter per verified part**, with prefix-cache hits
  - budget enforcement and walk-away runtime
- **3 NVIDIA judges are in round 1.** Nemotron in every agent role, and OpenShell sandboxing for the agent-written CadQuery code (it's untrusted code, so sandboxing is a natural fit).
- **You.com has a final judge and a round-1 judge.** The spec agent uses You.com search to pull material allowables (6061-T6, PETG yield) **with citations** into checks.json. It's a small integration that clearly matters.
