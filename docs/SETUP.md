# Setup: do this the night before

Goal: walk in Saturday with every risky dependency already proven. Nothing here is project code.

## 0. Accounts
- [ ] Crusoe: sign up at <https://console.crusoecloud.com/request-foundry>. One teammate creates the org and invites the others. **A credit card is required to get the free credits.**
- [ ] Claim the $50 credits: <https://forms.gle/JdEvMGSb4TURH1Tq8>
- [ ] Create an API key, **expiry 2026-10-18**, and save it to `.env`
- [ ] You.com platform account (optional, for agent web search)
- [ ] Join Discord, react 🔄 in #access

## 1. Crusoe endpoint smoke test
```bash
export CRUSOE_API_KEY=...
curl -s https://api.inference.crusoecloud.com/v1/models \
  -H "Authorization: Bearer $CRUSOE_API_KEY" | jq -r '.data[].id'

curl -s https://api.inference.crusoecloud.com/v1/chat/completions \
  -H "Authorization: Bearer $CRUSOE_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"zai/GLM-5.3","messages":[{"role":"user","content":"say ok"}],"max_tokens":5}'
```
Model IDs listed in the docs as of 2026-10-16: `zai/GLM-5.3`, `zai/GLM-5.3-Flash`,
`deepseek-ai/DeepSeek-V4-Pro`, `deepseek-ai/DeepSeek-V4-Flash`, `openai/gpt-oss-120b`,
`nvidia/Nemotron-3-Nano-30B-A3B`, `nvidia/Nemotron-3-Super-120B-A12B`, `qwen/Qwen3.8-27B`,
`google/gemma-4-31b-it`. **Confirm against `/v1/models`.**

## 2. Cluster access from outside the home network
- [ ] Tailscale (or ssh jump host) works **from a phone hotspot**, not just home Wi-Fi
- [ ] `tmux` installed so jobs survive disconnects
- [ ] `nvidia-smi` shows 8× A100 80GB, driver/CUDA versions noted

## 3. Student model: the riskiest step (about a 30% chance it breaks)
Nemotron-3-Nano is a hybrid Mamba-Transformer MoE. Prove both halves:

```bash
uv venv && source .venv/bin/activate
uv pip install vllm "transformers>=4.5x" trl peft accelerate datasets

huggingface-cli download nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B   # BF16 for training
huggingface-cli download Qwen/Qwen3-8B                           # fallback
```

**A. Serving with LoRA**
```bash
vllm serve nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --tensor-parallel-size 2 \
  --enable-lora --max-loras 4 --max-lora-rank 32 --trust-remote-code
```
**B. Training a LoRA**: 10 steps of SFT with PEFT on any tiny dataset, then save the adapter.
**C. Round trip**: load the adapter from B into the server from A
(`POST /v1/load_lora_adapter`) and get a completion.

| Result | Decision |
|---|---|
| A + B + C pass | Student = Nemotron (best case for the Nemotron prize) |
| any fails | Student = Qwen3-8B. Nemotron-3-Super becomes the Auditor on Crusoe |

Follow NVIDIA's official LoRA guide if PEFT target modules are unclear:
<https://docs.nvidia.com/nemotron/0.1.0/use-case-examples/sql-lora-finetuning-and-deployment/README.html>

## 4. Data
- [ ] Training pool with **real** tests: TACO and/or APPS train, CodeContests train
- [ ] Held-out: LiveCodeBench problems released **after** the student's training cutoff (easy + medium, at least 300)
- [ ] Fallback held-out: HumanEval+ / MBPP+ (note the contamination caveat if used)
- [ ] Dedupe check: no held-out problem text appears in the training pool

## 5. Measure throughput (sets the generation budget)
Time one batch: 100 problems × 16 samples. Multiply out to 600 × 16. If that takes more than 25 min, cut the pool size.

## 6. Agent tooling
- [ ] Coding agent configured with `CLAUDE.md`
- [ ] Spec skill ready (`/interview` or `/grill-me`)
- [ ] Unused skills/MCPs turned off (too many slows the agent down)

## 7. Sleep
This is a 6-hour hack. Being rested is worth more than another hour of prep.
