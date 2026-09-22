#!/usr/bin/env python3
"""Локальный сервер отчёта: раздаёт report.html + result.json, живая перерисовка по SSE,
принимает ответы человека в .states/answers.yaml."""
import os, sys, json, time, threading, argparse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENTS, LOCK = [], threading.Lock()


def watch(path):
    last = None
    while True:
        try:
            m = os.path.getmtime(path)
        except OSError:
            m = None
        if m != last:
            last = m
            with LOCK:
                dead = []
                for c in CLIENTS:
                    try:
                        c.wfile.write(b"data: reload\n\n")
                        c.wfile.flush()
                    except Exception:
                        dead.append(c)
                for d in dead:
                    CLIENTS.remove(d)
        time.sleep(0.4)


class H(SimpleHTTPRequestHandler):
    serve_dir = "."
    data_file = ""
    answers_file = ""

    def translate_path(self, path):
        path = path.split("?", 1)[0].split("#", 1)[0]
        if path in ("/", "/index.html"):
            return os.path.join(ROOT, "report", "report.html")
        if path == "/result.json":
            return self.data_file
        return os.path.join(ROOT, "report", path.lstrip("/"))

    def do_GET(self):
        if self.path.startswith("/events"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with LOCK:
                CLIENTS.append(self)
            try:
                while True:
                    time.sleep(10)
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except Exception:
                pass
            return
        self.send_header_nocache = True
        return SimpleHTTPRequestHandler.do_GET(self)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        SimpleHTTPRequestHandler.end_headers(self)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        import yaml
        cur = {}
        if os.path.exists(self.answers_file):
            cur = yaml.safe_load(open(self.answers_file)) or {}
        cur.setdefault("constraints", {})
        cur.setdefault("outcomes", {})
        sect, k, v = body.get("section", "constraints"), body.get("id"), body.get("value")
        cur.setdefault(sect, {})[k] = v
        os.makedirs(os.path.dirname(self.answers_file), exist_ok=True)
        yaml.safe_dump(cur, open(self.answers_file, "w"), allow_unicode=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "saved": {sect: {k: v}}}).encode())

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=os.path.join(ROOT, ".states/runs/checkout-widget.json"))
    ap.add_argument("--answers", default=os.path.join(ROOT, ".states/answers.yaml"))
    ap.add_argument("--port", type=int, default=4177)
    a = ap.parse_args()
    H.data_file, H.answers_file = a.data, a.answers
    threading.Thread(target=watch, args=(a.data,), daemon=True).start()
    print(f"state-matrix report: http://localhost:{a.port}  ← {a.data}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
