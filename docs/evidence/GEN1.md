# Gen-1 weights: referee-verified designs → Nemotron LoRA

Tier-3 of the memory stack (notebook → playbook → **weights**). After the
playbook gate converged on `playbook/v2.md`, we distilled the referee-verified
designs the team produced under v2 into a LoRA fine-tune of the designer model
on Crusoe Managed Inference.

Status: **trained; promotion pending a deployed held-out gate.** The adapter
exists and its weights are on disk, but it is not yet served, so it has not been
scored on held-out parts. By our own promotion rule (weights are kept only if
the held-out score rises) it is a trained candidate, not a promoted generation.

## Job

| field | value |
|---|---|
| job id | `ftjob-0330cd18758a46da997c2a530677360a` |
| fine-tuned model id | `ftmodel-503f6289-c017-4e66-8351-ee8919f19c3f` |
| model name | `ft:nvidia-nemotron-3-5-nano-30b-a3b-bf16-07292026:forge-gen1:5087e8e3` |
| base model | `ftmodel-6c22bf52-fb65-4bd5-94c4-736f0a7d33f0` (crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16) |
| status | `succeeded` |
| model_type | `adapter` (`model_source: evolution`) |
| method | supervised LoRA, `n_epochs=3`, `lora_rank=16`, `lora_variant=lora`, `lr_scheduler=cosine`, batch/lr `auto` |

API: `https://api.intelligence.crusoecloud.com/v1`, key `CRUSOE_API_KEY` from
`.env` (surrounding single quotes stripped; see `forge/distill.py:_load_env`).
Reproduce any of the numbers below with `python -m forge.adapter --info`.

## Dataset

24 chat examples harvested by `forge/distill.py` from the **train split only**
(6 train tasks, `br01`–`br06`), deduped by clamped-params hash, capped at 4
examples per task, preferring the lightest referee-verified pass. The playbook
is **pinned to `playbook/v2.md`** so the adapter and the playbook it was trained
against travel together (`gens/gen1/manifest.json`).

| field | value |
|---|---|
| examples | 24 (22 train / 2 val, 10 % split) |
| source | referee-verified designs, train split only (dev/heldout refused + asserted) |
| playbook pinned | `playbook/v2.md` (sha1 `f248a5bb849024041eb918138a384e3ad3a6cb16`) |
| token estimate (chars/4) | ~30,467 |
| each example | `system` = playbook prefix, `user` = designer prompt, `assistant` = clamped params + claim + rationale (byte-identical to the serving path) |

## Training metrics (checkpoint-3)

| metric | value |
|---|---|
| train_loss | 0.2782 |
| valid_loss | 0.2625 |
| trained tokens | 320,958 |
| epochs | 3 |
| checkpoint id | `checkpoint-3-ftjob-0330cd18758a46da997c2a530677360a` |

## Cost

Serverless fine-tuning is billed per trained token at **$0.40 / 1M tokens**:

```
320,958 tokens × $0.40 / 1,000,000 = $0.128  ≈ $0.13
```

The Gen-1 adapter cost about **13 cents** to train.

## Adapter files

Downloaded with `python -m forge.adapter --download` (endpoint:
`GET /v1/models/{id}/download`, returns a zip; the three documented file-id
endpoints 400/404 because this is an `evolution` model record). Saved to
`gens/gen1/adapter/` (gitignored):

| file | size |
|---|---|
| `ftmodel-503f6289-...zip` | 597,607,658 B (~570 MB) |
| └ `adapter_model.safetensors` | 861,631,936 B (~822 MB unpacked) |
| └ `adapter_config.json` | 1,183 B |

`adapter_config.json` confirms a real PEFT LoRA: `peft_type=LORA`, `r=16`,
`lora_alpha=16`, `lora_dropout=0.0`, target modules
`q_proj,k_proj,v_proj,o_proj,up_proj,down_proj`, `task_type=CAUSAL_LM`.

## Serving status (honest)

The adapter model record has `inference_available: False`, `globally_available:
False`. A serverless chat call against both the model id and the fine-tuned name
at `https://api.inference.crusoecloud.com/v1/chat/completions` returns:

```
404 - {'code': 'model_not_found', 'message': 'Model not found: ftmodel-503f6289-...'}
```

So adapters are **not** served on the shared serverless endpoint. Serving the
LoRA needs a **Self-Serve Deployment** (one-click in the Crusoe console:
Fine-tuning → this job → Deploy, which stands up a dedicated endpoint at
~$22/hr). We deliberately did **not** create a paid deployment during the event.

Promotion path once deployed: point `forge/agents.py` designers at the deployed
adapter endpoint, rerun `forge.gate --heldout --playbook-a <base-designer>
--playbook-b <adapter-designer>` on the held-out tasks, and keep the adapter
only if the held-out score rises, the same gate the playbook tier already
passes.

## Reproduce

```bash
python -m forge.distill --dry-run         # rebuild gens/gen1/{train,val}.jsonl + manifest
python -m forge.adapter --info            # job + checkpoint metrics + model record
python -m forge.adapter --download        # adapter weights -> gens/gen1/adapter/
python -m forge.adapter --infer           # serverless probe (expected: 404 model_not_found)
```
