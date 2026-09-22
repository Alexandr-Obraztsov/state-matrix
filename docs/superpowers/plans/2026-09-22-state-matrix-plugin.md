# state-matrix Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить рабочий прототип в устанавливаемый плагин Claude Code без внешних зависимостей, с непустой корзиной семантик и отчётом только в чат.

**Architecture:** Плагин со скиллом и одним CLI (`sm.py`), который исполняет весь конвейер и отказывает при нарушении протокола. Модель — JSON, только стандартная библиотека. MCP-сервера нет: строгость обеспечивают скрипты, а не транспорт.

**Tech Stack:** Python 3 (только stdlib), Claude Code plugin format, unittest.

**Spec:** `docs/superpowers/specs/2026-09-22-state-matrix-plugin-design.md`

## Global Constraints

- Только стандартная библиотека Python 3. `import yaml` запрещён во всём плагине.
- Модели, каталог, ответы — JSON. Расширение моделей: `.states.json`.
- Потолок матрицы: **100 строк** после схлопывания.
- Все пути внутри плагина строятся от `${CLAUDE_PLUGIN_ROOT}` или от `__file__`.
- Любой отказ печатается в stderr словом `ОТКАЗ:` и завершает процесс кодом 2.
- Числа в отчёте берутся только из `result.json`; ни один скрипт не печатает число, которого не посчитал.

---

### Task 1: Перевод на JSON и удаление HTML

**Files:**
- Modify: `scripts/engine.py`, `scripts/validate.py`, `scripts/verify.py`, `scripts/report_md.py`, `scripts/sm.py`
- Delete: `report/report.html`, `scripts/serve.py`, `.claude/launch.json`
- Create: `scripts/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `store.load(path) -> dict`, `store.save(path, obj) -> None`, `store.CEILING = 100`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_store.py
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
        root = os.path.join(os.path.dirname(__file__), "..", "scripts")
        for f in os.listdir(root):
            if f.endswith(".py"):
                self.assertNotIn("import yaml", open(os.path.join(root, f), encoding="utf-8").read(), f)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_store -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/store.py
"""Чтение и запись моделей. Только stdlib: на чужой машине ничего не ставится."""
import json, os

CEILING = 100

def load(path):
    if not path or not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def save(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
```

- [ ] **Step 4: Заменить yaml во всех скриптах**

В `engine.py`, `validate.py`, `verify.py`, `report_md.py`, `sm.py`:
убрать `import yaml`, добавить `import store`, заменить `yaml.safe_load(open(p))` на `store.load(p)`,
`yaml.safe_dump(obj, open(p,"w"), allow_unicode=True)` на `store.save(p, obj)`.
В `engine.py` заменить константу `CEILING = 200` на `from store import CEILING`.

- [ ] **Step 5: Удалить HTML-ветку**

```bash
git rm -r --cached report .claude 2>/dev/null; rm -rf report scripts/serve.py .claude
```

- [ ] **Step 6: Run tests**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Модель в JSON, HTML-отчёт удалён"
```

---

### Task 2: Корзина из пятнадцати семантик

**Files:**
- Create: `catalog/default.json`
- Delete: `catalog/default.yaml`
- Test: `tests/test_catalog.py`

**Interfaces:**
- Produces: JSON-массив записей `{id, matches:{names,types}, questions:[{id,ask}], values, special, env_candidate?}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_catalog.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import store

CAT = os.path.join(os.path.dirname(__file__), "..", "catalog", "default.json")

class T(unittest.TestCase):
    def setUp(self):
        self.c = store.load(CAT)

    def test_fifteen_or_more(self):
        self.assertGreaterEqual(len(self.c), 15)

    def test_required_keys(self):
        for e in self.c:
            for k in ("id", "matches", "questions", "values"):
                self.assertIn(k, e, e.get("id"))
            self.assertTrue(e["questions"], f"{e['id']}: семантика без вопросов бесполезна")
            for q in e["questions"]:
                self.assertIn("id", q); self.assertIn("ask", q)
                self.assertTrue(q["ask"].endswith("?"), f"{e['id']}/{q['id']}: вопрос без знака вопроса")

    def test_ids_unique(self):
        ids = [e["id"] for e in self.c]
        self.assertEqual(len(ids), len(set(ids)))

    def test_key_semantics_present(self):
        ids = {e["id"] for e in self.c}
        for need in ("free_text", "number", "money_amount", "http_endpoint",
                     "error_state", "auth_role", "collection", "date_time"):
            self.assertIn(need, ids)

    def test_endpoint_asks_about_failures(self):
        ep = next(e for e in self.c if e["id"] == "http_endpoint")
        asks = " ".join(q["ask"] for q in ep["questions"]).lower()
        for word in ("таймаут", "пуст", "авториз"):
            self.assertIn(word, asks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_catalog -v`
Expected: FAIL — `default.json` отсутствует, `load` вернёт `{}`

- [ ] **Step 3: Написать каталог**

Пятнадцать записей. Полное содержимое — в спеке, раздел «Корзина семантик».
Образец одной записи, остальные по тому же шаблону:

```json
[
  {
    "id": "error_state",
    "matches": {"names": ["error", "err", "failure", "errorMessage"],
                "types": ["enum", "string", "object"]},
    "questions": [
      {"id": "where",   "ask": "где показывается ошибка — на месте поля, баннером или экраном целиком?"},
      {"id": "retry",   "ask": "есть ли повтор действия и сколько попыток?"},
      {"id": "text",    "ask": "текст приходит с бэкенда или свой на клиенте?"},
      {"id": "data",    "ask": "что происходит с уже введёнными данными при ошибке?"},
      {"id": "log",     "ask": "ошибка логируется или уходит в мониторинг?"}
    ],
    "values": ["none", "field", "banner", "fatal"],
    "special": ["unknown_code", "empty_message", "html_in_message"],
    "seen": []
  }
]
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_catalog -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add catalog tests/test_catalog.py && git rm -f catalog/default.yaml
git commit -m "Корзина: пятнадцать семантик с обязательными вопросами"
```

---

### Task 3: Потолок 100 с разбором вклада параметров

**Files:**
- Modify: `scripts/engine.py`
- Test: `tests/test_ceiling.py`

**Interfaces:**
- Consumes: `store.CEILING`
- Produces: в `result.json` поле `advice` вида
  `{"over": bool, "contributions": [{"param","factor","env_candidate","rows_if_env"}], "unruled": [str], "cheapest": [str]}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ceiling.py
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import engine

def model(nvals):
    p = {f"p{i}": {"values": [f"v{j}" for j in range(n)], "from": "x.ts:1"}
         for i, n in enumerate(nvals)}
    return {"system": "T", "params": p}

class T(unittest.TestCase):
    def test_under_ceiling_no_advice(self):
        r = engine.build(model([2, 2, 2]), {})           # 8 строк
        self.assertFalse(r["slices"][0]["advice"]["over"])

    def test_over_ceiling_flags(self):
        r = engine.build(model([4, 4, 4, 4]), {})        # 256 строк
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_ceiling -v`
Expected: FAIL — `KeyError: 'advice'`

- [ ] **Step 3: Implement**

```python
# scripts/engine.py — внутри build_slice, после подсчёта matrix
def advise(params, matrix_len, model, cons):
    changed = set()
    for t in (model.get("transitions") or []):
        changed |= set((t.get("set") or {}).keys())
    ruled = set()
    for c in cons:
        ruled |= set((c.get("forbid") or {}).keys())
        ruled |= set((c.get("when") or {}).keys())
        ruled |= set(c.get("irrelevant") or [])
    contrib = []
    for n, p in params.items():
        f = len(p["values"])
        contrib.append({"param": n, "factor": f,
                        "env_candidate": n not in changed and not p.get("env"),
                        "rows_if_env": matrix_len // f if f else matrix_len})
    contrib.sort(key=lambda c: (-c["factor"], c["param"]))
    cheapest = [f"пометить env: {c['param']} (×{c['factor']}) → {c['rows_if_env']} строк"
                for c in contrib if c["env_candidate"]][:3]
    return {"over": matrix_len > CEILING, "ceiling": CEILING,
            "contributions": contrib, "unruled": sorted(set(params) - ruled),
            "cheapest": cheapest}
```

В возвращаемый словарь среза добавить `"advice": advise(params, len(matrix), model, cons)`.
В блоке находок заменить текст `CEILING` на отчёт с советами:

```python
    if len(matrix) > CEILING:
        adv = advice
        lines = [f"{len(matrix)} строк при потолке {CEILING}"]
        lines += [f"  {c['param']:12} ×{c['factor']}"
                  + ("  env-кандидат → " + str(c["rows_if_env"]) + " строк"
                     if c["env_candidate"] else "  нет правил схлопывания")
                  for c in adv["contributions"]]
        if adv["cheapest"]:
            lines.append("дешевле всего: " + "; ".join(adv["cheapest"]))
        if adv["unruled"]:
            lines.append("без единого правила: " + ", ".join(adv["unruled"])
                         + " — проверь, влияют ли они на исход")
        findings.insert(0, {"class": "CEILING", "severity": "block",
                            "message": "\n".join(lines)})
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_ceiling -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/engine.py tests/test_ceiling.py
git commit -m "Потолок 100 строк с разбором вклада параметров"
```

---

### Task 4: Недостающие подкоманды sm.py

**Files:**
- Modify: `scripts/sm.py`
- Test: `tests/test_sm.py`

**Interfaces:**
- Produces подкоманды: `init`, `show`, `rows`, `answer`, `param rm`, `rule rm`, `state rm`, `transition add`, `catalog list`, `catalog new`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sm.py
import json, os, subprocess, sys, tempfile, unittest
ROOT = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(ROOT, "scripts", "sm.py")

def run(*a, expect=0):
    r = subprocess.run([sys.executable, SM, *a], capture_output=True, text=True)
    assert r.returncode == expect, f"код {r.returncode}, ждали {expect}\n{r.stdout}{r.stderr}"
    return r.stdout + r.stderr

class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.m = os.path.join(self.d, "X.states.json")
        run("init", self.m, "--system", "X", "--source", "a.ts", "--mode", "code")

    def test_init_creates_model(self):
        self.assertEqual(json.load(open(self.m))["system"], "X")

    def test_param_without_catalog_refused(self):
        out = run("param", "add", self.m, "--name", "n", "--type", "number",
                  "--values", "a", "--from", "a.ts:1", expect=2)
        self.assertIn("корзина", out)

    def test_param_without_answers_refused(self):
        run("catalog", self.m, "amount", "--type", "number")
        out = run("param", "add", self.m, "--name", "amount", "--type", "number",
                  "--values", "zero", "--from", "a.ts:1", expect=2)
        self.assertIn("нет ответов", out)

    def test_param_added_with_answers(self):
        run("catalog", self.m, "amount", "--type", "number")
        cat = [e for e in json.load(open(os.path.join(ROOT, "catalog", "default.json")))
               if e["id"] == "money_amount"][0]
        ans = [f"-a{q['id']}=неизвестно" for q in cat["questions"]]
        flat = []
        for x in ans:
            flat += ["-a", x[2:]]
        run("param", "add", self.m, "--name", "amount", "--type", "number",
            "--values", "zero", "typical", "--from", "a.ts:1", *flat)
        p = json.load(open(self.m))["params"]["amount"]
        self.assertEqual(len(p["answers"]), len(cat["questions"]))

    def test_rule_without_ref_needs_ask(self):
        out = run("rule", "add", self.m, "--id", "r1", "--forbid", "amount=zero",
                  "--evidence", "просто так", expect=2)
        self.assertIn("--ask", out)

    def test_state_without_evidence_refused(self):
        out = run("state", "add", self.m, "--name", "S", expect=2)
        self.assertIn("evidence", out)

    def test_show_prints_human_text(self):
        out = run("show", self.m)
        self.assertIn("X", out)

    def test_param_rm(self):
        run("catalog", self.m, "flag", "--type", "boolean")
        run("param", "add", self.m, "--name", "flag", "--type", "boolean",
            "--values", "true", "false", "--from", "a.ts:2", "-a", "default=true")
        run("param", "rm", self.m, "flag")
        self.assertNotIn("flag", json.load(open(self.m)).get("params", {}))

    def test_answer_writes_file(self):
        run("answer", self.m, "c1", "proven")
        ans = json.load(open(os.path.join(self.d, "answers.json")))
        self.assertEqual(ans["constraints"]["c1"], "proven")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_sm -v`
Expected: FAIL — нет подкоманды `init`

- [ ] **Step 3: Implement**

```python
# scripts/sm.py — добавить команды

def cmd_init(a):
    if os.path.exists(a.model) and not a.force:
        die(f"модель {a.model} уже есть", "перезаписать: --force")
    store.save(a.model, {"system": a.system, "source": a.source, "mode": a.mode,
                         "params": {}, "excluded": {}, "constraints": [],
                         "transitions": [], "states": []})
    print(f"модель заведена: {a.model}\nдальше: sm.py extract <цель>")

def cmd_show(a):
    m = store.load(a.model)
    print(f"{m.get('system','—')}  ({m.get('mode','code')})  {m.get('source','—')}")
    print(f"\nпараметры ({len(m.get('params') or {})}):")
    for n, p in (m.get("params") or {}).items():
        env = " [окружение]" if p.get("env") else ""
        print(f"  {n}{env}: {', '.join(map(str, p['values']))}")
        if p.get("desc"): print(f"      {p['desc']}")
        print(f"      источник: {p.get('from','—')}")
        miss = [k for k, v in (p.get("answers") or {}).items() if v == "неизвестно"]
        if miss: print(f"      без ответа: {', '.join(miss)}")
    if m.get("excluded"):
        print(f"\nисключено: " + ", ".join(m["excluded"]))
    print(f"\nправила ({len(m.get('constraints') or [])}):")
    for c in m.get("constraints") or []:
        print(f"  [{c.get('status')}] {c.get('id')}: {c.get('desc') or c.get('evidence')}")
    print(f"\nсостояния ({len(m.get('states') or [])}):")
    for s in m.get("states") or []:
        print(f"  {s['name']}: {s.get('when')}")

def cmd_rows(a):
    res = store.load(a.result)
    if not res: die(f"нет {a.result}", "сначала: sm.py build <модель>")
    sl = res["slices"][a.env]
    rows = sl["rows"]
    if a.no_state: rows = [r for r in rows if not r.get("state")]
    if a.status:   rows = [r for r in rows if r["status"] == a.status]
    print(f"{len(rows)} строк")
    for r in rows[:a.limit]:
        vv = ", ".join(f"{k}={v}" for k, v in r["values"].items() if v != "*")
        path = " · путь: " + " → ".join(p["event"] for p in (r.get("path") or [])) \
               if r.get("path") else ""
        print(f"  {r['id']}  {vv}{path}")

def cmd_answer(a):
    p = os.path.join(os.path.dirname(a.model) or ".", "answers.json")
    cur = store.load(p) or {"constraints": {}, "outcomes": {}}
    cur.setdefault(a.section, {})[a.id] = a.value
    store.save(p, cur)
    print(f"{a.section}.{a.id} = {a.value} → {p}")
```

Плюс `param rm`, `rule rm`, `state rm`, `transition add`, `catalog list`, `catalog new` —
каждая читает модель через `store.load`, меняет и пишет `store.save`, печатая одну строку итога.
Регистрация в `argparse` по образцу существующих подкоманд.

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest tests.test_sm -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/sm.py tests/test_sm.py
git commit -m "sm.py: init, show, rows, answer, удаление сущностей, каталог"
```

---

### Task 5: Долговечная проверка протокола в validate.py

**Files:**
- Modify: `scripts/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `catalog/default.json`, `.states/catalog.json`
- Produces: ошибка `params.<имя>: нет ответа на вопрос «<id>» семантики <catalog>`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate.py
import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import validate, store

def m(**kw):
    base = {"system": "T", "source": "a.ts", "params": {}, "constraints": []}
    base.update(kw); return base

class T(unittest.TestCase):
    def check(self, model):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.states.json"); store.save(p, model)
            return validate.check(p)

    def test_param_without_answers_is_error(self):
        e, w = self.check(m(params={"amount": {"type": "number", "catalog": "money_amount",
                                               "values": ["zero"], "from": "a.ts:1"}}))
        self.assertTrue(any("ответа" in x for x in e), e)

    def test_param_with_all_answers_ok(self):
        cat = store.load(os.path.join(os.path.dirname(__file__), "..", "catalog", "default.json"))
        qs = next(c for c in cat if c["id"] == "money_amount")["questions"]
        e, w = self.check(m(params={"amount": {
            "type": "number", "catalog": "money_amount", "values": ["zero"],
            "from": "a.ts:1", "answers": {q["id"]: "неизвестно" for q in qs}}}))
        self.assertEqual([x for x in e if "ответа" in x], [])

    def test_param_without_catalog_still_needs_from(self):
        e, w = self.check(m(params={"x": {"type": "enum", "values": ["a"], "answers": {}}}))
        self.assertTrue(any("from" in x for x in e))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_validate -v`
Expected: FAIL — проверки ответов нет

- [ ] **Step 3: Implement**

```python
# scripts/validate.py — внутри check(), в цикле по параметрам
    cat = {c["id"]: c for c in store.load(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "catalog", "default.json"))}
    local = store.load(os.path.join(os.path.dirname(path), "..", "catalog.json"))
    for c in (local or []):
        cat[c["id"]] = c

    for n, p in P.items():
        cid = p.get("catalog")
        if cid and cid in cat:
            ans = p.get("answers") or {}
            for q in cat[cid]["questions"]:
                if q["id"] not in ans:
                    errs.append(f"{n}: нет ответа на вопрос «{q['id']}» семантики {cid} "
                                f"— параметр добавлен в обход sm.py")
```

- [ ] **Step 4: Run tests**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/validate.py tests/test_validate.py
git commit -m "validate: ответы на вопросы семантики обязательны"
```

---

### Task 6: Упаковка плагина

**Files:**
- Create: `.claude-plugin/marketplace.json`, `commands/states.md`, `commands/states-check.md`, `skills/state-matrix/references/catalog.md`, `skills/state-matrix/references/findings.md`, `README.md`, `.gitignore`
- Modify: `.claude-plugin/plugin.json`, `skills/state-matrix/SKILL.md`
- Test: `tests/test_package.py`

**Interfaces:**
- Produces: устанавливаемый плагин; точка входа — скилл `state-matrix`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_package.py
import json, os, re, unittest
R = os.path.join(os.path.dirname(__file__), "..")

class T(unittest.TestCase):
    def test_manifest(self):
        m = json.load(open(os.path.join(R, ".claude-plugin", "plugin.json")))
        for k in ("name", "version", "description"):
            self.assertIn(k, m)
        self.assertRegex(m["name"], r"^[a-z0-9-]+$")

    def test_marketplace(self):
        m = json.load(open(os.path.join(R, ".claude-plugin", "marketplace.json")))
        self.assertTrue(m["plugins"])
        self.assertEqual(m["plugins"][0]["name"], "state-matrix")

    def test_skill_frontmatter(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        self.assertTrue(s.startswith("---"))
        head = s.split("---")[1]
        self.assertIn("name: state-matrix", head)
        self.assertIn("description:", head)

    def test_skill_mentions_pipeline_order(self):
        s = open(os.path.join(R, "skills", "state-matrix", "SKILL.md"), encoding="utf-8").read()
        for step in ("extract", "sm.py catalog", "param add", "rule add", "state add", "build"):
            self.assertIn(step, s)

    def test_commands_exist(self):
        for c in ("states.md", "states-check.md"):
            self.assertTrue(os.path.exists(os.path.join(R, "commands", c)))

    def test_no_report_html_left(self):
        self.assertFalse(os.path.exists(os.path.join(R, "report")))
        self.assertFalse(os.path.exists(os.path.join(R, "scripts", "serve.py")))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_package -v`
Expected: FAIL — нет `marketplace.json`

- [ ] **Step 3: Написать манифесты**

```json
// .claude-plugin/marketplace.json
{
  "name": "state-matrix",
  "owner": {"name": "obraztsov"},
  "metadata": {"description": "Матрица состояний: все комбинации входов и их исходы"},
  "plugins": [{
    "name": "state-matrix",
    "source": "./",
    "description": "Поднимает все состояния системы по коду или спеке, считает достижимость и показывает комбинации, о которых никто не подумал",
    "version": "1.0.0",
    "category": "testing",
    "tags": ["testing", "coverage", "state-machine", "spec-review"]
  }]
}
```

- [ ] **Step 4: Написать SKILL.md с конвейером**

Обязательные разделы: железное правило (числа только из движка), обязательный
конвейер с точными командами, правила отказа, когда отказываться от задачи,
классы находок. Описание в frontmatter должно срабатывать на «составь матрицу
состояний», «разбери все состояния по спеке», «какие случаи не покрыты».

- [ ] **Step 5: Run tests**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "Упаковка: манифесты, команды, скилл, README"
```

---

### Task 7: Сквозная проверка на живом коде

**Files:**
- Create: `examples/CommentComposer.states.json`, `tests/test_e2e.py`
- Delete: `.states/models/CommentComposer.states.yaml`, `examples/checkout-widget.states.yaml`

**Interfaces:**
- Consumes: всё предыдущее

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e2e.py
import json, os, subprocess, sys, tempfile, unittest
R = os.path.join(os.path.dirname(__file__), "..")
SM = os.path.join(R, "scripts", "sm.py")
MODEL = os.path.join(R, "examples", "CommentComposer.states.json")

class T(unittest.TestCase):
    def test_example_builds(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            r = subprocess.run([sys.executable, os.path.join(R, "scripts", "engine.py"),
                                MODEL, "-o", out], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            res = json.load(open(out))
            sl = res["slices"][0]
            self.assertLessEqual(sl["counts"]["collapsed"], 100)
            self.assertFalse(sl["advice"]["over"])

    def test_example_validates(self):
        r = subprocess.run([sys.executable, os.path.join(R, "scripts", "validate.py"), MODEL],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_report_prints_all_sections(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            subprocess.run([sys.executable, os.path.join(R, "scripts", "engine.py"),
                            MODEL, "-o", out], capture_output=True)
            md = subprocess.run([sys.executable, os.path.join(R, "scripts", "report_md.py"), out],
                                capture_output=True, text=True).stdout
            for sec in ("## Параметры", "## Правила", "## Состояния", "## Матрица"):
                self.assertIn(sec, md)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_e2e -v`
Expected: FAIL — нет `examples/CommentComposer.states.json`

- [ ] **Step 3: Пересобрать эталон через тулы**

Пройти конвейер целиком на `review-graph/src/components/CommentComposer.tsx`:
`extract` → `catalog` по каждому кандидату → `param add` с ответами →
`exclude` для шести не-параметров → `rule add` ×3 → `transition add` ×10 →
`state add` ×4 → `build`. Результат сохранить как `examples/CommentComposer.states.json`.

- [ ] **Step 4: Run all tests**

Run: `python3 -m unittest discover -s tests -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Эталонная модель, собранная через тулы, и сквозные тесты"
```
