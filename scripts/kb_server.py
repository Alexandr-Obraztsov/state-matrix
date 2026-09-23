#!/usr/bin/env python3
"""Страница базы знаний: где искать входы и корнер-кейсы по видам параметров.

Читает базовую базу плагина и проектную из .states/knowledge.json, сливает их
и отдаёт одной страницей. Страница перечитывает данные сама — дописанное через
sm_learn появляется без перезапуска.

  python3 kb_server.py --project . --port 4178
"""
import os, sys, json, argparse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store, sm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "knowledge", "page.html")
SOURCES = os.path.join(ROOT, "knowledge", "sources.json")


def payload(project):
    proj_file = os.path.join(project, ".states", "knowledge.json")
    kinds = sm.merge_knowledge(store.load(sm.BASE_KB) or [], store.load(proj_file) or [])
    src = store.load(SOURCES) or {}
    return {
        "project": os.path.basename(os.path.abspath(project)) or project,
        "project_file": proj_file if os.path.exists(proj_file) else None,
        "sources": src.get("sources", []),
        "trace": src.get("trace"),
        "kinds": list(kinds.values()),
    }


def handler_for(project):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/knowledge":
                body = json.dumps(payload(project), ensure_ascii=False).encode()
                ctype = "application/json; charset=utf-8"
            elif path in ("/", "/index.html"):
                with open(PAGE, "rb") as f:
                    body = f.read()
                ctype = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=".", help="корень проекта, где лежит .states/")
    ap.add_argument("--port", type=int, default=4178)
    a = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), handler_for(a.project))
    print(f"база знаний: http://localhost:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
