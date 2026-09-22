import json, os, unittest

R = os.path.join(os.path.dirname(__file__), "..")


class T(unittest.TestCase):
    def test_manifest(self):
        m = json.load(open(os.path.join(R, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        for k in ("name", "version", "description"):
            self.assertIn(k, m)
        self.assertRegex(m["name"], r"^[a-z0-9-]+$")

    def test_marketplace(self):
        m = json.load(open(os.path.join(R, ".claude-plugin", "marketplace.json"), encoding="utf-8"))
        self.assertTrue(m["plugins"])
        self.assertEqual(m["plugins"][0]["name"], "state-matrix")
        self.assertEqual(m["plugins"][0]["source"], "./")

    def test_skill_frontmatter(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        self.assertTrue(s.startswith("---"))
        head = s.split("---")[1]
        self.assertIn("name: state-matrix", head)
        self.assertIn("description:", head)

    def test_skill_mentions_pipeline_order(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        for step in ("sm_init", "sm_param_add", "sm_params", "sm_param_values",
                     "sm_state_add", "sm_states", "sm_rule_add", "sm_build"):
            self.assertIn(step, s)

    def test_skill_states_the_ceiling(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("100", s)

    def test_commands_exist(self):
        for c in ("states.md", "states-check.md"):
            p = os.path.join(R, "commands", c)
            self.assertTrue(os.path.exists(p), c)
            self.assertTrue(open(p, encoding="utf-8").read().startswith("---"), c)

    def test_skill_states_the_gates(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        for g in ("Ворота 1", "Ворота 2", "Ворота 3", "Ворота 4"):
            self.assertIn(g, s)

    def test_skill_forbids_inventing(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("Ничего не выдумывать", s)

    def test_no_catalog_left(self):
        self.assertFalse(os.path.exists(os.path.join(R, "catalog")),
                         "корзина параметров удалена")
        self.assertFalse(os.path.exists(os.path.join(R, "scripts", "report_md.py")),
                         "md-отчёта больше нет: всё в чате")

    def test_references_exist(self):
        for f in ("findings.md",):
            self.assertTrue(os.path.exists(
                os.path.join(R, "skills", "state-matrix", "references", f)), f)

    def test_mcp_declared(self):
        c = json.load(open(os.path.join(R, ".mcp.json"), encoding="utf-8"))
        self.assertIn("state-matrix", c)
        self.assertEqual(c["state-matrix"]["command"], "python3")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", " ".join(c["state-matrix"]["args"]))

    def test_no_report_html_left(self):
        self.assertFalse(os.path.exists(os.path.join(R, "report")))
        self.assertFalse(os.path.exists(os.path.join(R, "scripts", "serve.py")))

    def test_readme_shows_install(self):
        s = open(os.path.join(R, "README.md"), encoding="utf-8").read()
        self.assertIn("/plugin marketplace add", s)

    def test_skill_requires_showing_tool_output(self):
        """Пользователь не видит вывод тулов — агент обязан вставлять его в чат."""
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("не видит", s.lower())
        self.assertIn("целиком", s)

    def test_gate_tools_say_output_is_invisible(self):
        s = open(os.path.join(R, "scripts", "mcp_server.py"), encoding="utf-8").read()
        for t in ("sm_params", "sm_states", "sm_show", "sm_build"):
            i = s.index(f'tool("{t}"')
            self.assertIn("НЕ ВИДИТ", s[i:i + 900], t)
