#!/usr/bin/env python3
"""FORGE live demo server. stdlib only.

    python3 ui/serve.py [--port 8008] [--run runs/<run>]

Serves ui/index.html, static files from the repo root (runs/, playbook/, ui/fixture/),
and two JSON endpoints:
    /events?run=<dir>   SSE stream: replays the existing events.jsonl, then tails it live.
                        Without ?run, picks the newest runs/*/events.jsonl (falls back to the fixture).
    /runs               JSON list of run dirs that have an events.jsonl, newest first.
"""
import argparse, glob, json, os, sys, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, "ui")
FIXTURE = "ui/fixture/demo"
FORCED_RUN = None


def run_dirs():
    paths = glob.glob(os.path.join(ROOT, "runs", "**", "events.jsonl"), recursive=True)
    paths.sort(key=os.path.getmtime, reverse=True)
    return [os.path.relpath(os.path.dirname(p), ROOT) for p in paths]


def newest_run():
    if FORCED_RUN:
        return FORCED_RUN
    r = run_dirs()
    return r[0] if r else FIXTURE


def safe_rel(rel):
    """Resolve a repo-relative dir, refusing escapes."""
    full = os.path.realpath(os.path.join(ROOT, rel or ""))
    if not full.startswith(os.path.realpath(ROOT)):
        return None
    return full


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):  # quieter: skip SSE keepalive noise
        if "/events" not in (args[0] if args else ""):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self.path = "/ui/index.html"
            return super().do_GET()
        if u.path == "/runs":
            return self.json(dict(runs=run_dirs(), newest=newest_run(), fixture=FIXTURE))
        if u.path == "/events":
            q = parse_qs(u.query)
            run = q.get("run", [None])[0]
            return self.sse(run or newest_run(), live="replay" not in q, explicit=bool(run))
        return super().do_GET()

    def json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def sse(self, run, live=True, explicit=False):
        d = safe_rel(run)
        if not d:
            self.send_error(400, "bad run")
            return
        path = os.path.join(d, "events.jsonl")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        def send(ev, data):
            self.wfile.write(f"event: {ev}\ndata: {data}\n\n".encode())
            self.wfile.flush()

        send("meta", json.dumps(dict(run=os.path.relpath(d, ROOT), live=live)))
        pos = 0
        buf = b""
        idle = 0
        try:
            while True:
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        f.seek(pos)
                        chunk = f.read()
                    if chunk:
                        pos += len(chunk)
                        buf += chunk
                        *lines, buf = buf.split(b"\n")
                        for ln in lines:
                            ln = ln.strip()
                            if ln:
                                send("ev", ln.decode("utf-8", "replace"))
                        idle = 0
                        continue
                if not live:
                    send("done", "{}")
                    return
                time.sleep(0.25)
                idle += 1
                if idle % 60 == 0:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                # a newer run appeared: tell the client to reconnect (it will pick the newest)
                if FORCED_RUN is None and not explicit and run != newest_run():
                    send("switch", json.dumps(dict(run=newest_run())))
                    return
        except (BrokenPipeError, ConnectionResetError):
            return


def main():
    global FORCED_RUN
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8008)
    ap.add_argument("--run", help="repo-relative run dir to tail (default: newest runs/*)")
    a = ap.parse_args()
    FORCED_RUN = a.run
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print(f"FORGE UI  http://localhost:{a.port}/   tailing {newest_run()}")
    print(f"replay:   http://localhost:{a.port}/?replay={FIXTURE}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
