"""Протокол sm.py: порядок этапов и отказы."""
import json, os, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(ROOT, "scripts", "sm.py")

SPEC = """# Спека

## §1 Корзина
Загрузка, готово, пусто.

## §2 Сумма
Ноль допустим.
"""


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".states", "models"))
        self.m = os.path.join(self.d, ".states", "models", "X.states.json")
        with open(os.path.join(self.d, "spec.md"), "w", encoding="utf-8") as f:
            f.write(SPEC)
        self.sm("init", self.m, "--system", "X", "--source", "spec.md")

    def sm(self, *a, expect=0):
        r = subprocess.run([sys.executable, SM, "--root", self.d, *a],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, expect, f"код {r.returncode}\n{r.stdout}{r.stderr}")
        return r.stdout + r.stderr

    def model(self):
        with open(self.m, encoding="utf-8") as f:
            return json.load(f)

    def declare(self, name="cart"):
        self.sm("param", "add", self.m, "--name", name, "--type", "enum",
                "--desc", "описание", "--from", "spec.md:§1")

    def with_values(self, name="cart", *vals):
        self.declare(name)
        self.sm("param", "values", self.m, "--name", name, "--all-values", *(vals or ("a", "b")))

    # --- этап 1 ---

    def test_param_requires_desc(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--type", "enum",
                      "--from", "spec.md:§1", expect=2)
        self.assertIn("--desc", out)

    def test_param_requires_from(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--type", "enum",
                      "--desc", "d", expect=2)
        self.assertIn("--from", out)

    def test_invented_reference_refused(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--type", "enum",
                      "--desc", "d", "--from", "spec.md:§99", expect=2)
        self.assertIn("выдумана", out)

    def test_declared_without_values(self):
        self.declare()
        self.assertNotIn("values", self.model()["params"]["cart"])

    def test_params_shows_what_is_missing(self):
        self.declare()
        out = self.sm("params", self.m)
        self.assertIn("значения не заданы", out)
        self.assertIn("ждут: cart", out)

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

    def test_grouping_required(self):
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

    # --- этап 3 ---

    def test_state_requires_real_reference(self):
        self.with_values()
        out = self.sm("state", "add", self.m, "--name", "S", "--desc", "видно",
                      "--evidence", "просто так", expect=2)
        self.assertIn("не подтверждается", out)

    def test_state_requires_desc(self):
        self.with_values()
        out = self.sm("state", "add", self.m, "--name", "S",
                      "--evidence", "spec.md:§1", expect=2)
        self.assertIn("--desc", out)

    def test_state_unknown_value_refused(self):
        self.with_values()
        out = self.sm("state", "add", self.m, "--name", "S", "--when", "cart=z",
                      "--desc", "видно", "--evidence", "spec.md:§1", expect=2)
        self.assertIn("отсутствует", out)

    # --- этап 4 ---

    def test_rule_requires_real_reference(self):
        self.with_values()
        out = self.sm("rule", "add", self.m, "--id", "r1", "--forbid", "cart=a",
                      "--evidence", "потому что", expect=2)
        self.assertIn("не подтверждается", out)

    def test_build_refuses_without_values(self):
        self.declare()
        out = self.sm("build", self.m, expect=2)
        self.assertIn("нет значений", out)

    def test_build_refuses_without_states(self):
        self.with_values()
        out = self.sm("build", self.m, expect=2)
        self.assertIn("нет ни одного состояния", out)

    def test_full_flow(self):
        self.with_values("cart", "pending", "ok")
        self.sm("state", "add", self.m, "--name", "Загрузка", "--when", "cart=pending",
                "--desc", "скелетон", "--evidence", "spec.md:§1")
        self.sm("state", "add", self.m, "--name", "Готово", "--when", "cart=ok",
                "--desc", "форма", "--evidence", "spec.md:§1")
        out = self.sm("build", self.m)
        self.assertIn("МАТРИЦА", out)
        self.assertIn("Загрузка", out)
        self.assertNotIn("НЕ ОПРЕДЕЛЕНО", out)

    def test_rows_without_state(self):
        self.with_values("cart", "pending", "ok")
        self.sm("state", "add", self.m, "--name", "Загрузка", "--when", "cart=pending",
                "--desc", "скелетон", "--evidence", "spec.md:§1")
        self.sm("build", self.m)
        out = self.sm("rows", os.path.join(self.d, ".states", "runs", "X.json"),
                      "--no-state")
        self.assertIn("1 строк из 2", out)

    def test_param_rm_cleans_dependents(self):
        self.with_values()
        self.sm("state", "add", self.m, "--name", "S", "--when", "cart=a",
                "--desc", "видно", "--evidence", "spec.md:§1")
        out = self.sm("param", "rm", self.m, "cart")
        self.assertIn("заодно убрано состояние", out)
        self.assertEqual(self.model()["states"], [])
