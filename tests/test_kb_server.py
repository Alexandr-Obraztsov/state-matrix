"""Страница базы знаний: данные сливаются и отдаются, страница на месте."""
import json, os, sys, tempfile, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer

R = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(R, "scripts"))
import kb_server, store


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".states"))
        store.save(os.path.join(self.d, ".states", "knowledge.json"), [
            {"kind": "строка", "aka": [], "cases": [{"case": "вставка из Word", "why": "разметка"}]},
            {"kind": "промокод", "aka": ["купон"], "cases": [{"case": "уже использован", "why": "другой текст"}]},
        ])
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), kb_server.handler_for(self.d))
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()

    def get(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as r:
            return r.status, r.read().decode()

    def test_api_merges_base_and_project(self):
        status, body = self.get("/api/knowledge")
        d = json.loads(body)
        self.assertEqual(status, 200)
        kinds = {k["kind"]: k for k in d["kinds"]}
        self.assertIn("строка", kinds)
        own = [c for c in kinds["строка"]["cases"] if c.get("own")]
        self.assertEqual([c["case"] for c in own], ["вставка из Word"])
        self.assertTrue(kinds["промокод"]["own"], "свой вид помечен")

    def test_api_ships_sources_and_trace(self):
        d = json.loads(self.get("/api/knowledge")[1])
        self.assertGreaterEqual(len(d["sources"]), 8)
        self.assertEqual(d["trace"]["example"]["endpoint"], "POST /orders")

    def test_every_kind_has_description(self):
        d = json.loads(self.get("/api/knowledge")[1])
        for k in d["kinds"]:
            if not k.get("own"):
                self.assertTrue(k.get("desc"), f"{k['kind']}: нет описания")

    def test_page_served(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("База знаний", body)
        self.assertIn("/api/knowledge", body)

    def test_unknown_path_404(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.get("/nope")
        self.assertEqual(e.exception.code, 404)
