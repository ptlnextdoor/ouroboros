"""Crusoe Managed Inference client with cost tracking + per-run budget cap.

OpenAI-compatible. Every call is priced from `usage` and appended to
runs/<run>/calls.jsonl. Past a per-run cap we raise BudgetExceeded so the loop
stops rather than silently burning credits.

Design notes:
- The system prompt + playbook are passed as a stable prefix so the backend can
  cache them (we read usage.prompt_tokens_details.cached_tokens to price those
  at the cached rate).
- Nemotron models need enable_thinking=False or they return empty content and
  take ~60 s. We always pass that extra_body for nvidia/* models.
- We never print the API key.
"""
import json
import os
import random
import threading
import time
from dataclasses import dataclass, field

from openai import OpenAI

# ---- model catalogue -------------------------------------------------------
# Verified working IDs (see docs). Prices are $/1M tokens: (in, out, cached_in).
MODELS = {
    "spec":     "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
    "designer": "nvidia/Nemotron-3.5-Lightning-30B-A3B",
    "critic":   "deepseek-ai/DeepSeek-V4-Pro",
    "editor":   "deepseek-ai/DeepSeek-V4-Pro",
    "cheap":    "openai/gpt-oss-120b",
}
PRICES = {  # $/1M tokens: input, output, cached_input
    "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B": (0.30, 2.40, 0.15),
    "nvidia/Nemotron-3.5-Lightning-30B-A3B":    (0.05, 0.20, 0.03),
    "deepseek-ai/DeepSeek-V4-Pro":              (1.74, 3.48, 0.15),
    "openai/gpt-oss-120b":                      (0.05, 0.20, 0.05),
}
NVIDIA_EXTRA = {"chat_template_kwargs": {"enable_thinking": False, "force_nonempty_content": True}}
DEFAULT_RUN_CAP_USD = float(os.environ.get("FORGE_BUDGET_USD", "3.0"))


class BudgetExceeded(RuntimeError):
    pass


def _load_env():
    """Load .env without python-dotenv as a fallback (manual parse)."""
    key = os.environ.get("CRUSOE_API_KEY")
    base = os.environ.get("CRUSOE_BASE_URL")
    if key and base:
        return key, base
    try:
        from dotenv import load_dotenv  # type: ignore
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(root, ".env"))
        key = os.environ.get("CRUSOE_API_KEY")
        base = os.environ.get("CRUSOE_BASE_URL")
    except Exception:
        pass
    if not (key and base):  # manual parse
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, ".env")
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
            key = os.environ.get("CRUSOE_API_KEY")
            base = os.environ.get("CRUSOE_BASE_URL")
    base = base or "https://api.inference.crusoecloud.com/v1"
    return key, base


def price_call(model, usage):
    """Return USD cost for one call given an OpenAI usage object/dict."""
    pin, pout, pcached = PRICES.get(model, (0.0, 0.0, 0.0))
    u = usage if isinstance(usage, dict) else usage.model_dump()
    prompt = u.get("prompt_tokens", 0) or 0
    completion = u.get("completion_tokens", 0) or 0
    details = u.get("prompt_tokens_details") or {}
    cached = (details.get("cached_tokens", 0) if isinstance(details, dict) else 0) or 0
    fresh = max(prompt - cached, 0)
    return (fresh * pin + cached * pcached + completion * pout) / 1_000_000.0


@dataclass
class LLM:
    """Shared client. One per run so cost + logging accumulate together."""
    run_dir: str = "runs/_adhoc"
    budget_usd: float = DEFAULT_RUN_CAP_USD
    spent: float = 0.0
    calls: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _client: OpenAI = field(default=None, repr=False)

    def __post_init__(self):
        key, base = _load_env()
        if not key:
            raise RuntimeError("CRUSOE_API_KEY missing (checked env and .env)")
        self._client = OpenAI(api_key=key, base_url=base)
        os.makedirs(self.run_dir, exist_ok=True)
        self._calls_path = os.path.join(self.run_dir, "calls.jsonl")

    # -- cost accounting ----------------------------------------------------
    def _log(self, rec):
        with self._lock:
            with open(self._calls_path, "a") as f:
                f.write(json.dumps(rec) + "\n")

    def _charge(self, model, role, usage, seconds, meta):
        cost = price_call(model, usage)
        u = usage if isinstance(usage, dict) else usage.model_dump()
        with self._lock:
            self.spent += cost
            self.calls += 1
            spent = self.spent
        self._log(dict(ts=time.time(), role=role, model=model, cost_usd=round(cost, 6),
                       spent_usd=round(spent, 6), seconds=round(seconds, 2),
                       prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                       cached_tokens=((u.get("prompt_tokens_details") or {}) or {}).get("cached_tokens", 0),
                       **(meta or {})))
        if spent > self.budget_usd:
            raise BudgetExceeded(f"run budget ${self.budget_usd:.2f} exceeded (spent ${spent:.4f})")

    # -- chat ---------------------------------------------------------------
    def chat(self, role, messages, *, temperature=1.0, top_p=0.95, max_tokens=1024,
             seed=None, model=None, meta=None, retries=5):
        """One chat completion. `role` selects a model and prices it.

        messages[0] should be the stable system+playbook prefix for cache hits.
        """
        model = model or MODELS[role]
        extra_body = {}
        if model.startswith("nvidia/"):
            extra_body = dict(NVIDIA_EXTRA)
        kwargs = dict(model=model, messages=messages, temperature=temperature,
                      top_p=top_p, max_tokens=max_tokens)
        if seed is not None:
            kwargs["seed"] = seed
        if extra_body:
            kwargs["extra_body"] = extra_body
        last = None
        for attempt in range(retries):
            # pre-check budget so we never start a call we can't afford to log
            if self.spent > self.budget_usd:
                raise BudgetExceeded(f"run budget ${self.budget_usd:.2f} exceeded before call")
            t0 = time.time()
            try:
                resp = self._client.chat.completions.create(**kwargs)
                dt = time.time() - t0
                content = resp.choices[0].message.content or ""
                self._charge(model, role, resp.usage, dt, meta)
                return content
            except BudgetExceeded:
                raise
            except Exception as e:  # 429 / transient: exponential backoff + jitter
                last = e
                msg = str(e)
                transient = any(s in msg for s in ("429", "rate", "Rate", "timeout", "Timeout",
                                                   "502", "503", "504", "overloaded", "Connection"))
                if attempt == retries - 1 or not transient:
                    if not transient:
                        raise
                    break
                sleep = min(30.0, (2 ** attempt) * 1.0) + random.uniform(0, 1.0)
                time.sleep(sleep)
        raise RuntimeError(f"LLM call failed after {retries} tries: {last}")

    def chat_json(self, role, messages, *, extract=True, **kw):
        """Chat and parse a JSON object out of the reply (tolerant of fences)."""
        txt = self.chat(role, messages, **kw)
        return (parse_json(txt) if extract else txt), txt


def parse_json(text):
    """Pull the first JSON object/array out of an LLM reply. Returns None on fail."""
    if not text:
        return None
    t = text.strip()
    # strip code fences
    if "```" in t:
        import re
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", t, re.S)
        for b in blocks:
            got = _try_load(b)
            if got is not None:
                return got
    got = _try_load(t)
    if got is not None:
        return got
    # bracket scan
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i = t.find(open_c)
        if i < 0:
            continue
        depth = 0
        for j in range(i, len(t)):
            if t[j] == open_c:
                depth += 1
            elif t[j] == close_c:
                depth -= 1
                if depth == 0:
                    got = _try_load(t[i:j + 1])
                    if got is not None:
                        return got
                    break
    return None


def _try_load(s):
    try:
        return json.loads(s.strip())
    except Exception:
        return None


def dry_run():
    """Cheap connectivity + pricing check. One tiny call on the cheapest model."""
    llm = LLM(run_dir="runs/_dryrun", budget_usd=0.5)
    out = llm.chat("cheap", [
        {"role": "system", "content": "Reply with exactly: ok"},
        {"role": "user", "content": "say ok"},
    ], max_tokens=8, temperature=0.0)
    print(f"llm dry-run ok: reply={out!r} spent=${llm.spent:.6f} calls={llm.calls}")
    return out


if __name__ == "__main__":
    import sys
    if "--dry-run" in sys.argv or "--selftest" in sys.argv:
        # offline price-math check first (no network)
        c = price_call("nvidia/Nemotron-3.5-Lightning-30B-A3B",
                       {"prompt_tokens": 1000, "completion_tokens": 500,
                        "prompt_tokens_details": {"cached_tokens": 200}})
        exp = (800 * 0.05 + 200 * 0.03 + 500 * 0.20) / 1e6
        assert abs(c - exp) < 1e-12, (c, exp)
        print(f"price math ok: ${c:.8f}")
        if "--dry-run" in sys.argv:
            dry_run()
