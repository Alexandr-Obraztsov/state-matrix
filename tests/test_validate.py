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

    def test_param_without_from_is_error(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"]}}))
        self.assertTrue(any("from" in z for z in e), e)

    def test_param_without_values_is_error(self):
        e, w = self.check(m(params={"x": {"type": "enum", "desc": "d", "from": "a.md:1"}}))
        self.assertTrue(any("нет values" in z for z in e), e)

    def test_state_without_evidence_is_error(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"], "from": "a.md:1"}},
                            states=[{"name": "S", "when": {"x": "a"}, "desc": "d"}]))
        self.assertTrue(any("evidence" in z for z in e), e)

    def test_state_without_desc_is_error(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"], "from": "a.md:1"}},
                            states=[{"name": "S", "when": {"x": "a"},
                                     "evidence": "a.md:1"}]))
        self.assertTrue(any("desc" in z for z in e), e)

    def test_catchall_state_must_be_last(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"], "from": "a.md:1"}},
                            states=[{"name": "Все", "when": {}, "desc": "d",
                                     "evidence": "a.md:1"},
                                    {"name": "Частный", "when": {"x": "a"}, "desc": "d",
                                     "evidence": "a.md:1"}]))
        self.assertTrue(any("не последнее" in z for z in e), e)

    def test_duplicate_state_name_is_error(self):
        st = {"name": "S", "when": {"x": "a"}, "desc": "d", "evidence": "a.md:1"}
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"], "from": "a.md:1"}},
                            states=[st, dict(st)]))
        self.assertTrue(any("повторяется" in z for z in e), e)

    def test_no_states_is_warning(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"],
                                          "all_values": ["a"], "from": "a.md:1"}}))
        self.assertTrue(any("состояния" in z for z in w), w)


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
