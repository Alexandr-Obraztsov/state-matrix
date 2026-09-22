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
