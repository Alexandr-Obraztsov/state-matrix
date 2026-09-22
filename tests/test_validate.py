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

    def test_param_without_answers_is_error(self):
        e, w = self.check(m(params={"amount": {"type": "number", "catalog": "money_amount",
                                               "values": ["zero"], "from": "a.ts:1"}}))
        self.assertTrue(any("ответа" in x for x in e), e)

    def test_error_names_the_bypass(self):
        e, w = self.check(m(params={"amount": {"type": "number", "catalog": "money_amount",
                                               "values": ["zero"], "from": "a.ts:1"}}))
        self.assertTrue(any("обход" in x for x in e), e)

    def test_param_with_all_answers_ok(self):
        qs = next(c for c in store.load(CAT) if c["id"] == "money_amount")["questions"]
        e, w = self.check(m(params={"amount": {
            "type": "number", "catalog": "money_amount", "values": ["zero"],
            "from": "a.ts:1", "answers": {q["id"]: "неизвестно" for q in qs}}}))
        self.assertEqual([x for x in e if "ответа" in x], [])

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
