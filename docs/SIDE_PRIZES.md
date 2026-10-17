# Side prizes: OpenShell sandbox + Nemotron on Crusoe

Researched 2026-10-17 10:45 PT from the OpenShell README/docs (v0.1.4) and the Crusoe hackathon skill file (refreshed Oct 13). Both sources say "verify"; items marked VERIFY were not run locally.

## 1. Best Use of NemoClaw & OpenShell

### Local status (this laptop, Apple Silicon, macOS 27)

| Check | Result |
|---|---|
| `which openshell` | not installed |
| `which podman` | not installed |
| `which docker` | `/usr/local/bin/docker` 29.8.2, context `orbstack`, daemon reachable, 0 running containers |
| `/var/run/docker.sock` | symlink to `~/.orbstack/run/docker.sock` (installer waits on exactly this path, good) |
| Docker VM kernel | `7.2.9-orbstack` (OpenShell needs Landlock ABI 3, Linux 6.2+, so OK) |
| Homebrew | `/opt/homebrew/bin/brew` (required: macOS install is a brew formula + `brew services` gateway) |
| License | Apache 2.0. No key, no account. Telemetry on by default, disable with `OPENSHELL_TELEMETRY_ENABLED=false` on the gateway |

**Blockers / risks**

1. Support matrix lists **macOS (Docker Desktop)** only. OrbStack is unlisted. Installer only needs a reachable `/var/run/docker.sock` and Docker >= 28, which OrbStack satisfies, but the Docker driver requires **host networking enabled** on the daemon so sandboxes reach the gateway on loopback. OrbStack supports host networking, Docker Desktop needs it toggled on. If sandbox creation hangs on "connecting to gateway", set `grpc_endpoint` in `~/.config/openshell/gateway.toml` under `[openshell.drivers.docker]`. Fallback: VM driver (Hypervisor.framework, opt-in in gateway.toml, no Docker needed).
2. Install is not fully user-space: it creates a local brew tap `nvidia/openshell`, installs formula `openshell`, and starts a `brew services` gateway on `https://localhost:17670`. Reversible: `brew services stop nvidia/openshell/openshell && brew uninstall nvidia/openshell/openshell && rm -rf "$(brew --prefix)/var/openshell"`.
3. Filesystem policy is **allow-list only** (`read_only` / `read_write`). There is no `deny` key. "Deny `./referee/hidden`" = do not list it, and do not list its parent. Landlock blocks everything unlisted. If `hidden/` lives under the workdir, it must be excluded at upload time (never copied into the sandbox) because any `read_write` grant on the parent would cover it.
4. Sandbox FS is a copy, not a bind mount. Files go in via `--upload` / `openshell sandbox upload`, come out via `openshell sandbox download`. Bind mounts exist but are explicitly documented as bypassing filesystem policy (don't use for the demo).
5. Network binary matching uses the **real path** of the executable. On the default image (Ubuntu 24.04) `python3` -> `/usr/bin/python3.12`. Confirm inside sandbox with `readlink -f /usr/bin/python3`.
6. Default image `nvcr.io/nvidia/base/ubuntu:24.04` has python3 but **no CadQuery**. Build our own image (`docker build -t cq-sandbox .`, `--from cq-sandbox:latest`). Docker driver accepts local image tags.

### Install (one command, ~2 min, needs Docker running)

```bash
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh
openshell gateway list          # expect a local gateway at https://localhost:17670
openshell sandbox create --name smoke --no-keep -- sh -c 'echo ok'   # smoke test
```

Agent skills for the CLI (optional, user-space): `npx skills add NVIDIA/OpenShell`.

### Policy file: `openshell/part-runner.yaml`

Allows RW on `/sandbox/work`, never mentions `referee/hidden` (so Landlock denies it), egress only `api.inference.crusoecloud.com:443` from the Python interpreter.

```yaml
version: 1

filesystem_policy:
  include_workdir: false          # explicit: do NOT grant the whole workspace
  read_only: [/usr, /lib, /etc]   # baseline; /proc, /dev/urandom etc. added automatically
  read_write: [/sandbox/work, /tmp]
  # /sandbox/referee/hidden is intentionally absent -> Landlock denies it

landlock:
  compatibility: hard_requirement  # fail to start rather than run without FS rules

process:
  run_as_user: sandbox
  run_as_group: sandbox

network_policies:
  crusoe_inference:
    endpoints:
      - host: api.inference.crusoecloud.com
        port: 443
        protocol: rest
        enforcement: enforce
        rules:
          - allow:
              method: POST
              path: /v1/chat/completions
          - allow:
              method: GET
              path: /v1/models
    binaries:
      - path: /usr/bin/python3.12   # real path; `readlink -f /usr/bin/python3` in the image
```

Everything else (pypi, github, DNS to anything) is denied. If the demo needs `pip install` inside, add a second rule for `pypi.org` + `files.pythonhosted.org` (read-only) or bake deps into the image.

### Run `python3 work/part.py` inside it

```bash
# 1. image with CadQuery (one-time)
cat > openshell/Dockerfile <<'EOF'
FROM nvcr.io/nvidia/base/ubuntu:24.04
RUN apt-get update && apt-get install -y python3 python3-pip && pip3 install --break-system-packages cadquery
WORKDIR /sandbox
EOF
docker build -t cq-sandbox:latest openshell/

# 2. create sandbox (uploads cannot be combined with a trailing command, so create detached, then exec)
openshell sandbox create --name part-runner --detach \
  --from cq-sandbox:latest \
  --policy openshell/part-runner.yaml \
  --upload ./work:/sandbox/work \
  --env CRUSOE_API_KEY="$CRUSOE_API_KEY"      # or attach via a provider so the agent never sees the key

# 3. run the part script
openshell sandbox exec -n part-runner -- python3 /sandbox/work/part.py

# 4. pull results back
openshell sandbox download part-runner work ./work-out

# proof shots for judges
openshell sandbox exec -n part-runner -- ls /sandbox/referee/hidden   # Permission denied (Landlock)
openshell sandbox exec -n part-runner -- python3 -c "import urllib.request;urllib.request.urlopen('https://pypi.org')"  # blocked
openshell policy get part-runner --full
openshell sandbox logs part-runner    # shows denied connections + Landlock ruleset event

openshell sandbox delete part-runner
```

Prize angle: the **referee runs in its own sandbox** with `read_only: [/sandbox/referee]` and **no network rule at all**, so the agent sandbox cannot reach hidden load cases and the referee cannot leak them. Two policies, two sandboxes, one gateway. "NemoClaw" is the NVIDIA agent runtime name used in the prize title; OpenShell is the sandbox layer it ships on, so a bare OpenShell policy demo qualifies.

## 2. Nemotron on Crusoe Managed Inference

Endpoint: `https://api.inference.crusoecloud.com/v1` (OpenAI-compatible). Old hostnames `api.crusoe.ai` / `managed-inference-api-proxy.crusoecloud.com` return 429/404, do not use.

Key gotcha: keys contain `$`. Export with **single quotes**: `export CRUSOE_API_KEY='...'`.

### Model IDs (case-sensitive; both "from docs table, confirm" in the skill file)

| ID | Ctx | $/1M in / out / cached | Use |
|---|---|---|---|
| `nvidia/Nemotron-3-Super-120B-A12B` | 262,144 | 0.30 / 2.40 / 0.15 | planner, tool use, hard CadQuery steps |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | 1,048,576 | 0.05 / 0.20 / 0.03 | sub-agent workhorse, long loops |

Confirm before demo (wrong case = `404 model_not_found`):

```bash
curl -s https://api.inference.crusoecloud.com/v1/models -H "Authorization: Bearer $CRUSOE_API_KEY" \
  | jq -r '.data[] | select(.id|test("emotron")) | "\(.id)\t\(.context_length)\t\(.supported_parameters)"'
```

### Request params

- Sampling (both cards): `temperature=1.0`, `top_p=0.95`.
- Thinking toggle: `extra_body={"chat_template_kwargs": {"enable_thinking": true|false}}`. Lightning thinks **by default**; set `false` for cheap direct answers. Super also has `low_effort` (fewer reasoning tokens). Do NOT send DeepSeek-style top-level `"thinking": {...}`, proxy returns 403 `parameter 'thinking' is not allowed`. `reasoning_effort` alone does not turn thinking on.
- Coding agents: `chat_template_kwargs: {"force_nonempty_content": true}` (both cards) so `content` is never empty when the model only emits a tool call / reasoning.
- `max_tokens`: reasoning tokens count against it. Below a few hundred, `content` comes back `None` with `finish_reason == "length"`. Use >= 1024 (2048+ for code generation with thinking on). Reasoning returns in `message.reasoning_content` or `message.reasoning`; read via `message.model_dump()`.
- Tool calling: standard `tools` / `tool_calls`; append the assistant `tool_calls` message **before** the `role: tool` replies or you get a 400.
- 429: per-project, per-model, per-minute. No payment method = **30 RPM / 500K TPM per model**; card on file = 600 RPM / 2M TPM. Spread roles across both models to double headroom. 503 = shared endpoint busy, same retry. Headers: `x-ratelimit-remaining-requests`, `x-ratelimit-remaining-tokens`.

### Prefix caching + cost meter

- Keep system prompt + tool schema + history **byte-identical** (whitespace, tool order, JSON key order). Append only; editing an earlier message invalidates from that point. Put the changing part (new load case, new error) last.
- Turn 1 is always cold. Short prompts can report 0 even when identical (segment granularity). Measure with your real prompt.
- Meter: `usage.prompt_tokens_details.cached_tokens`. Cost = `(prompt - cached) * in + cached * cached_rate + completion * out`. Session hit rate = `sum(cached) / sum(prompt)`.
- Dashboard: https://console.crusoecloud.com/foundry/metrics (PromQL `inference_counter_cached_prompt_token / inference_counter_prompt_token`).

### Minimal client (retry/backoff + meter)

```python
import os, random, time
from openai import OpenAI, RateLimitError, InternalServerError, APIConnectionError

BASE = "https://api.inference.crusoecloud.com/v1"
SUPER = "nvidia/Nemotron-3-Super-120B-A12B"
LIGHT = "nvidia/nemotron-3.5-lightning-30b-a3b"
PRICE = {  # $/1M: input, output, cached
    SUPER: (0.30, 2.40, 0.15),
    LIGHT: (0.05, 0.20, 0.03),
}
client = OpenAI(base_url=BASE, api_key=os.environ["CRUSOE_API_KEY"])
spent = {"usd": 0.0, "prompt": 0, "cached": 0, "completion": 0}


def chat(messages, model=LIGHT, think=False, tools=None, max_tokens=2048, max_tries=6):
    for attempt in range(max_tries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                temperature=1.0,
                top_p=0.95,
                max_tokens=max_tokens,
                extra_body={"chat_template_kwargs": {
                    "enable_thinking": think,
                    "force_nonempty_content": True,
                }},
            )
            break
        except (RateLimitError, InternalServerError, APIConnectionError):  # 429 / 503 / net
            if attempt == max_tries - 1:
                raise
            time.sleep(min(60, 2 ** attempt) + random.uniform(0, 0.5))

    u = resp.usage
    cached = (u.prompt_tokens_details.cached_tokens or 0) if u.prompt_tokens_details else 0
    pin, pout, pcache = PRICE[model]
    spent["usd"] += ((u.prompt_tokens - cached) * pin + cached * pcache + u.completion_tokens * pout) / 1e6
    spent["prompt"] += u.prompt_tokens
    spent["cached"] += cached
    spent["completion"] += u.completion_tokens

    msg = resp.choices[0].message
    if resp.choices[0].finish_reason == "length" and not msg.content:
        raise RuntimeError("starved: raise max_tokens (reasoning ate the budget)")
    return msg  # msg.content, msg.tool_calls, msg.model_dump().get("reasoning_content")


if __name__ == "__main__":
    m = chat([{"role": "user", "content": "Reply with the single word: ok"}])
    print(m.content, spent)
```

Hit rate printout: `spent["cached"] / spent["prompt"]`; expect 0 on turn 1, rising after.

### Prize angle

Use Lightning (1M ctx, $0.05) for every sub-agent iteration and Super for the planner / repair step. Log `cached_tokens` per turn and show the cost meter live. Both are "built for long-running agents" per NVIDIA's cards, which matches the hackathon theme.
