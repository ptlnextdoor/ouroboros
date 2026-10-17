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

## Dossiers (fable)

Researched 2026-10-17 10:45-10:55 PT under a 15-min cap. Venue IP was blocked by Google/DDG; sources are Bing snippets, Sessionize, GitHub, personal sites, LinkedIn post previews. CONFIRMED = read at the URL. INFERRED = my read on what lands, not a fact about them. Raj, Pranay, Kaan, Michelle, George Kalangi, Christina not researched (out of scope per task).

### FINAL ROUND

**Connor Guerrero** (Crusoe, Sr DevRel Manager, founding devrel team, joined Feb 2026; ex-Tenstorrent, ex-AONDevices edge-AI chips)
- CONFIRMED: ML engineer background on AI accelerators; built "fully local AI agent from scratch using vLLM" notebook; lists Agno, LangChain, OpenAI Agents SDK, Google ADK, Strands as agent tooling. https://www.connor-guerrero.com/ , https://github.com/c-jg
- CONFIRMED: speaks on GPU infra, training and inference workflows (MLSys 2026 lightning talk, AI Engineer Paris). https://sessionize.com/connor-guerrero/ , https://mlsys.org/virtual/2026/sponsor-lightning-talk/10004
- CONFIRMED: on AI Engineer podcast demoed Crusoe auto-detecting a dead GPU and restarting a training job with no human. https://finance.biggo.com/news/1cb9f885bf4d6b46
- SAY: "Every agent call is plain OpenAI-compatible vLLM on Crusoe Managed Inference, so the whole loop (designer, critic, playbook rewrite) is swappable to any model you host, and the referee runs with zero human in the loop." (INFERRED angle: hardware-pragmatic, likes self-healing automation.)

**Emmanuel Acheampong** (Crusoe, Sr Manager DevRel, founding Managed AI devrel; ex-cofounder/Head of AI yShade.ai; NVIDIA Developer Champion)
- CONFIRMED: ships Crusoe provider integrations everywhere (LiteLLM, Pydantic AI, Pipecat, Vercel AI SDK, Strands, aisuite, models.dev, pi-crusoe). https://github.com/acheamponge , https://github.com/acheamponge/pi-crusoe
- CONFIRMED: talk "No Single Model to Rule Them All: Building Resilient AI Agents Across Open & Closed LLMs" (multi-model routing, failover, match model to task). Also "Inference in Production" workshop (prefill/decode, KV cache, TTFT). https://sessionize.com/emmanuel-acheampong/
- CONFIRMED: built wassce-benchmark (evaluating open LLMs on a real exam) so he cares about evals on real tasks. https://github.com/acheamponge
- SAY: "Nemotron designs, a different model critiques, and the only ground truth is CalculiX, so a held-out FEA score, not model vibes, decides whether playbook N+1 ships." (Lands on his multi-model + real-eval thesis. If asked about tooling: we hit Managed Inference via the OpenAI-compatible endpoint, same path as his LiteLLM provider.)

**Piyush Kadam** (Crusoe, Group PM; ex-NVIDIA, ex-AWS)
- CONFIRMED: leads Crusoe's model customization / post-training service: "token shock" from agents, beat base-model on narrow use cases, "automate evals, queuing, scheduling, failure recovery, and serving", predictable token pricing. https://www.linkedin.com/posts/piyush-kadam_excited-to-share-what-my-team-and-i-have-activity-7485781348285095937-08ZB
- CONFIRMED: hosts Crusoe SF office builder meetups. https://www.linkedin.com/posts/piyush-kadam_the-crusoe-team-is-opening-our-sf-doors-wednesday-activity-7462333051327631360-afPh
- SAY: "Every kept playbook version is also a labeled dataset of spec -> verified part -> FEA score, which is exactly the post-training data you'd feed Crusoe's customization service to make a smaller Nemotron beat the base model on this domain." Show the live $ per verified part meter: it speaks directly to his "token shock" framing. (INFERRED: product-ROI lens.)

**Sako Mammadov** (You.com, Staff Backend Engineer, joined ~early 2026; prior DevOps/security eng at Gladly)
- CONFIRMED: ran You.com API workshop on extracting "clean, agent-ready Markdown context directly from public URLs" for agents; co-ran You.com Agentic Hackathon (Jul 2026). https://www.linkedin.com/posts/tejkiran-yenugunti_artificialintelligence-agenticai-softwareengineering-activity-7488412423561826305-w56n , https://luma.com/youdotcom-agentic-hackathon-sf
- CONFIRMED: background in DevOps and security engineering. https://www.youtube.com/watch?v=xcUNsomOq5Y
- SAY: "The spec agent pulls 6061-T6 and PETG yield allowables through You.com search with the citation URL written into checks.json, so the referee's pass/fail traces back to a source, not a hallucinated number." Then one line on sandboxing (OpenShell runs the agent-written CadQuery) for his security side. (INFERRED: will probe whether the search call is real and whether results are grounded. Have the raw You.com response ready.)

### ROUND 1: NVIDIA

**Sanjana Somayajula** (NVIDIA, PM; UW grad)
- CONFIRMED: LinkedIn headline snippet: "Combining OpenClaw, Red Hat OpenShift, and NVIDIA OpenShell is the perfect solution" and "four weeks of my..." (recent role, actively posting about OpenShell). https://www.bing.com/search?q=%22Sanjana+Somayajula%22+NVIDIA (LinkedIn: linkedin.com/in/ search result, profile itself not fetched)
- SAY: "Agent-written CadQuery is untrusted code, so it executes inside an OpenShell sandbox; the referee never trusts the designer's process." She likely works on or near OpenShell/NemoClaw; ask her what the right policy granularity is. (INFERRED.)

**Abhinav Balasubramanian** (NVIDIA, Staff AI Engineer; "scaling generative AI and agentic" systems; OpenReview researcher profile, patents; onboarded 7+ internal bots at NVIDIA)
- CONFIRMED: https://www.linkedin.com/in/abhi-bala (snippet), https://openreview.net profile, https://scrs.in resume PDF (via Bing). Hosted/attended "Agents for Impact" hackathon at SCU (Oct 2025). https://luma.com/user
- SAY: "The playbook is the only mutable memory, it's rewritten by an agent, and it's kept only if held-out FEA score goes up, so memory can't drift into superstition." Expect technical probing on how we avoid overfitting to the hidden load cases. (INFERRED.)

**Didi Kamalova** (NVIDIA, System Software Eng, "GPU systems @ nvidia", Stanford; headline "lpx @ nvidia")
- CONFIRMED: https://www.linkedin.com/in/dilnazkamalova (snippet), GitHub didikamalova (signal-processing project). Little public 2026 content found.
- SAY: "The FEA referee is CPU CalculiX, the designer is GPU Nemotron on Crusoe, and we run N design candidates in parallel against one referee so GPU time is the only thing that scales." (INFERRED: systems person, cares about where compute goes.)

### ROUND 1: Crusoe

**Janaki Ram Goteti** (Crusoe, Sr Staff SWE; leads serverless fine-tuning infra for open-source LLMs; ex-Microsoft, 14 patents; speaking at Open Source Summit Korea 2026 on supervised fine-tuning of OSS LLMs)
- CONFIRMED: https://osskorea2026.sched.com/speaker/jgoteti , https://huggingface.co/jgoteticrusoe , named by Piyush as core to the customization launch.
- SAY: "Each accepted playbook version yields SFT pairs with a physics-verified reward; the obvious next step is fine-tuning Nemotron on them with Crusoe's serverless fine-tuning." (INFERRED.)

**George Gulabyan** (Crusoe, Sr PM, "Building Serverless Inference"; ex-Moody's ML platform scaling)
- CONFIRMED: https://gulabyan.com , https://www.linkedin.com/in/gulabyan ; posted on OpenAI Operator / browser agents.
- SAY: "Burst of parallel designer calls then idle while FEA runs: serverless inference is the right shape for this workload, and the cost meter shows what one verified part costs." (INFERRED.)

**Shubham Amilkanthwar** (Crusoe, Staff Data Eng, leads data team, real-time data pipelines; InfoWorld contributor)
- CONFIRMED: https://www.infoworld.com/profile/shubham-amilkanthwar ; spoke on Confluent panel "What Your Agent Doesn't Know Yet" about getting agents into production with data. https://www.linkedin.com/in/shubhamamilkanthwar
- SAY: "Every run emits a structured event log (spec, candidate, FEA result, playbook diff, accept/reject), so the memory loop is auditable like a data pipeline, not a prompt blob." (INFERRED.)

**Martin Cala** (Crusoe, Staff Solutions Eng; customer-facing)
- CONFIRMED: authored Crusoe x Union.ai blog on orchestrated compute; "AI Lab" video on open-source inference with vLLM + SGLang; interviewed Windsurf on building on Crusoe. https://www.crusoe.ai/resources/blog/crusoe-cloud-union-ai , https://www.youtube.com/watch (AI Lab: vLLM + SGLang, Nov 2025), GitHub martin-cala1/crusoe-developer-hub.
- SAY: "This is the Windsurf story for hardware: a customer with a parts catalog points it at Managed Inference and gets verified designs with a cost per part." (INFERRED: thinks in customer use cases, knows vLLM serving.)

**Hemant Sethi** (Crusoe, Staff SWE, storage; co-leads AI-optimized object storage; MLCommons Storage WG; USENIX speaker)
- CONFIRMED: https://www.sethihemant.com/about , https://github.com/roolerzz , USENIX speaker page.
- SAY: "Playbook versions and FEA artifacts are content-addressed and immutable; rollback to version N is a pointer flip." (INFERRED: storage person, will like immutable versioned artifacts.)

**Rohit Kalmankar** (Crusoe, Sr Staff Solutions Eng; compute/storage/networking foundational layer; ex-C3 AI lead solution architect)
- CONFIRMED: https://www.linkedin.com/in/rohitkalmankar (snippet).
- SAY: "Enterprise-style framing: deterministic referee, versioned memory, budget cap, and a walk-away runtime, i.e. this can run unattended on Crusoe for a week." (INFERRED: C3 AI background = enterprise deployment lens.)

### Cross-cutting lines (use in the 2-min pitch)
1. "No single model to rule them all" is a Crusoe DevRel thesis (Emmanuel). Say designer and critic are separate models and the referee is not an LLM.
2. "Token shock" is Crusoe product's framing (Piyush). Show $ per verified part.
3. OpenShell is live in NVIDIA PM content (Sanjana). Say "untrusted agent code runs in OpenShell" once, clearly.
4. You.com: cite the URL inside checks.json on screen (Sako, Christina).
