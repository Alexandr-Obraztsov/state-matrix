import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store

CAT = os.path.join(os.path.dirname(__file__), "..", "catalog", "default.json")


class T(unittest.TestCase):
    def setUp(self):
        self.c = store.load(CAT)

    def test_fifteen_or_more(self):
        self.assertGreaterEqual(len(self.c), 15)

    def test_required_keys(self):
        for e in self.c:
            for k in ("id", "matches", "questions", "values"):
                self.assertIn(k, e, e.get("id"))
            self.assertTrue(e["questions"], f"{e['id']}: семантика без вопросов бесполезна")
            for q in e["questions"]:
                self.assertIn("id", q)
                self.assertIn("ask", q)
                self.assertTrue(q["ask"].endswith("?"),
                                f"{e['id']}/{q['id']}: вопрос без знака вопроса")

    def test_ids_unique(self):
        ids = [e["id"] for e in self.c]
        self.assertEqual(len(ids), len(set(ids)))

    def test_key_semantics_present(self):
        ids = {e["id"] for e in self.c}
        for need in ("free_text", "number", "money_amount", "http_endpoint",
                     "error_state", "auth_role", "collection", "date_time"):
            self.assertIn(need, ids)

    def test_endpoint_asks_about_failures(self):
        ep = next(e for e in self.c if e["id"] == "http_endpoint")
        asks = " ".join(q["ask"] for q in ep["questions"]).lower()
        for word in ("таймаут", "пуст", "авториз"):
            self.assertIn(word, asks)

    def test_env_candidates_marked(self):
        ids = {e["id"]: e for e in self.c}
        for n in ("viewport", "locale", "feature_flag"):
            self.assertTrue(ids[n].get("env_candidate"), f"{n} должен быть env-кандидатом")

    def test_matches_are_lists(self):
        for e in self.c:
            m = e["matches"]
            self.assertIsInstance(m.get("names", []), list)
            self.assertIsInstance(m.get("types", []), list)
            self.assertTrue(m.get("names") or m.get("types"),
                            f"{e['id']}: семантику невозможно найти")


class NoOverlap(unittest.TestCase):
    def test_names_do_not_collide(self):
        """Имя в двух семантиках — параметр уйдёт не в ту корзину."""
        c = store.load(CAT)
        seen, dupes = {}, []
        for e in c:
            for n in e["matches"].get("names", []):
                if n in seen:
                    dupes.append(f"«{n}»: {seen[n]} и {e['id']}")
                seen[n] = e["id"]
        self.assertEqual(dupes, [])


class Learning(unittest.TestCase):
    """Корзина должна учиться: правка пользователя дописывает вопрос в тип."""

    def setUp(self):
        import subprocess, tempfile, sys
        self.sub, self.sys = subprocess, sys
        self.d = tempfile.mkdtemp()
        self.m = os.path.join(self.d, ".states", "models", "T.states.json")
        os.makedirs(os.path.dirname(self.m))
        self.sm = os.path.join(os.path.dirname(__file__), "..", "scripts", "sm.py")
        self.sm_run("init", self.m, "--system", "T", "--source", "spec.md")

    def sm_run(self, *a, expect=0):
        r = self.sub.run([self.sys.executable, self.sm, *a], capture_output=True, text=True)
        self.assertEqual(r.returncode, expect, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def test_every_question_has_options(self):
        for e in store.load(CAT):
            for q in e["questions"]:
                self.assertTrue(q.get("options"), f"{e['id']}/{q['id']}: нет вариантов")
                self.assertEqual(q["options"][-1], "в спеке не сказано",
                                 f"{e['id']}/{q['id']}: последний вариант обязателен")

    def test_every_type_has_title_and_desc(self):
        for e in store.load(CAT):
            self.assertTrue(e.get("title"), f"{e['id']}: нет названия")
            self.assertTrue(e.get("desc"), f"{e['id']}: нет описания")

    def test_list_hides_questions(self):
        out = self.sm_run("catalog-list")
        self.assertIn("Обращение к сервису", out)
        self.assertNotIn("идемпотентен", out, "список не должен вываливать вопросы")

    def test_get_shows_questions_with_options(self):
        out = self.sm_run("catalog-get", self.m, "http_endpoint")
        self.assertIn("идемпотентен", out)
        self.assertIn("варианты:", out)

    def test_edit_adds_question_and_persists(self):
        before = self.sm_run("catalog-get", self.m, "http_endpoint")
        self.sm_run("catalog-edit", self.m, "http_endpoint",
                 "--add-questions", "cache=кэшируется ли ответ?|да|нет")
        after = self.sm_run("catalog-get", self.m, "http_endpoint")
        self.assertNotIn("кэшируется", before)
        self.assertIn("кэшируется", after)
        proj = store.load(os.path.join(self.d, ".states", "catalog.json"))
        self.assertEqual(proj[0]["id"], "http_endpoint")
        self.assertEqual(proj[0]["questions"][0]["options"][-1], "в спеке не сказано")

    def test_edit_does_not_touch_default_catalog(self):
        self.sm_run("catalog-edit", self.m, "http_endpoint",
                 "--add-questions", "cache=кэшируется ли ответ?|да|нет")
        d = store.load(CAT)
        ep = next(c for c in d if c["id"] == "http_endpoint")
        self.assertFalse(any(q["id"] == "cache" for q in ep["questions"]),
                         "дефолтная корзина плагина правиться не должна")

    def test_added_name_makes_type_findable(self):
        out = self.sm_run("catalog", self.m, "cart", "--type", "endpoint")
        self.assertIn("ВЫБЕРИ САМ", out)
        self.sm_run("catalog-edit", self.m, "http_endpoint", "--add-names", "cart")
        out = self.sm_run("catalog", self.m, "cart", "--type", "endpoint")
        self.assertIn("ТОЧНОЕ СОВПАДЕНИЕ", out)

    def test_duplicate_question_refused(self):
        self.sm_run("catalog-edit", self.m, "http_endpoint",
                 "--add-questions", "retry=повтор?|да", expect=2)

    def test_new_type_requires_title_and_desc(self):
        out = self.sm_run("catalog-new", self.m, "--id", "x", "--type", "enum",
                       "--title", "X", "--questions", "a=что?|да", expect=2)
        self.assertIn("--desc", out)
