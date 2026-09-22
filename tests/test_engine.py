import json, os, subprocess, sys, unittest, tempfile
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(R, "scripts"))
import store, engine

MODEL = os.path.join(R, "examples", "checkout-widget.states.json")


def run(answers=None):
    m = store.load(MODEL)
    return engine.build(m, answers or {})


class T(unittest.TestCase):
    def test_deterministic(self):
        a = json.dumps(run(), sort_keys=True, default=str)
        b = json.dumps(run(), sort_keys=True, default=str)
        self.assertEqual(a, b, "движок обязан быть детерминированным")

    def test_env_slices(self):
        r = run()
        self.assertEqual(len(r["slices"]), 6, "3 viewport × 2 hostVersion")
        self.assertNotIn("viewport", r["param_order"])

    def test_forbid_removes(self):
        sl = run()["slices"][0]
        self.assertLess(sl["counts"]["valid"], sl["counts"]["total"])

    def test_v1_has_no_sbp(self):
        v1 = [s for s in run()["slices"] if s["env"]["hostVersion"] == "v1"][0]
        for row in v1["rows"]:
            self.assertNotEqual(row["values"]["payMethod"], "sbp",
                                "контракт v1 запрещает СБП")

    def test_answer_shrinks_matrix(self):
        before = run()["slices"][0]["counts"]["collapsed"]
        after = run({"constraints": {"c6": "proven"}})["slices"][0]["counts"]["collapsed"]
        self.assertLess(after, before, "подтверждённое правило обязано схлопнуть матрицу")

    def test_assumed_not_applied(self):
        q = run()["slices"][0]["questions"]
        self.assertTrue(any(x["id"] == "c6" for x in q), "assumed должен стать вопросом")

    def test_rule_overlap_detected(self):
        f = run()["slices"][0]["findings"]
        self.assertTrue(any(x["class"] == "RULE_OVERLAP" for x in f))

    def test_paths_from_initial(self):
        sl = run()["slices"][0]
        reachable = [r for r in sl["rows"] if r["reachable"]]
        self.assertTrue(all(isinstance(r["path"], list) for r in reachable))

    def test_validate_clean(self):
        p = subprocess.run([sys.executable, os.path.join(R, "scripts", "validate.py"), MODEL],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
