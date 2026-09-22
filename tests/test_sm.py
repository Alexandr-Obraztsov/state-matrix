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

    def add(self, name="cart", *vals):
        self.sm("param", "add", self.m, "--name", name, "--desc", "описание",
                "--from", "spec.md:§1", "--all-values", *(vals or ("a", "b")))

    def state(self, name="S"):
        self.sm("state", "add", self.m, "--name", name, "--desc", "видно",
                "--evidence", "spec.md:§1")

    # --- параметры ---

    def test_param_requires_desc(self):
        out = self.sm("param", "add", self.m, "--name", "cart",
                      "--from", "spec.md:§1", "--all-values", "a", expect=2)
        self.assertIn("--desc", out)

    def test_param_requires_from(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--desc", "d",
                      "--all-values", "a", expect=2)
        self.assertIn("--from", out)

    def test_param_requires_all_values(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--desc", "d",
                      "--from", "spec.md:§1", expect=2)
        self.assertIn("--all-values", out)

    def test_invented_reference_refused(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--desc", "d",
                      "--from", "spec.md:§99", "--all-values", "a", expect=2)
        self.assertIn("выдумана", out)

    def test_grouping_required(self):
        out = self.sm("param", "add", self.m, "--name", "cart", "--desc", "d",
                      "--from", "spec.md:§1", "--all-values", "a", "b", "c",
                      "--values", "a", "bc", expect=2)
        self.assertIn("--grouping", out)

    def test_grouping_recorded(self):
        self.sm("param", "add", self.m, "--name", "cart", "--desc", "d",
                "--from", "spec.md:§1", "--all-values", "a", "b", "c",
                "--values", "a", "bc", "--grouping", "b и c дают один исход по §1")
        p = self.model()["params"]["cart"]
        self.assertEqual(len(p["all_values"]), 3)
        self.assertEqual(len(p["values"]), 2)
        self.assertNotIn("type", p, "тип параметра больше не хранится")

    # --- состояния ---


    def test_state_requires_real_reference(self):
        out = self.sm("state", "add", self.m, "--name", "S", "--desc", "видно",
                      "--evidence", "просто так", expect=2)
        self.assertIn("не подтверждается", out)

    def test_state_requires_desc(self):
        out = self.sm("state", "add", self.m, "--name", "S",
                      "--evidence", "spec.md:§1", expect=2)
        self.assertIn("--desc", out)

    def test_state_has_no_condition(self):
        self.state()
        st = self.model()["states"][0]
        self.assertNotIn("when", st, "состояния больше не несут условий")

    def test_duplicate_state_refused(self):
        self.state()
        self.sm("state", "add", self.m, "--name", "S", "--desc", "видно",
                "--evidence", "spec.md:§1", expect=2)

    # --- правила и матрица ---


    def test_rule_requires_real_reference(self):
        self.add()
        out = self.sm("rule", "add", self.m, "--id", "r1", "--forbid", "cart=a",
                      "--evidence", "потому что", expect=2)
        self.assertIn("не подтверждается", out)

    def test_build_refuses_without_params(self):
        out = self.sm("build", self.m, expect=2)
        self.assertIn("нет параметров", out)

    def test_build_refuses_without_states(self):
        self.add()
        out = self.sm("build", self.m, expect=2)
        self.assertIn("нет ни одного состояния", out)

    def test_build_lists_unassigned_rows(self):
        self.add("cart", "pending", "ok")
        self.state("Загрузка")
        out = self.sm("build", self.m)
        self.assertIn("БЕЗ СОСТОЯНИЯ: r000, r001", out)
        self.assertIn("НЕ НАЗНАЧЕНО", out)

    def test_assign_fills_rows(self):
        self.add("cart", "pending", "ok")
        self.state("Загрузка")
        self.sm("build", self.m)
        self.sm("assign", self.m, "--state", "Загрузка", "--rows", "r000")
        out = self.sm("build", self.m)
        self.assertIn("Загрузка", out)
        self.assertEqual(out.count("НЕ НАЗНАЧЕНО"), 1, "должна остаться одна строка")

    def test_assign_unknown_state_refused(self):
        self.add()
        self.state()
        self.sm("build", self.m)
        out = self.sm("assign", self.m, "--state", "Нет такого", "--rows", "r000",
                      expect=2)
        self.assertIn("нет", out)

    def test_assign_unknown_row_refused(self):
        self.add()
        self.state()
        self.sm("build", self.m)
        out = self.sm("assign", self.m, "--state", "S", "--rows", "r999", expect=2)
        self.assertIn("нет таких строк", out)

    def test_assignment_survives_rebuild(self):
        self.add("cart", "pending", "ok")
        self.state("Загрузка")
        self.sm("build", self.m)
        self.sm("assign", self.m, "--state", "Загрузка", "--rows", "r000")
        self.assertEqual(len(self.model()["assignments"]), 1)
        self.sm("build", self.m)
        self.assertEqual(len(self.model()["assignments"]), 1)

    def test_state_rm_drops_assignments(self):
        self.add("cart", "pending", "ok")
        self.state("Загрузка")
        self.sm("build", self.m)
        self.sm("assign", self.m, "--state", "Загрузка", "--rows", "r000")
        self.sm("state", "rm", self.m, "Загрузка")
        self.assertEqual(self.model()["assignments"], {})

    def test_param_rm_cleans_rules(self):
        self.add()
        self.sm("rule", "add", self.m, "--id", "r1", "--forbid", "cart=a",
                "--evidence", "spec.md:§1")
        out = self.sm("param", "rm", self.m, "cart")
        self.assertIn("заодно убрано правило", out)
