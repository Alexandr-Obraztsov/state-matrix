import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import engine


def model(nvals):
    p = {f"p{i}": {"values": [f"v{j}" for j in range(n)], "from": "x.ts:1"}
         for i, n in enumerate(nvals)}
    return {"system": "T", "params": p}


class T(unittest.TestCase):
    def test_under_ceiling_no_advice(self):
        r = engine.build(model([2, 2, 2]), {})
        self.assertFalse(r["slices"][0]["advice"]["over"])

    def test_over_ceiling_flags(self):
        r = engine.build(model([4, 4, 4, 4]), {})
        a = r["slices"][0]["advice"]
        self.assertTrue(a["over"])
        self.assertEqual(len(a["contributions"]), 4)

    def test_env_candidate_is_param_no_transition_sets(self):
        m = model([4, 4, 4, 4])
        m["initial"] = {f"p{i}": "v0" for i in range(4)}
        m["transitions"] = [{"event": "e", "set": {"p0": "v1"}, "evidence": "x.ts:1"}]
        a = engine.build(m, {})["slices"][0]["advice"]
        byname = {c["param"]: c for c in a["contributions"]}
        self.assertFalse(byname["p0"]["env_candidate"], "p0 меняется переходом")
        self.assertTrue(byname["p1"]["env_candidate"])

    def test_rows_if_env_divides(self):
        a = engine.build(model([4, 4, 4, 4]), {})["slices"][0]["advice"]
        c = a["contributions"][0]
        self.assertEqual(c["rows_if_env"], 256 // c["factor"])

    def test_unruled_lists_params_without_rules(self):
        m = model([2, 2])
        m["constraints"] = [{"id": "c", "when": {"p0": "v0"}, "irrelevant": ["p1"],
                             "evidence": "x.ts:1", "status": "proven"}]
        a = engine.build(m, {})["slices"][0]["advice"]
        self.assertNotIn("p0", a["unruled"])
        self.assertNotIn("p1", a["unruled"])

    def test_ceiling_finding_is_actionable(self):
        r = engine.build(model([4, 4, 4, 4]), {})
        f = [x for x in r["slices"][0]["findings"] if x["class"] == "CEILING"]
        self.assertTrue(f)
        msg = f[0]["message"]
        self.assertIn("env-кандидат", msg)
        self.assertIn("дешевле всего", msg)

    def test_ceiling_is_100(self):
        import store
        self.assertEqual(store.CEILING, 100)
