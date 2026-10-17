"""Gen-1 adapter tool: inspect, download, and probe the Crusoe LoRA fine-tune.

The Gen-1 fine-tune (forge.distill --launch) produced a LoRA adapter on
Nemotron-3.5-Nano-30B. This tool reads that job's metadata, downloads the
adapter weights, and probes whether the fine-tuned id is servable without a
paid deployment.

Transport note: Crusoe sits behind Cloudflare, which rejects Python's stdlib
urllib user-agent (Error 1010 "browser signature banned"). We therefore go
through the OpenAI SDK for the typed endpoints and its bundled httpx client
for the raw byte endpoints, matching forge.distill's working client.

CLI:
  python -m forge.adapter --info               job + checkpoint metrics + model record
  python -m forge.adapter --download OUT_DIR   pull adapter weights into OUT_DIR
  python -m forge.adapter --infer              try a serverless chat call, report the error

The adapter weights go to gens/gen1/adapter/ (gitignored) by default.
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- Gen-1 fine-tune record (from forge.distill --launch) -------------------
JOB_ID = "ftjob-0330cd18758a46da997c2a530677360a"
MODEL_ID = "ftmodel-503f6289-c017-4e66-8351-ee8919f19c3f"
MODEL_NAME = "ft:nvidia-nemotron-3-5-nano-30b-a3b-bf16-07292026:forge-gen1:5087e8e3"
BASE_MODEL_ID = "ftmodel-6c22bf52-fb65-4bd5-94c4-736f0a7d33f0"

# management / fine-tuning API (job + model records, weights)
FT_BASE = "https://api.intelligence.crusoecloud.com/v1"
# serverless inference API (chat completions)
INFER_BASE = "https://api.inference.crusoecloud.com/v1"

GEN_DIR = os.path.join(ROOT, "gens", "gen1")
DEFAULT_OUT = os.path.join(GEN_DIR, "adapter")


# ---------------------------------------------------------------------------
# env (same contract as forge.distill._load_env: strip surrounding quotes)
# ---------------------------------------------------------------------------
def _load_env():
    key = os.environ.get("CRUSOE_API_KEY")
    if key:
        return key.strip().strip('"').strip("'")
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)
        key = os.environ.get("CRUSOE_API_KEY")
    return (key or "").strip().strip('"').strip("'") or None


def _key():
    k = _load_env()
    if not k:
        raise RuntimeError("CRUSOE_API_KEY missing (checked env and .env)")
    return k


def _client(base=FT_BASE):
    from openai import OpenAI
    return OpenAI(api_key=_key(), base_url=base)


def _httpx(base=FT_BASE):
    """Bundled httpx client with the auth header and a browser-ish UA so
    Cloudflare does not 1010 us the way stdlib urllib gets blocked."""
    import httpx
    return httpx.Client(
        base_url=base,
        headers={
            "Authorization": f"Bearer {_key()}",
            "User-Agent": "forge-adapter/1.0 (+httpx)",
        },
        timeout=120.0,
        follow_redirects=True,
    )


# ---------------------------------------------------------------------------
# --info
# ---------------------------------------------------------------------------
def info():
    client = _client()

    print(f"job id:   {JOB_ID}")
    print(f"model id: {MODEL_ID}")
    print(f"name:     {MODEL_NAME}")
    print(f"base:     {BASE_MODEL_ID}")
    print("=" * 72)

    # 1) job record
    print(f"\n[job]  fine_tuning.jobs.retrieve({JOB_ID})")
    try:
        job = client.fine_tuning.jobs.retrieve(JOB_ID)
        for k in ("status", "fine_tuned_model", "model", "trained_tokens",
                  "created_at", "finished_at", "error"):
            v = getattr(job, k, None)
            if v not in (None, ""):
                print(f"  {k}: {v}")
        hp = getattr(job, "hyperparameters", None) or getattr(job, "method", None)
        if hp:
            print(f"  hyperparameters: {hp}")
    except Exception as e:
        print(f"  error: {e!r}")

    # 2) checkpoint metrics (losses, tokens)
    print(f"\n[checkpoints]  fine_tuning.jobs.checkpoints.list({JOB_ID})")
    try:
        ck = client.fine_tuning.jobs.checkpoints.list(JOB_ID)
        for c in ck.data:
            step = getattr(c, "step_number", None) or getattr(c, "step", "?")
            metrics = getattr(c, "metrics", None)
            cfid = getattr(c, "fine_tuned_model_checkpoint", None) or getattr(c, "id", None)
            print(f"  step {step}: {metrics}")
            if cfid:
                print(f"    checkpoint id: {cfid}")
    except Exception as e:
        print(f"  error: {e!r}")

    # 3) model record
    print(f"\n[model]  models.retrieve({MODEL_ID})")
    try:
        mdl = client.models.retrieve(MODEL_ID).model_dump()
        for k in ("id", "model_name", "model_type", "model_source",
                  "inference_available", "fine_tuning_available",
                  "globally_available", "base_model_id", "owned_by", "created"):
            if k in mdl:
                print(f"  {k}: {mdl[k]}")
    except Exception as e:
        print(f"  error: {e!r}")


# ---------------------------------------------------------------------------
# --download
# ---------------------------------------------------------------------------
def _checkpoint_ids(client):
    ids = []
    try:
        ck = client.fine_tuning.jobs.checkpoints.list(JOB_ID)
        for c in ck.data:
            for attr in ("fine_tuned_model_checkpoint", "id"):
                v = getattr(c, attr, None)
                if v:
                    ids.append(str(v))
    except Exception as e:
        print(f"  (checkpoints.list failed: {e!r})")
    return ids


def _candidates(client):
    """(label, path) download candidates, most-likely first."""
    for cid in _checkpoint_ids(client):
        yield (f"files/{cid}/content", f"/files/{cid}/content")
    yield ("models/{id}/content", f"/models/{MODEL_ID}/content")
    yield ("models/{id}/download", f"/models/{MODEL_ID}/download")
    yield ("files/{model_id}/content", f"/files/{MODEL_ID}/content")


def download(out_dir):
    client = _client()
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    print(f"downloading adapter -> {out_dir}")

    saved = []
    with _httpx() as hx:
        for label, path in _candidates(client):
            try:
                r = hx.get(path)
            except Exception as e:
                print(f"  try {label}  -> error {e!r}")
                continue
            ct = r.headers.get("content-type", "").lower()
            body = r.content
            print(f"  try {label}  -> {r.status_code}  ({ct or 'no content-type'}, {len(body)} B)")
            if r.status_code != 200 or not body:
                if body and "json" in ct:
                    print(f"      {body[:200].decode('utf-8','replace')}")
                continue
            # JSON listing of files -> follow each
            if "json" in ct and body[:1] in (b"{", b"["):
                try:
                    parsed = json.loads(body)
                except Exception:
                    parsed = None
                items = parsed.get("data") if isinstance(parsed, dict) else parsed
                if isinstance(items, list):
                    for it in items:
                        fid = it.get("id") or it.get("file_id")
                        name = it.get("filename") or it.get("name") or fid
                        du = it.get("download_url")
                        try:
                            rr = hx.get(du) if du else hx.get(f"/files/{fid}/content")
                        except Exception:
                            continue
                        if rr.status_code == 200 and rr.content:
                            fp = os.path.join(out_dir, name)
                            open(fp, "wb").write(rr.content)
                            saved.append(fp)
                    if saved:
                        break
                    continue
            # raw bytes are the artifact
            fname = _filename_from(r.headers) or _default_name(ct)
            fp = os.path.join(out_dir, fname)
            open(fp, "wb").write(body)
            saved.append(fp)
            break

    if not saved:
        print("\nno adapter weights downloaded. None of the candidate endpoints "
              "returned bytes. The adapter is an 'evolution' model record whose "
              "weights are not exposed over the public files API; export it from "
              "the Crusoe console, or attach it to a deployment. See docs/evidence/GEN1.md.")
        return

    print("\nsaved files:")
    for fp in saved:
        print(f"  {os.path.relpath(fp, ROOT)}  ({os.path.getsize(fp):,} B)")


def _filename_from(headers):
    cd = headers.get("content-disposition", "")
    if "filename=" in cd:
        return cd.split("filename=")[-1].strip().strip('"') or None
    return None


def _default_name(ct):
    if "zip" in ct:
        return "adapter.zip"
    if "tar" in ct:
        return "adapter.tar"
    if "octet" in ct or "binary" in ct:
        return "adapter.bin"
    return "adapter.safetensors"


# ---------------------------------------------------------------------------
# --infer : probe serverless inference against the fine-tuned id
# ---------------------------------------------------------------------------
def _try_infer(client, model):
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return True, resp.choices[0].message.content
    except Exception as e:
        return False, repr(e)


def infer():
    client = _client(base=INFER_BASE)
    print(f"POST {INFER_BASE}/chat/completions")
    for model in (MODEL_ID, MODEL_NAME):
        ok, out = _try_infer(client, model)
        print(f"\n  model={model}\n  -> {'OK' if ok else 'ERROR'}: {str(out)[:500]}")
    print("\nConclusion: the adapter model record has inference_available=False, so "
          "the shared serverless endpoint will not serve it. Serving needs a "
          "Self-Serve Deployment (one-click in the Crusoe console, ~$22/hr) which "
          "we deliberately did not create.")


def main():
    ap = argparse.ArgumentParser(description="FORGE gen-1 adapter tool")
    ap.add_argument("--info", action="store_true", help="job + checkpoint metrics + model record")
    ap.add_argument("--download", metavar="OUT_DIR", nargs="?", const=DEFAULT_OUT,
                    help=f"download adapter weights (default {os.path.relpath(DEFAULT_OUT, ROOT)})")
    ap.add_argument("--infer", action="store_true", help="probe serverless inference, report error")
    args = ap.parse_args()

    did = False
    if args.info:
        info(); did = True
    if args.download is not None:
        download(args.download); did = True
    if args.infer:
        infer(); did = True
    if not did:
        ap.print_help()


if __name__ == "__main__":
    main()
