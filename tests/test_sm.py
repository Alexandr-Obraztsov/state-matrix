import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(ROOT, "scripts", "sm.py")
CAT = json.load(open(os.path.join(ROOT, "catalog", "default.json"), encoding="utf-8"))


def run(*a, expect=0):
    r = subprocess.run([sys.executable, SM, *a], capture_output=True, text=True)
    assert r.returncode == expect, f"код {r.returncode}, ждали {expect}\n{r.stdout}{r.stderr}"
    return r.stdout + r.stderr


def answers_for(cid):
    e = next(c for c in CAT if c["id"] == cid)
    out = []
    for q in e["questions"]:
        out += ["-a", f"{q['id']}=неизвестно"]
    return out


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.m = os.path.join(self.d, "X.states.json")
        run("init", self.m, "--system", "X", "--source", "spec.md")

    def test_init_creates_model(self):
        self.assertEqual(json.load(open(self.m))["system"], "X")

    def test_param_without_catalog_refused(self):
        out = run("param", "add", self.m, "--name", "n", "--type", "number",
                  "--values", "a", "--from", "a.ts:1", expect=2)
        self.assertIn("корзина", out)

    def test_param_without_answers_refused(self):
        run("catalog", self.m, "amount", "--type", "number")
        out = run("param", "add", self.m, "--name", "amount", "--type", "number",
                  "--values", "zero", "--from", "a.ts:1", expect=2)
        self.assertIn("нет ответов", out)

    def test_param_without_from_refused(self):
        run("catalog", self.m, "amount", "--type", "number")
        out = run("param", "add", self.m, "--name", "amount", "--type", "number",
                  "--values", "zero", "--all-values", "zero",
                  *answers_for("money_amount"), expect=2)
        self.assertIn("--from", out)

    def test_param_added_with_answers(self):
        run("catalog", self.m, "amount", "--type", "number")
        run("param", "add", self.m, "--name", "amount", "--type", "number",
            "--values", "zero", "typical", "--all-values", "zero", "typical",
            "--from", "a.ts:1", *answers_for("money_amount"))
        p = json.load(open(self.m))["params"]["amount"]
        self.assertEqual(len(p["answers"]),
                         len(next(c for c in CAT if c["id"] == "money_amount")["questions"]))
        self.assertEqual(p["catalog"], "money_amount")

    def _amount(self):
        run("catalog", self.m, "amount", "--type", "number")
        run("param", "add", self.m, "--name", "amount", "--type", "number",
            "--values", "zero", "typical", "--all-values", "zero", "typical",
            "--from", "a.ts:1", *answers_for("money_amount"))

    def test_rule_without_ref_needs_ask(self):
        self._amount()
        out = run("rule", "add", self.m, "--id", "r1", "--forbid", "amount=zero",
                  "--evidence", "просто так", expect=2)
        self.assertIn("--ask", out)

    def test_rule_with_ref_is_proven(self):
        self._amount()
        run("rule", "add", self.m, "--id", "r1", "--forbid", "amount=zero",
            "--evidence", "a.ts:12 — ноль невозможен")
        self.assertEqual(json.load(open(self.m))["constraints"][0]["status"], "proven")

    def test_rule_unknown_value_refused(self):
        self._amount()
        out = run("rule", "add", self.m, "--id", "r1", "--forbid", "amount=миллион",
                  "--evidence", "a.ts:12", expect=2)
        self.assertIn("отсутствует", out)

    def test_state_without_evidence_refused(self):
        out = run("state", "add", self.m, "--name", "S", expect=2)
        self.assertIn("evidence", out)

    def test_show_prints_human_text(self):
        self._amount()
        out = run("show", self.m)
        self.assertIn("amount", out)
        self.assertIn("zero", out)

    def test_param_rm(self):
        self._amount()
        run("param", "rm", self.m, "amount")
        self.assertNotIn("amount", json.load(open(self.m)).get("params", {}))

    def test_answer_writes_file(self):
        run("answer", self.m, "c1", "proven")
        ans = json.load(open(os.path.join(self.d, "answers.json")))
        self.assertEqual(ans["constraints"]["c1"], "proven")

    def test_transition_add(self):
        self._amount()
        run("transition", "add", self.m, "--event", "pay", "--set", "amount=typical",
            "--evidence", "a.ts:30")
        self.assertEqual(json.load(open(self.m))["transitions"][0]["event"], "pay")

    def test_catalog_list(self):
        out = run("catalog-list")
        self.assertIn("money_amount", out)
        self.assertIn("http_endpoint", out)
