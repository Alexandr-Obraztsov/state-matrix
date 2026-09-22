"""Протокол sm.py: порядок этапов и отказы на каждом."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(ROOT, "scripts", "sm.py")


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".states", "models"))
        self.m = os.path.join(self.d, ".states", "models", "X.states.json")
        open(os.path.join(self.d, "spec.md"), "w", encoding="utf-8").write(
            "# Спека\n\n## §1 Корзина\nПусто, загрузка, готово.\n\n## §2 Сумма\nНоль допустим.\n")
        self.sm("init", self.m, "--system", "X",
                "--source", os.path.join(self.d, "spec.md"))

    def sm(self, *a, expect=0):
        r = subprocess.run([sys.executable, SM, *a], capture_output=True, text=True)
        self.assertEqual(r.returncode, expect, f"код {r.returncode}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def model(self):
        with open(self.m, encoding="utf-8") as f:
            return json.load(f)

    def declare(self, name="cart", type_="enum"):
        self.sm("param", "add", self.m, "--name", name, "--type", type_,
                "--desc", "описание", "--from", "spec.md:§1")

    # --- этап 1 ---

    def test_init_creates_model(self):
        self.assertEqual(self.model()["system"], "X")
        self.assertEqual(self.model()["params"], {})

    def test_param_add_requires_desc(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--type", "enum",
                      "--from", "spec.md:§1", expect=2)
        self.assertIn("--desc", out)

    def test_param_add_requires_from(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--type", "enum",
                      "--desc", "описание", expect=2)
        self.assertIn("--from", out)

    def test_param_declared_without_values(self):
        self.declare()
        p = self.model()["params"]["cart"]
        self.assertNotIn("values", p, "значения задаются отдельным шагом")

    def test_params_shows_pending_values(self):
        self.declare()
        out = self.sm("params", self.m)
        self.assertIn("значения не заданы", out)
        self.assertIn("ждут: cart", out)

    def test_exclude_recorded(self):
        self.sm("exclude", self.m, "кнопка", "не вход системы")
        self.assertIn("кнопка", self.model()["excluded"])

    # --- этап 2 ---

    def test_values_before_declare_refused(self):
        out = self.sm("param", "values", self.m, "--name", "cart",
                      "--all-values", "a", expect=2)
        self.assertIn("не объявлен", out)

    def test_values_require_all_values(self):
        self.declare()
        out = self.sm("param", "values", self.m, "--name", "cart",
                      "--values", "a", expect=2)
        self.assertIn("--all-values", out)

    def test_grouping_required_when_collapsing(self):
        self.declare()
        out = self.sm("param", "values", self.m, "--name", "cart",
                      "--all-values", "a", "b", "c", "--values", "a", "bc", expect=2)
        self.assertIn("--grouping", out)

    def test_grouping_recorded(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart",
                "--all-values", "a", "b", "c", "--values", "a", "bc",
                "--grouping", "b и c дают один исход по §1")
        p = self.model()["params"]["cart"]
        self.assertEqual(len(p["all_values"]), 3)
        self.assertEqual(len(p["values"]), 2)
        self.assertIn("один исход", p["grouping"])

    def test_values_default_to_all_values(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        self.assertEqual(self.model()["params"]["cart"]["values"], ["a", "b"])

    # --- этап 3 ---

    def test_state_requires_evidence_ref(self):
        self.declare()
        out = self.sm("state", "add", self.m, "--name", "S", "--desc", "видно",
                      "--evidence", "просто так", expect=2)
        self.assertIn("ссылки", out)

    def test_state_requires_desc(self):
        self.declare()
        out = self.sm("state", "add", self.m, "--name", "S",
                      "--evidence", "spec.md:§1", expect=2)
        self.assertIn("--desc", out)

    def test_state_unknown_value_refused(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        out = self.sm("state", "add", self.m, "--name", "S", "--when", "cart=z",
                      "--desc", "видно", "--evidence", "spec.md:§1", expect=2)
        self.assertIn("отсутствует", out)

    # --- этап 4 ---

    def test_build_refuses_without_values(self):
        self.declare()
        out = self.sm("build", self.m, "--root", self.d, expect=2)
        self.assertIn("нет значений", out)

    def test_build_refuses_without_states(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        out = self.sm("build", self.m, "--root", self.d, expect=2)
        self.assertIn("нет ни одного состояния", out)

    def test_rule_without_ref_needs_ask(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        out = self.sm("rule", "add", self.m, "--id", "r1", "--forbid", "cart=a",
                      "--evidence", "просто так", expect=2)
        self.assertIn("--ask", out)

    def test_rule_with_ref_is_proven(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        self.sm("rule", "add", self.m, "--id", "r1", "--forbid", "cart=a",
                "--evidence", "spec.md:§1 — так написано")
        self.assertEqual(self.model()["constraints"][0]["status"], "proven")

    def test_full_flow_builds(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart",
                "--all-values", "pending", "ok")
        self.sm("state", "add", self.m, "--name", "Загрузка", "--when", "cart=pending",
                "--desc", "скелетон", "--evidence", "spec.md:§1")
        self.sm("state", "add", self.m, "--name", "Готово", "--when", "cart=ok",
                "--desc", "форма", "--evidence", "spec.md:§1")
        out = self.sm("build", self.m, "--root", self.d)
        self.assertIn("МАТРИЦА", out)
        self.assertIn("Загрузка", out)
        self.assertNotIn("БЕЗ СОСТОЯНИЯ", out)

    def test_param_rm_cleans_dependents(self):
        self.declare()
        self.sm("param", "values", self.m, "--name", "cart", "--all-values", "a", "b")
        self.sm("state", "add", self.m, "--name", "S", "--when", "cart=a",
                "--desc", "видно", "--evidence", "spec.md:§1")
        out = self.sm("param", "rm", self.m, "cart")
        self.assertIn("заодно убрано состояние", out)
        self.assertEqual(self.model()["states"], [])

    def test_answer_writes_file(self):
        self.sm("answer", self.m, "r1", "proven")
        p = os.path.join(self.d, ".states", "models", "answers.json")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["constraints"]["r1"], "proven")
