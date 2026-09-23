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
        for step in ("sm_init", "sm_param_add", "sm_state_add", "sm_build",
                     "sm_assign", "sm_exclude"):
            self.assertIn(step, s)

    def test_skill_states_the_ceiling(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("100", s)

    def test_commands_exist(self):
        for c in ("states.md", "states-check.md"):
            p = os.path.join(R, "commands", c)
            self.assertTrue(os.path.exists(p), c)
            self.assertTrue(open(p, encoding="utf-8").read().startswith("---"), c)

    def test_skill_shows_step_indicator(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        for g in ("Шаг 1 из 4", "Шаг 2 из 4", "Шаг 3 из 4", "Шаг 4 из 4"):
            self.assertIn(g, s)

    def test_skill_requires_answer_options(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("с вариантами ответа", s)
        self.assertGreaterEqual(s.count("Вопрос вариантами"), 3,
                                "нужны примеры вопросов с вариантами")

    def test_skill_forbids_code_fences_for_content(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("Без кодовых блоков", s)
        body = s.split("## Как разговаривать")[1]
        self.assertNotIn("```", body, "примеры не должны быть в кодовых блоках")

    def test_skill_reviews_one_by_one(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("Параметры — по одному", s)
        self.assertIn("Правила — по одному", s)

    def test_skill_forbids_inventing(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("Ничего не выдумывать", s)

    def test_no_catalog_left(self):
        self.assertFalse(os.path.exists(os.path.join(R, "catalog")),
                         "корзина параметров удалена")
        self.assertFalse(os.path.exists(os.path.join(R, "scripts", "report_md.py")),
                         "md-отчёта больше нет: всё в чате")

    def test_skill_hides_internals(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertNotIn("RULE_OVERLAP", s)
        self.assertIn("Не грузи внутренностями", s)

    def test_skill_traces_endpoints_to_sources(self):
        """Параметры ручек разматываются до источника — главный способ не упустить вход."""
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("Где искать", s)
        self.assertIn("откуда берётся", s)
        for src in ("навигация", "сессия", "окружение", "время", "параметры ручек"):
            self.assertIn(src, s)

    def test_skill_requires_knowledge_before_each_param(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        self.assertIn("Перед каждым параметром — база знаний", s)
        self.assertIn("обязательный шаг", s)
        m = open(os.path.join(R, "scripts", "mcp_server.py"), encoding="utf-8").read()
        i = m.index('tool("sm_param_add"')
        self.assertIn("sm_cases", m[i:i + 600])

    def test_knowledge_base_shipped(self):
        self.assertTrue(os.path.exists(os.path.join(R, "knowledge", "base.json")))

    def test_skill_points_at_knowledge_base(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"),
                 encoding="utf-8").read()
        self.assertIn("sm_cases", s)
        self.assertIn("sm_learn", s)
        self.assertIn("sm_cases", s)

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
        for t in ("sm_build",):
            i = s.index(f'tool("{t}"')
            self.assertIn("НЕ ВИДИТ", s[i:i + 900], t)
