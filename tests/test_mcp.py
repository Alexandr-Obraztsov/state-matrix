import json, os, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(__file__), "..")
SRV = os.path.join(R, "scripts", "mcp_server.py")


def talk(messages):
    """Прогоняет список JSON-RPC сообщений через сервер, возвращает ответы."""
    inp = "\n".join(json.dumps(m, ensure_ascii=False) for m in messages) + "\n"
    r = subprocess.run([sys.executable, SRV], input=inp, capture_output=True, text=True)
    out = []
    for line in r.stdout.splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out, r.stderr


def call(name, args, _id=2):
    return {"jsonrpc": "2.0", "id": _id, "method": "tools/call",
            "params": {"name": name, "arguments": args}}


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}


class T(unittest.TestCase):
    def test_initialize(self):
        out, _ = talk([INIT])
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "state-matrix")
        self.assertIn("tools", out[0]["result"]["capabilities"])

    def test_tools_list_has_schemas(self):
        out, _ = talk([INIT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}])
        tools = out[1]["result"]["tools"]
        self.assertGreaterEqual(len(tools), 15)
        names = {t["name"] for t in tools}
        for n in ("sm_init", "sm_catalog", "sm_param_add", "sm_rule_add",
                  "sm_state_add", "sm_build"):
            self.assertIn(n, names)
        for t in tools:
            self.assertIn("inputSchema", t)
            self.assertTrue(t["description"])
            self.assertNotIn("_fn", t, "внутренние поля не должны уезжать клиенту")

    def test_param_without_catalog_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "X.states.json")
            out, _ = talk([INIT,
                           call("sm_init", {"model": m, "system": "X",
                                            "source": "spec.md"}, 2),
                           call("sm_param_add", {"model": m, "name": "n", "type": "number",
                                                 "values": ["a"], "all_values": ["a"],
                                                 "from": "a.ts:1", "answers": []}, 3)])
            res = out[2]["result"]
            self.assertTrue(res["isError"])
            self.assertIn("корзина", res["content"][0]["text"])

    def test_full_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "X.states.json")
            ans = ["unit=копейки"]
            out, err = talk([INIT,
                             call("sm_init", {"model": m, "system": "X",
                                              "source": "spec.md"}, 2),
                             call("sm_catalog_new", {
                                 "model": m, "id": "money", "title": "Сумма",
                                 "desc": "Денежная сумма.", "type": "number",
                                 "names": ["amount"],
                                 "questions": ["unit=в каких единицах?|копейки|рубли"],
                                 "values": ["zero", "typical"]}, 9),
                             call("sm_catalog", {"model": m, "name": "amount",
                                                 "type": "number"}, 3),
                             call("sm_param_add", {"model": m, "name": "amount",
                                                   "type": "number",
                                                   "values": ["zero", "typical"],
                                                   "all_values": ["zero", "typical"],
                                                   "from": "a.ts:1", "answers": ans}, 4),
                             call("sm_show", {"model": m}, 5)])
            for r in out[1:]:
                self.assertFalse(r["result"].get("isError"), r["result"]["content"][0]["text"])
            self.assertIn("amount", out[-1]["result"]["content"][0]["text"])

    def test_unknown_tool_is_error(self):
        out, _ = talk([INIT, call("sm_nope", {}, 2)])
        self.assertTrue(out[1]["result"]["isError"])

    def test_notification_gets_no_response(self):
        out, _ = talk([INIT, {"jsonrpc": "2.0", "method": "notifications/initialized"}])
        self.assertEqual(len(out), 1, "на уведомление отвечать нельзя")

    def test_mcp_json_points_at_server(self):
        c = json.load(open(os.path.join(R, ".mcp.json"), encoding="utf-8"))
        self.assertIn("state-matrix", c)
        self.assertIn("mcp_server.py", " ".join(c["state-matrix"]["args"]))


class StreamPurity(unittest.TestCase):
    """stdout под MCP — это поток JSON-RPC. Любая прямая запись в него ломает сессию."""

    def test_build_does_not_pollute_stdout(self):
        spec = os.path.join(R, "examples", "checkout-spec.md")
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, ".states", "models", "D.states.json")
            os.makedirs(os.path.dirname(m))
            import shutil
            shutil.copy(spec, os.path.join(d, "spec.md"))
            out, err = talk([
                INIT,
                call("sm_init", {"model": m, "system": "D", "source": "spec.md"}, 2),
                call("sm_catalog_new", {
                    "model": m, "id": "money", "title": "Сумма", "desc": "Сумма.",
                    "type": "number", "names": ["amount"],
                    "questions": ["unit=в каких единицах?|копейки"],
                    "values": ["zero", "typical"]}, 7),
                call("sm_catalog", {"model": m, "name": "amount", "type": "number"}, 3),
                call("sm_param_add", {"model": m, "name": "amount", "type": "number",
                                      "values": ["zero", "typical"],
                                      "all_values": ["zero", "typical"],
                                      "from": os.path.join(d, "spec.md") + ":§3",
                                      "answers": ["unit=копейки"]}, 4),
                call("sm_state_add", {"model": m, "name": "Любое", "when": [],
                                      "evidence": os.path.join(d, "spec.md") + ":§3"}, 5),
                call("sm_build", {"model": m, "root": d}, 6),
            ])
            self.assertEqual(err.strip(), "", "сервер не должен писать в stderr")
            self.assertEqual(len(out), 7, "лишние или потерянные ответы")
            for r in out:
                self.assertIn("result", r)
            last = out[-1]["result"]
            self.assertFalse(last.get("isError"), last["content"][0]["text"])
            self.assertIn("## Матрица", last["content"][0]["text"])
