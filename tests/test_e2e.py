import json, os, subprocess, sys, tempfile, unittest

R = os.path.join(os.path.dirname(__file__), "..")
SC = os.path.join(R, "scripts")
EXAMPLES = [os.path.join(R, "examples", f) for f in os.listdir(os.path.join(R, "examples"))
            if f.endswith(".states.json")]


def build(model, out):
    return subprocess.run([sys.executable, os.path.join(SC, "engine.py"), model, "-o", out],
                          capture_output=True, text=True)


class T(unittest.TestCase):
    def test_every_example_validates(self):
        for m in EXAMPLES:
            r = subprocess.run([sys.executable, os.path.join(SC, "validate.py"), m],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{os.path.basename(m)}:\n{r.stdout}")

    def test_every_example_under_ceiling(self):
        with tempfile.TemporaryDirectory() as d:
            for m in EXAMPLES:
                out = os.path.join(d, "r.json")
                self.assertEqual(build(m, out).returncode, 0)
                for sl in json.load(open(out, encoding="utf-8"))["slices"]:
                    self.assertLessEqual(sl["counts"]["collapsed"], 100,
                                         os.path.basename(m))
                    self.assertFalse(sl["advice"]["over"])

    def test_build_prints_matrix_to_chat(self):
        """Отчёта-файла нет: sm build печатает всё в поток, агент отдаёт это в чат."""
        spec = os.path.join(R, "examples", "Checkout.states.json")
        r = subprocess.run([sys.executable, os.path.join(SC, "sm.py"), "build", spec,
                            "--root", R], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        for sec in ("СОСТОЯНИЯ", "МАТРИЦА", "ВНЕ МАТРИЦЫ"):
            self.assertIn(sec, r.stdout)

    def test_no_parser_left(self):
        self.assertFalse(os.path.exists(os.path.join(SC, "extract.py")),
                         "парсер кода удалён: инструмент работает только со спеками")

    def test_spec_example_has_named_states(self):
        spec = os.path.join(R, "examples", "Checkout.states.json")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            build(spec, out)
            sl = json.load(open(out, encoding="utf-8"))["slices"][0]
            self.assertEqual(sl["no_state"], 0, "все строки должны получить состояние")
            self.assertGreaterEqual(len(sl["states"]), 5)

    def test_fake_section_reference_caught(self):
        spec = os.path.join(R, "examples", "Checkout.states.json")
        m = json.load(open(spec, encoding="utf-8"))
        m["constraints"][0]["evidence"] = "examples/checkout-spec.md:§99 — выдумка"
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "lie.states.json")
            json.dump(m, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            r = subprocess.run([sys.executable, os.path.join(SC, "verify.py"), p,
                                "--root", R], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("выдумана", r.stdout + r.stderr)
