"""Движок: свёртка, состояния, потолок. Без сети и без ИИ."""
import os, sys, json, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import engine


def model(params, constraints=None, states=None, assignments=None):
    return {"system": "T", "source": "s.md", "params": params,
            "constraints": constraints or [], "states": states or [],
            "assignments": assignments or {}}


def enum(*vals, **kw):
    p = {"desc": "d", "from": "s.md:§1",
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
    """Состояния — справочник; привязка к строкам хранится по ключу строки."""

    def st(self, name):
        return {"name": name, "desc": "видно", "evidence": "s.md:§1"}

    def test_rows_start_without_state(self):
        r = engine.build(model({"a": enum("1", "2")}, states=[self.st("S")]))
        self.assertEqual(r["counts"]["no_state"], 2)
        self.assertTrue(any(f["class"] == "UNDEFINED" for f in r["findings"]))

    def test_assignment_by_row_key(self):
        r = engine.build(model({"a": enum("1", "2")}, states=[self.st("S")],
                               assignments={"a=1": "S"}))
        by = {row["values"]["a"]: row["state"] for row in r["rows"]}
        self.assertEqual(by["1"], "S")
        self.assertIsNone(by["2"])
        self.assertEqual(r["states"][0]["rows"], 1)

    def test_assignment_to_unknown_state_ignored(self):
        r = engine.build(model({"a": enum("1")}, states=[self.st("S")],
                               assignments={"a=1": "Нет такого"}))
        self.assertIsNone(r["rows"][0]["state"])

    def test_key_survives_collapse(self):
        r = engine.build(model(
            {"a": enum("1"), "b": enum("x", "y")},
            [{"id": "c", "when": {"a": "1"}, "irrelevant": ["b"], "evidence": "s.md:§1"}],
            states=[self.st("S")], assignments={"a=1|b=*": "S"}))
        self.assertEqual(r["rows"][0]["state"], "S")


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
                               states=[{"name": "S", "desc": "d",
                                        "evidence": "s.md:§1"}]))
        self.assertFalse([x for x in r["findings"] if x["class"] == "CEILING"])

