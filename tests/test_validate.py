"""Инварианты модели и проверка ссылок."""
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store, validate

SPEC = "# Спека\n\n## §1 Раздел\nтекст\n"


def param(**kw):
    p = {"desc": "d", "from": "spec.md:§1",
         "all_values": ["a"], "values": ["a"]}
    p.update(kw)
    return p


def state(**kw):
    s = {"name": "S", "desc": "видно", "evidence": "spec.md:§1"}
    s.update(kw)
    return s


class T(unittest.TestCase):
    def check(self, params=None, constraints=None, states=None, assignments=None):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "spec.md"), "w", encoding="utf-8") as f:
                f.write(SPEC)
            p = os.path.join(d, "m.states.json")
            store.save(p, {"system": "T", "source": "spec.md",
                           "params": params if params is not None else {"x": param()},
                           "constraints": constraints or [],
                           "states": states if states is not None else [state()],
                           "assignments": assignments or {}})
            return validate.check(p, d)

    def test_clean_model_passes(self):
        e, w = self.check()
        self.assertEqual(e, [])

    def test_param_without_desc(self):
        e, w = self.check({"x": param(desc=None)})
        self.assertTrue(any("desc" in z for z in e), e)

    def test_param_without_values(self):
        p = param(); del p["values"]
        e, w = self.check({"x": p})
        self.assertTrue(any("значения не заданы" in z for z in e), e)

    def test_param_without_all_values(self):
        p = param(); del p["all_values"]
        e, w = self.check({"x": p})
        self.assertTrue(any("all_values" in z for z in e), e)

    def test_collapse_without_grouping(self):
        e, w = self.check({"x": param(all_values=["a", "b"], values=["a"])})
        self.assertTrue(any("без объяснения" in z for z in e), e)

    def test_invented_section_caught(self):
        e, w = self.check({"x": param(**{"from": "spec.md:§99"})})
        self.assertTrue(any("выдумана" in z for z in e), e)

    def test_missing_file_caught(self):
        e, w = self.check({"x": param(**{"from": "nowhere.md:§1"})})
        self.assertTrue(any("нет файла" in z for z in e), e)

    def test_reference_without_anchor_caught(self):
        e, w = self.check({"x": param(**{"from": "просто текст"})})
        self.assertTrue(any("нет ссылки" in z for z in e), e)

    def test_state_without_evidence(self):
        s = state(); del s["evidence"]
        e, w = self.check(states=[s])
        self.assertTrue(any("evidence" in z for z in e), e)

    def test_state_without_desc(self):
        s = state(); del s["desc"]
        e, w = self.check(states=[s])
        self.assertTrue(any("desc" in z for z in e), e)

    def test_assignment_to_unknown_state(self):
        e, w = self.check(assignments={"x=a": "Нет такого"})
        self.assertTrue(any("Нет такого" in z for z in e), e)

    def test_duplicate_state_names(self):
        e, w = self.check(states=[state(), state()])
        self.assertTrue(any("повторяется" in z for z in e), e)

    def test_no_states_is_warning(self):
        e, w = self.check(states=[])
        self.assertEqual(e, [])
        self.assertTrue(any("состояния" in z for z in w), w)

    def test_rule_without_evidence(self):
        e, w = self.check(constraints=[{"id": "r", "forbid": {"x": "a"}}])
        self.assertTrue(any("evidence" in z for z in e), e)

    def test_rule_unknown_param(self):
        e, w = self.check(constraints=[{"id": "r", "forbid": {"нет": "a"},
                                        "evidence": "spec.md:§1"}])
        self.assertTrue(any("неизвестный параметр" in z for z in e), e)
