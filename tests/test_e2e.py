"""Сквозной прогон на примере из репозитория."""
import json, os, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(__file__), "..")
SC = os.path.join(R, "scripts")
MODEL = os.path.join(R, "examples", "Checkout.states.json")


def run(*a):
    return subprocess.run([sys.executable, *a], capture_output=True, text=True)


class T(unittest.TestCase):
    def test_example_validates(self):
        r = run(os.path.join(SC, "validate.py"), MODEL, "--root", R)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_example_builds_and_prints_matrix(self):
        r = run(os.path.join(SC, "sm.py"), "--root", R, "build", MODEL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for sec in ("СОСТОЯНИЯ", "МАТРИЦА", "ВНЕ МАТРИЦЫ"):
            self.assertIn(sec, r.stdout)

    def test_example_under_ceiling_and_fully_covered(self):
        sys.path.insert(0, SC)
        import store, engine
        res = engine.build(store.load(MODEL))
        self.assertLessEqual(res["counts"]["collapsed"], res["ceiling"])
        self.assertEqual(res["counts"]["no_state"], 0, "все строки должны получить состояние")
        self.assertGreaterEqual(len(res["states"]), 4)

    def test_fake_reference_caught(self):
        sys.path.insert(0, SC)
        import store
        m = store.load(MODEL)
        m["constraints"][0]["evidence"] = "examples/checkout-spec.md:§99"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lie.states.json")
            store.save(p, m)
            r = run(os.path.join(SC, "validate.py"), p, "--root", R)
            self.assertEqual(r.returncode, 1)
            self.assertIn("выдумана", r.stdout)

    def test_no_removed_scripts(self):
        for gone in ("verify.py", "report_md.py", "extract.py"):
            self.assertFalse(os.path.exists(os.path.join(SC, gone)), gone)
