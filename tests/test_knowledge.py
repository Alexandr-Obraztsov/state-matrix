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
        self.sm("learn", self.m, "--kind", "строка", "--case", "голосовой ввод",
                "--why", "невидимая разметка")
        out = self.sm("cases", self.m, "--kind", "строка")
        self.assertIn("голосовой ввод", out)
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


class Focus(unittest.TestCase):
    """Пять главных видов проработаны так, чтобы по ним шла и небольшая модель."""
    FOCUS = ("число", "деньги", "строка", "дата", "запрос")

    def setUp(self):
        with open(BASE, encoding="utf-8") as f:
            self.kb = {k["kind"]: k for k in json.load(f)}

    def test_focus_kinds_come_first(self):
        with open(BASE, encoding="utf-8") as f:
            order = [k["kind"] for k in json.load(f)][:5]
        self.assertEqual(tuple(order), self.FOCUS)

    def test_each_has_the_full_guide(self):
        for name in self.FOCUS:
            k = self.kb[name]
            self.assertTrue(k.get("desc"), name)
            self.assertGreaterEqual(len(k.get("signals") or []), 8, f"{name}: мало сигналов")
            self.assertGreaterEqual(len(k.get("where") or []), 4, f"{name}: мало мест поиска")
            self.assertGreaterEqual(len(k.get("derive") or []), 5, f"{name}: мало шагов")
            self.assertGreaterEqual(len(k["cases"]), 15, f"{name}: мало кейсов")

    def test_cases_are_grouped(self):
        for name in self.FOCUS:
            groups = {c.get("group") for c in self.kb[name]["cases"]}
            self.assertNotIn(None, groups, f"{name}: кейс без группы")
            self.assertGreaterEqual(len(groups), 5, f"{name}: мало групп")

    def test_sources_cited(self):
        for name in self.FOCUS:
            self.assertTrue(self.kb[name].get("sources"), f"{name}: не указаны источники")

    def test_guide_rendered_in_order(self):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, ".states", "models"))
        m = os.path.join(d, ".states", "models", "X.states.json")
        with open(os.path.join(d, "spec.md"), "w", encoding="utf-8") as f:
            f.write("# Спека\n")
        subprocess.run([sys.executable, SM, "--root", d, "init", m, "--system", "X",
                        "--source", "spec.md"], capture_output=True)
        out = subprocess.run([sys.executable, SM, "--root", d, "cases", m, "--kind", "ручка"],
                             capture_output=True, text=True).stdout
        parts = ["КАК УЗНАТЬ В СПЕКЕ", "ГДЕ ИСКАТЬ ЗНАЧЕНИЯ", "КАК ПОЛУЧИТЬ ЗНАЧЕНИЯ",
                 "КОРНЕР-КЕЙСЫ"]
        idx = [out.index(p) for p in parts]
        self.assertEqual(idx, sorted(idx), "разделы должны идти в порядке работы")
        self.assertIn("[ошибки]", out)
