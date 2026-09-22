import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store, validate

CAT = os.path.join(os.path.dirname(__file__), "..", "catalog", "default.json")


def m(**kw):
    base = {"system": "T", "source": "a.ts", "params": {}, "constraints": []}
    base.update(kw)
    return base


class T(unittest.TestCase):
    def check(self, model):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.states.json")
            store.save(p, model)
            return validate.check(p)

    def _with_catalog(self, d, params):
        store.save(os.path.join(d, "catalog.json"),
                   [{"id": "money_amount", "title": "Сумма", "desc": "…",
                     "matches": {"names": ["amount"], "types": ["number"]},
                     "questions": [{"id": "unit", "ask": "единицы?",
                                    "options": ["в спеке не сказано"]}],
                     "values": ["zero"]}])
        p = os.path.join(d, "m.states.json")
        store.save(p, m(params=params))
        return validate.check(p)

    def test_question_ignored_entirely_is_error(self):
        """Вопрос, которого вообще нет в answers, — признак обхода тулов."""
        with tempfile.TemporaryDirectory() as d:
            e, w = self._with_catalog(d, {"amount": {
                "type": "number", "catalog": "money_amount", "values": ["zero"],
                "all_values": ["zero"], "from": "a.ts:1"}})
        self.assertTrue(any("не учтён" in x for x in e), e)

    def test_not_found_answer_is_warning_not_error(self):
        """«Не выяснено» — замечание в отчёт, а не отказ."""
        with tempfile.TemporaryDirectory() as d:
            e, w = self._with_catalog(d, {"amount": {
                "type": "number", "catalog": "money_amount", "values": ["zero"],
                "all_values": ["zero"], "from": "a.ts:1",
                "answers": {"unit": "не выяснено"}}})
        self.assertEqual(e, [])
        self.assertTrue(any("не выяснено" in x for x in w), w)

    def test_error_names_the_bypass(self):
        with tempfile.TemporaryDirectory() as d:
            e, w = self._with_catalog(d, {"amount": {
                "type": "number", "catalog": "money_amount", "values": ["zero"],
                "all_values": ["zero"], "from": "a.ts:1"}})
        self.assertTrue(any("обход" in x for x in e), e)

    def test_param_with_all_answers_ok(self):
        with tempfile.TemporaryDirectory() as d:
            e, w = self._with_catalog(d, {"amount": {
                "type": "number", "catalog": "money_amount", "values": ["zero"],
                "all_values": ["zero"], "from": "a.ts:1",
                "answers": {"unit": "копейки — §3"}}})
        self.assertEqual(e, [])
        self.assertEqual(w, [])

    def test_param_without_catalog_still_needs_from(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"], "answers": {}}}))
        self.assertTrue(any("from" in x for x in e))

    def test_unknown_catalog_id_is_error(self):
        e, w = self.check(m(params={"x": {"type": "enum", "catalog": "нет_такой",
                                          "values": ["a"], "from": "a.ts:1", "answers": {}}}))
        self.assertTrue(any("нет_такой" in x for x in e), e)


class Grouping(unittest.TestCase):
    """Все значения перечисляются до объединения, объединение объясняется."""

    def check(self, params):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.states.json")
            store.save(p, {"system": "T", "source": "a.md", "params": params,
                           "constraints": []})
            return validate.check(p)

    def test_missing_all_values_is_error(self):
        e, w = self.check({"x": {"type": "enum", "values": ["a"], "from": "a.md:1"}})
        self.assertTrue(any("all_values" in z for z in e), e)

    def test_grouping_required_when_collapsed(self):
        e, w = self.check({"x": {"type": "enum", "all_values": ["a", "b", "c"],
                                 "values": ["a", "bc"], "from": "a.md:1"}})
        self.assertTrue(any("без объяснения" in z for z in e), e)

    def test_grouping_present_is_ok(self):
        e, w = self.check({"x": {"type": "enum", "all_values": ["a", "b", "c"],
                                 "values": ["a", "bc"], "from": "a.md:1",
                                 "grouping": "b и c дают один исход по §2"}})
        self.assertEqual([z for z in e if "объяснения" in z], [])

    def test_no_collapse_needs_no_grouping(self):
        e, w = self.check({"x": {"type": "enum", "all_values": ["a", "b"],
                                 "values": ["a", "b"], "from": "a.md:1"}})
        self.assertEqual(e, [])
