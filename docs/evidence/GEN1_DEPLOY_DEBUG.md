# GEN1 deploy debug: why `forge-gen1` Fused LoRA failed

Date: 2026-10-17 15:52 PDT. Read-only investigation (no deployment or job touched).

## Verdict

**Hypothesis B is correct: "Nemotron 3.5 Lightning 30B A3B" in the console IS the
`crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16-07292026` fine-tuning base. There is no
base mismatch.** The deployment failed because the replica never became ready inside
Crusoe's 40-minute provisioning ceiling ("0 of 1 replica available" at exactly +40m18s).
That is a readiness timeout, not a config rejection. Most likely cause: the fused-LoRA
merge + engine start for this hybrid Mamba-MoE adapter (11,824 LoRA tensors, per-expert
LoRA on 128 experts x 29 MoE layers) did not finish, or the engine crashed on load, inside
the window. Crusoe exposes no engine logs, so the exact engine error is not retrievable.

## Evidence

### 1. The deployment object (real API, not the OpenAI-compatible hosts)

Deployments live at `https://api.crusoecloud.com/v1/projects/{PROJECT_ID}/foundry/selfserve`
(found via Crusoe support article 56533535142427). Project id = `625de128-87a0-423c-b42f-5b00c034e32d`
(the `owned_by` on our ftmodels). Needs `-A curl/8.7.1` (Cloudflare blocks default python UA).

`GET .../deployments/nvidia-nemotron-3-5-lightning-fc72a4f4`:

```json
{"id":"nvidia-nemotron-3-5-lightning-fc72a4f4","deployment_name":"forge-gen1","status":"failed",
 "model":"NVIDIA-Nemotron-3.5-Lightning-30B-A3B","base_model":"NVIDIA-Nemotron-3.5-Lightning-30B-A3B",
 "quantization":"bf16","gpu_type":"h100","gpus_per_replica":4,"target_replicas":1,"available_replicas":0,
 "fine_tuned_model":"ftmodel-503f6289-c017-4e66-8351-ee8919f19c3f","flavor_type":"throughput",
 "hourly_cost":"22","created_at":"2026-10-17T21:56:06Z"}
```

`GET .../deployments/nvidia-nemotron-3-5-lightning-fc72a4f4/activity`:

```json
{"events":[
 {"event_type":"deployment_failed","title":"Deployment failed","message":"0 of 1 replica available","timestamp":"2026-10-17T22:36:24Z"},
 {"event_type":"deployment_created","title":"Deployment created","message":"Created \"forge-gen1\" with 1 replica","timestamp":"2026-10-17T21:56:06Z"}]}
```

created 21:56:06Z, failed 22:36:24Z = **40m18s**. Crusoe docs: "Provisioning reserved
capacity can take up to 40 minutes." The failure is the deadline firing. No other error text
exists anywhere in the API.

### 2. Base identity: Lightning == Nano-07292026

- The API **accepted** `fine_tuned_model: ftmodel-503f...` (base_model_id `ftmodel-6c22...` =
  `crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16-07292026`) onto the
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B` flavor. Docs: "A checkpoint can only be deployed
  onto the base model architecture it was trained against ... will not appear as a selectable
  checkpoint under any other base model." The console listed checkpoint-3 under Lightning
  (coordinator-verified), so Crusoe's registry maps our base to Lightning.
- Fine-tuning `GET /v1/models` (intelligence host) lists exactly one Nemotron 3.5 base:
  `crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16-07292026`. Crusoe's fine-tuning docs list
  "Nemotron 3.5 Lightning 30B A3B" as the fine-tunable model. Same object, two names.
- Serverless inference `GET /v1/models` lists `nvidia/Nemotron-3.5-Lightning-30B-A3B`
  (bf16, 32.9B params, ctx 262144). Our deployment's `context_length` is also 262144, bf16.
- Self-serve "Available models" doc entry `nvidia/nemotron-3.5-lightning-30b-a3b` links to HF
  `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-NVFP4`; Crusoe serves a BF16 re-upload under
  the `crusoeai/` org (same pattern as `crusoeai/gpt-oss-120b-BF16`). "07292026" is the
  checkpoint date tag.

Hypothesis A (base mismatch) is dead: the platform would not have listed the checkpoint or
accepted the create call.

### 3. Flavor matrix for this base (`GET .../flavors`, 58 flavors)

| model | flavor_type | gpu | n | quant | fused_lora | multi_lora | lora_suitable | $/h |
|---|---|---|---|---|---|---|---|---|
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B | throughput (used) | h100 | 4 | bf16 | **true** | false | **true** | 22 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B | responsiveness | h100 | 8 | bf16 | true | false | true | 44 |
| NVIDIA-Nemotron-3.5-Lightning-30B-A3B | multi_lora | h200 | 2 | bf16 | false | **false** (max_lora_rank 64, max_loras 16) | false | 12 |

The flavor we used is officially Fused-LoRA capable, so this is not an "unsupported
combination" rejection either. The `multi_lora` flavor exists but is flagged
`multi_lora_supported: false, lora_suitable: false` on every model: multi-LoRA is not live
yet on Crusoe. **No serverless adapter path exists**: docs state "Serverless Inference ...
serves base models only. It does not accept custom or fine-tuned models at all."

### 4. Adapter shape (local zip `gens/gen1/adapter/ftmodel-503f...zip`)

- `adapter_config.json`: PEFT 0.19.1 LORA r16 alpha16, target_modules q/k/v/o/up/down_proj,
  `base_model_name_or_path = .../crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16-07292026`.
- `adapter_model.safetensors`: **11,824 tensors**. Attention layers (5,12,19,26,33,42): 8
  tensors each (q/k/v/o x A/B). 29 MoE layers: 512 tensors each =
  `layers.N.mixer.experts.{0..127}.{up,down}_proj.lora_{A,B}` (per-expert LoRA, from job
  config `expert_lora_sharing: per_expert`, `target_parameters: [up_proj, down_proj]`,
  `quant_lora_method: weight_lora`). Mamba layers: untouched.
- Job training config: `ep_type: nemotron_h_ep`, `ep_size: 8`, `export_merged_native: false`.

Why this matters: fusing 3,712 per-expert LoRA pairs into packed MoE expert weights, then
loading a Nemotron-H hybrid (Mamba2 + MoE + attention) into the serving engine with
TP=4 and a 262k context, is the heaviest fused-LoRA path Crusoe offers. The 40-min budget
is shared between GPU capacity acquisition and engine readiness; the console showed 30%
"Loading model, starting server" for ~40 min, i.e. capacity was acquired and the engine
never reported healthy.

### 5. Platform flakiness today

Fine-tune job events: `[State: TRANSIENT_FAILED] error=Internal server error` at
13:38 PDT during ENGINE_PENDING, auto-retried and succeeded. Serverless chat completions
against the Lightning base returned `rate_limit_error: max_requests_limit (orchestrator)`
at 15:49 PDT. Crusoe's inference control plane is under load right now.

## Exact fix (ordered, pick first that fits budget)

### Fix 1 (recommended): retry the same deployment, 8xH100 responsiveness flavor

Console: Intelligence Foundry -> Model Shaping -> Serverless Fine-Tuning -> job
`ftjob-0330cd18758a46da997c2a530677360a` -> checkpoint-3 row -> three-dot -> **Deploy**.
Base will pre-populate as "Nemotron 3.5 Lightning 30B A3B" (correct, leave it). Choose
configuration **Responsiveness (8xH100, $44/h)**, replicas 1, name `forge-gen1-v2`
(alias must be unique; old failed one still holds `forge-gen1`). Delete the failed
`forge-gen1` deployment first (stops any residual billing, frees the alias).

Why 8xH100: TP=8 halves per-GPU weight footprint and merge memory, and more SMs shorten
the merge/compile. Same `fused_lora_supported: true`. Cost for a 1h demo window ~$44.

P(success) ~ 55%. Most likely way it's wrong: the engine is crashing deterministically on
the per-expert LoRA merge for Nemotron-H (not a resource/time issue), in which case any
flavor fails identically at +40m.

### Fix 2 (cheap retry): same 4xH100 throughput flavor again

Pure transient-capacity/load retry. P ~ 35%. Costs $22/h. Only worth it if Fix 1 is over
budget. Watch the activity log; if it is still at "Loading model" at +25 min it will fail.

### Fix 3 (fallback, off-platform, ~2-3 h): merge + serve ourselves

We already have the adapter locally (862 MB). Merge with PEFT into
`crusoeai/NVIDIA-Nemotron-3.5-Nano-30B-A3B-BF16-07292026` (needs HF access to the
crusoeai repo or the nvidia Nano BF16 equivalent, ~60 GB bf16), serve merged weights with
vLLM on a single rented H100 80GB. Note vLLM's LoRA runtime does not support per-expert
LoRA on MoE experts, so **merge first, do not serve the adapter dynamically**. P ~ 60%
conditional on getting the base weights; risk is Nemotron-H support/version drift in vLLM.

### Not viable

- Serverless inference with adapter: not offered (base models only).
- Multi-LoRA flavor: present in the API but `multi_lora_supported: false`; would be
  rejected or fail.
- API-side `fine_tuned_model_id` of the *checkpoint* vs *job*: both are `ftmodel-503f...`
  here (single checkpoint), so no id confusion.

### Escalation

Open a Crusoe support ticket with deployment id `nvidia-nemotron-3-5-lightning-fc72a4f4`
and ask for the engine log; the public API hides it. Mention: Nemotron 3.5 Lightning,
fused LoRA, per-expert LoRA adapter, 4xH100 throughput, failed at +40m with 0/1 replicas.

## Commands used (reproducible)

```bash
K=$(grep CRUSOE_API_KEY .env | cut -d= -f2- | tr -d "'\"")
D=https://api.crusoecloud.com/v1/projects/625de128-87a0-423c-b42f-5b00c034e32d/foundry/selfserve
curl -s -A curl/8.7.1 -H "Authorization: Bearer $K" $D/deployments
curl -s -A curl/8.7.1 -H "Authorization: Bearer $K" $D/deployments/nvidia-nemotron-3-5-lightning-fc72a4f4/activity
curl -s -A curl/8.7.1 -H "Authorization: Bearer $K" $D/flavors
curl -s -H "Authorization: Bearer $K" https://api.intelligence.crusoecloud.com/v1/fine_tuning/jobs/ftjob-0330cd18758a46da997c2a530677360a/events
```

Dead ends: `/v1/deployments`, `/v1/self-serve/deployments`, `/v1/endpoints`, `/v2/...` on
both OpenAI-compatible hosts are 404. `/openapi.json` is Cloudflare-403 even with auth;
`/redoc` on the intelligence host renders but points at the blocked spec.
