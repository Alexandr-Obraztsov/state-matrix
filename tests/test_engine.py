"""Движок: свёртка, состояния, потолок. Без сети и без ИИ."""
import os, sys, json, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import engine


def model(params, constraints=None, states=None):
    return {"system": "T", "source": "s.md", "params": params,
            "constraints": constraints or [], "states": states or []}


def enum(*vals, **kw):
    p = {"type": "enum", "desc": "d", "from": "s.md:§1",
         "all_values": list(vals), "values": list(vals)}
    p.update(kw)
    return p


class Matrix(unittest.TestCase):
    def test_cartesian(self):
        r = engine.build(model({"a": enum("1", "2"), "b": enum("x", "y", "z")}))
        self.assertEqual(r["counts"]["total"], 6)
        self.assertEqual(r["counts"]["collapsed"], 6)

    def test_deterministic(self):
        m = model({"a": enum("1", "2"), "b": enum("x", "y")})
        a = json.dumps(engine.build(m), sort_keys=True, default=str)
        b = json.dumps(engine.build(m), sort_keys=True, default=str)
        self.assertEqual(a, b, "движок обязан быть детерминированным")

    def test_forbid_removes_rows(self):
        r = engine.build(model(
            {"a": enum("1", "2"), "b": enum("x", "y")},
            [{"id": "c", "forbid": {"a": "1", "b": "x"}, "evidence": "s.md:§1"}]))
        self.assertEqual(r["counts"]["valid"], 3)

    def test_irrelevant_collapses_columns(self):
        r = engine.build(model(
            {"a": enum("1", "2"), "b": enum("x", "y", "z")},
            [{"id": "c", "when": {"a": "1"}, "irrelevant": ["b"], "evidence": "s.md:§1"}]))
        starred = [row for row in r["rows"] if row["values"]["b"] == "*"]
        self.assertEqual(len(starred), 1)
        self.assertEqual(starred[0]["covers"], 3)
        self.assertEqual(r["counts"]["collapsed"], 4)

    def test_specials_are_outside_the_product(self):
        r = engine.build(model({"a": enum("1", "2", special=["nan", "inf"])}))
        self.assertEqual(r["counts"]["total"], 2)
        self.assertEqual(r["counts"]["specials"], 2)


class States(unittest.TestCase):
    def st(self, name, when):
        return {"name": name, "when": when, "desc": "видно", "evidence": "s.md:§1"}

    def test_first_match_wins(self):
        r = engine.build(model(
            {"a": enum("1", "2")},
            states=[self.st("Частный", {"a": "1"}), self.st("Общий", {})]))
        by = {row["values"]["a"]: row["state"] for row in r["rows"]}
        self.assertEqual(by["1"], "Частный")
        self.assertEqual(by["2"], "Общий")

    def test_rows_without_state_are_counted(self):
        r = engine.build(model({"a": enum("1", "2")},
                               states=[self.st("Только один", {"a": "1"})]))
        self.assertEqual(r["counts"]["no_state"], 1)
        self.assertTrue(any(f["class"] == "UNDEFINED" for f in r["findings"]))

    def test_state_rows_counted(self):
        r = engine.build(model({"a": enum("1", "2", "3")},
                               states=[self.st("Все", {})]))
        self.assertEqual(r["states"][0]["rows"], 3)

    def test_mixed_state_detected(self):
        """Схлопнутая строка не должна покрывать разные состояния."""
        r = engine.build(model(
            {"a": enum("1"), "b": enum("x", "y")},
            [{"id": "c", "when": {"a": "1"}, "irrelevant": ["b"], "evidence": "s.md:§1"}],
            [self.st("Первое", {"b": "x"}), self.st("Второе", {"b": "y"})]))
        self.assertTrue(any(f["class"] == "MIXED_STATE" for f in r["findings"]))


class Findings(unittest.TestCase):
    def test_ceiling_is_100(self):
        import store
        self.assertEqual(store.CEILING, 100)

    def test_ceiling_lists_contributions(self):
        params = {f"p{i}": enum(*[str(j) for j in range(4)]) for i in range(4)}
        r = engine.build(model(params))
        f = [x for x in r["findings"] if x["class"] == "CEILING"]
        self.assertTrue(f)
        self.assertIn("вклад параметров", f[0]["message"])
        self.assertIn("×4", f[0]["message"])

    def test_no_ceiling_finding_when_small(self):
        r = engine.build(model({"a": enum("1", "2")},
                               states=[{"name": "S", "when": {}, "desc": "d",
                                        "evidence": "s.md:§1"}]))
        self.assertFalse([x for x in r["findings"] if x["class"] == "CEILING"])

    def test_rule_overlap_detected(self):
        r = engine.build(model(
            {"a": enum("1", "2"), "b": enum("x", "y"), "c": enum("p", "q")},
            [{"id": "r1", "when": {"a": "1"}, "irrelevant": ["c"], "evidence": "s.md:§1"},
             {"id": "r2", "when": {"b": "x"}, "irrelevant": ["c"], "evidence": "s.md:§1"}]))
        self.assertTrue(any(f["class"] == "RULE_OVERLAP" for f in r["findings"]))
