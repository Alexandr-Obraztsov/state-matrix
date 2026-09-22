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
