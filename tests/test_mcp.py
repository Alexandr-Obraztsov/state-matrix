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
                                            "source": "a.ts", "mode": "code"}, 2),
                           call("sm_param_add", {"model": m, "name": "n", "type": "number",
                                                 "values": ["a"], "from": "a.ts:1",
                                                 "answers": []}, 3)])
            res = out[2]["result"]
            self.assertTrue(res["isError"])
            self.assertIn("корзина", res["content"][0]["text"])

    def test_full_happy_path(self):
        with tempfile.TemporaryDirectory() as d:
            m = os.path.join(d, "X.states.json")
            cat = json.load(open(os.path.join(R, "catalog", "default.json"),
                                 encoding="utf-8"))
            qs = next(c for c in cat if c["id"] == "money_amount")["questions"]
            ans = [f"{q['id']}=неизвестно" for q in qs]
            out, err = talk([INIT,
                             call("sm_init", {"model": m, "system": "X",
                                              "source": "a.ts", "mode": "code"}, 2),
                             call("sm_catalog", {"model": m, "name": "amount",
                                                 "type": "number"}, 3),
                             call("sm_param_add", {"model": m, "name": "amount",
                                                   "type": "number",
                                                   "values": ["zero", "typical"],
                                                   "from": "a.ts:1", "answers": ans}, 4),
                             call("sm_show", {"model": m}, 5)])
            for r in out[1:]:
                self.assertFalse(r["result"].get("isError"), r["result"]["content"][0]["text"])
            self.assertIn("amount", out[4]["result"]["content"][0]["text"])

    def test_extract_tool(self):
        out, _ = talk([INIT, call("sm_extract",
                                  {"target": os.path.join(R, "scripts", "store.py")}, 2)])
        self.assertFalse(out[1]["result"].get("isError"))

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
