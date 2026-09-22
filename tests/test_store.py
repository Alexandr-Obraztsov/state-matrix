import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store


class T(unittest.TestCase):
    def test_roundtrip_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.states.json")
            store.save(p, {"system": "Тест", "params": {"a": {"values": [1, 2]}}})
            self.assertEqual(store.load(p)["system"], "Тест")

    def test_missing_returns_empty(self):
        self.assertEqual(store.load("/nope/x.json"), {})

    def test_readable_on_disk(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            store.save(p, {"system": "Тест"})
            self.assertIn("Тест", open(p, encoding="utf-8").read())

    def test_no_yaml_anywhere(self):
        """Любая форма импорта yaml — нарушение требования «только stdlib»."""
        import re
        pat = re.compile(r"^\s*(import\s+.*\byaml\b|from\s+yaml\b)", re.M)
        root = os.path.join(os.path.dirname(__file__), "..", "scripts")
        for f in os.listdir(root):
            if f.endswith(".py"):
                src = open(os.path.join(root, f), encoding="utf-8").read()
                self.assertIsNone(pat.search(src), f"{f}: импортирует yaml")
