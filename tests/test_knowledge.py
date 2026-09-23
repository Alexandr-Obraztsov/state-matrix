"""База знаний: базовая часть, проектное обогащение, изоляция."""
import json, os, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(R, "scripts", "sm.py")
BASE = os.path.join(R, "knowledge", "base.json")


class Base(unittest.TestCase):
    def setUp(self):
        with open(BASE, encoding="utf-8") as f:
            self.kb = json.load(f)

    def test_covers_main_kinds(self):
        kinds = {k["kind"] for k in self.kb}
        for need in ("строка", "число", "деньги", "перечисление", "список",
                     "дата", "запрос", "ошибка", "права", "файл"):
            self.assertIn(need, kinds)

    def test_every_case_explains_why(self):
        for k in self.kb:
            self.assertTrue(k["cases"], k["kind"])
            for c in k["cases"]:
                self.assertTrue(c.get("case"), k["kind"])
                self.assertTrue(c.get("why"), f"{k['kind']}/{c['case']}: нет объяснения")

    def test_string_has_the_classic_traps(self):
        st = next(k for k in self.kb if k["kind"] == "строка")
        cases = " ".join(c["case"] for c in st["cases"])
        for trap in ("пустая", "пробел", "эмодзи"):
            self.assertIn(trap, cases)

    def test_aka_do_not_collide(self):
        seen = {}
        for k in self.kb:
            for a in [k["kind"]] + (k.get("aka") or []):
                self.assertNotIn(a, seen, f"«{a}»: {seen.get(a)} и {k['kind']}")
                seen[a] = k["kind"]


class Project(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.d, ".states", "models"))
        self.m = os.path.join(self.d, ".states", "models", "X.states.json")
        with open(os.path.join(self.d, "spec.md"), "w", encoding="utf-8") as f:
            f.write("# Спека\n\n## §1 Раздел\nтекст\n")
        self.sm("init", self.m, "--system", "X", "--source", "spec.md")

    def sm(self, *a, expect=0):
        r = subprocess.run([sys.executable, SM, "--root", self.d, *a],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, expect, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def test_list_shows_kinds(self):
        out = self.sm("cases", self.m)
        self.assertIn("строка", out)
        self.assertIn("инпут", out, "синонимы должны быть видны")

    def test_lookup_by_synonym(self):
        out = self.sm("cases", self.m, "--kind", "инпут")
        self.assertIn("только пробелы", out)

    def test_unknown_kind_refused(self):
        out = self.sm("cases", self.m, "--kind", "чепуха", expect=2)
        self.assertIn("в базе нет", out)

    def test_learn_adds_to_project(self):
        self.sm("learn", self.m, "--kind", "строка", "--case", "вставка из Word",
                "--why", "невидимая разметка")
        out = self.sm("cases", self.m, "--kind", "строка")
        self.assertIn("вставка из Word", out)
        self.assertIn("[своё]", out)

    def test_learn_creates_new_kind(self):
        self.sm("learn", self.m, "--kind", "промокод", "--case", "уже использован",
                "--why", "отличается от истёкшего", "--aka", "купон")
        self.assertIn("промокод", self.sm("cases", self.m))
        self.assertIn("уже использован", self.sm("cases", self.m, "--kind", "купон"))

    def test_duplicate_refused(self):
        out = self.sm("learn", self.m, "--kind", "строка", "--case", "только пробелы",
                      expect=2)
        self.assertIn("уже есть", out)

    def test_base_untouched(self):
        before = open(BASE, encoding="utf-8").read()
        self.sm("learn", self.m, "--kind", "строка", "--case", "новое")
        self.assertEqual(open(BASE, encoding="utf-8").read(), before,
                         "базовая база знаний плагина правиться не должна")

    def test_project_file_location(self):
        self.sm("learn", self.m, "--kind", "строка", "--case", "новое")
        self.assertTrue(os.path.exists(os.path.join(self.d, ".states", "knowledge.json")))
