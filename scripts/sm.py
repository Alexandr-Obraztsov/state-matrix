#!/usr/bin/env python3
"""Единственный способ изменить модель. Агент не редактирует YAML руками:
он вызывает эти команды, и каждая отказывает, если протокол нарушен.

Протокол добавления параметра:
  1. sm.py catalog <модель> <имя> --type <тип>      ← ОБЯЗАТЕЛЬНО первым
  2. ответить на все вопросы семантики
  3. sm.py param add ... -a q=ответ ...             ← иначе отказ
"""
import os, sys, json, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CATALOG = os.path.join(ROOT, "catalog", "default.json")


def die(msg, hint=""):
    print(f"ОТКАЗ: {msg}", file=sys.stderr)
    if hint:
        print(f"  {hint}", file=sys.stderr)
    sys.exit(2)


def load_model(p):
    if not os.path.exists(p):
        return {}
    return store.load(p) or {}


def save_model(p, m):
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    store.save(p, m)


def ledger_path(model):
    d = os.path.join(os.path.dirname(model) or ".", ".session")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, os.path.basename(model) + ".json")


def ledger(model):
    p = ledger_path(model)
    return json.load(open(p)) if os.path.exists(p) else {"lookups": {}}


def save_ledger(model, L):
    json.dump(L, open(ledger_path(model), "w"), ensure_ascii=False, indent=1)


def project_catalog(model_path):
    """Проектная корзина лежит рядом с .states/, на уровень выше models/."""
    return os.path.normpath(os.path.join(
        os.path.dirname(model_path) or ".", "..", "catalog.json"))


def merge_entry(base, patch):
    """Проектная запись ДОПОЛНЯЕТ дефолтную, а не заменяет её: вопросы и имена
    добавляются, значения и описание перекрываются, если заданы."""
    out = json.loads(json.dumps(base))
    seen = {q["id"] for q in out.get("questions", [])}
    for q in patch.get("questions") or []:
        if q["id"] not in seen:
            out.setdefault("questions", []).append(q)
            seen.add(q["id"])
    m = out.setdefault("matches", {})
    for key in ("names", "types"):
        have = m.get(key) or []
        for x in (patch.get("matches") or {}).get(key) or []:
            if x not in have:
                have.append(x)
        m[key] = have
    for key in ("title", "desc", "env_candidate"):
        if patch.get(key):
            out[key] = patch[key]
    for key in ("values", "special"):
        have = out.get(key) or []
        for x in patch.get(key) or []:
            if x not in have:
                have.append(x)
        if have:
            out[key] = have
    return out


def catalogs(project_dir):
    """Дефолтная корзина, дополненная проектной. Проектная ищется рядом с моделью
    и на уровень выше (обычный случай — .states/catalog.json)."""
    base = {e["id"]: e for e in (store.load(DEFAULT_CATALOG) or [])}
    order = list(base)
    for cand in (os.path.join(project_dir, "..", "catalog.json"),
                 os.path.join(project_dir, "catalog.json")):
        for e in (store.load(cand) or []):
            if e["id"] in base:
                base[e["id"]] = merge_entry(base[e["id"]], e)
            else:
                base[e["id"]] = e
                order.append(e["id"])
    return [base[i] for i in order]


def find(cat, name, type_):
    exact, loose = [], []
    for c in cat:
        m = c.get("matches") or {}
        if name in (m.get("names") or []):
            exact.append(c)
        elif type_ and type_ in (m.get("types") or []):
            loose.append(c)
    return exact, loose


# ---------- команды ----------

def cmd_init(a):
    if os.path.exists(a.model) and not a.force:
        die(f"модель {a.model} уже есть", "перезаписать: --force")
    store.save(a.model, {"system": a.system, "source": a.source,
                         "params": {}, "excluded": {}, "constraints": [],
                         "transitions": [], "states": []})
    print(f"модель заведена: {a.model}")
    print(f"дальше: прочитай {a.source}, выпиши входные параметры;"
          " по каждому сначала catalog, потом param add")


def cmd_show(a):
    m = store.load(a.model)
    if not m:
        die(f"нет модели {a.model}", "завести: sm.py init <модель> --system … --source …")
    print(f"{m.get('system','—')}  {m.get('source','—')}")
    P = m.get("params") or {}
    print(f"\nпараметры ({len(P)}):")
    for n, p in P.items():
        env = "  [окружение]" if p.get("env") else ""
        cat = f"  ←{p['catalog']}" if p.get("catalog") else ""
        print(f"  {n}{env}{cat}")
        av = p.get("all_values") or p["values"]
        if len(av) != len(p["values"]):
            print(f"      все значения ({len(av)}): {', '.join(map(str, av))}")
            print(f"      классы ({len(p['values'])}): {', '.join(map(str, p['values']))}")
            print(f"      объединены: {p.get('grouping', '— без объяснения —')}")
        else:
            print(f"      значения: {', '.join(map(str, p['values']))}")
        if p.get("special"):
            print(f"      вне матрицы: {', '.join(map(str, p['special']))}")
        if p.get("desc"):
            print(f"      {p['desc']}")
        print(f"      источник: {p.get('from','—')}")
        unk = [k for k, v in (p.get("answers") or {}).items() if str(v).lower() == "неизвестно"]
        if unk:
            print(f"      ответ «неизвестно»: {', '.join(unk)}")
    if m.get("excluded"):
        print(f"\nисключено ({len(m['excluded'])}): " + ", ".join(m["excluded"]))
    C = m.get("constraints") or []
    print(f"\nправила ({len(C)}):")
    for c in C:
        kind = "запрет" if "forbid" in c else "схлопывание"
        print(f"  [{c.get('status','?'):7}] {c.get('id')}  {kind}: {c.get('desc') or c.get('evidence')}")
    T = m.get("transitions") or []
    print(f"\nпереходы ({len(T)}):")
    for t in T:
        w = ", ".join(f"{k}={v}" for k, v in (t.get("when") or {}).items()) or "из любого"
        st = ", ".join(f"{k}→{v}" for k, v in t["set"].items())
        print(f"  {t['event']}: когда {w} → {st}")
    S = m.get("states") or []
    print(f"\nсостояния ({len(S)}):")
    for x in S:
        w = ", ".join(f"{k}={v}" for k, v in (x.get("when") or {}).items()) or "всегда"
        print(f"  {x['name']}: {w}")


def cmd_rows(a):
    res = store.load(a.result)
    if not res:
        die(f"нет {a.result}", "сначала: sm.py build <модель>")
    sl = res["slices"][a.env]
    rows = sl["rows"]
    if a.no_state:
        rows = [r for r in rows if not r.get("state")]
    if a.status:
        rows = [r for r in rows if r["status"] == a.status]
    print(f"{len(rows)} строк из {len(sl['rows'])}")
    for r in rows[:a.limit]:
        vv = ", ".join(f"{k}={v}" for k, v in r["values"].items() if v != "*")
        path = (" · путь: " + " → ".join(p["event"] for p in r["path"])) if r.get("path") else ""
        st = f"  [{r['state']}]" if r.get("state") else "  [без состояния]"
        print(f"  {r['id']}{st}  {vv}{path}")


def cmd_answer(a):
    p = os.path.join(os.path.dirname(a.model) or ".", "answers.json")
    cur = store.load(p) or {}
    cur.setdefault(a.section, {})[a.id] = a.value
    store.save(p, cur)
    print(f"{a.section}.{a.id} = {a.value} → {p}")


def cmd_param_rm(a):
    m = store.load(a.model)
    if a.name not in (m.get("params") or {}):
        die(f"параметра «{a.name}» нет в модели")
    del m["params"][a.name]
    for c in list(m.get("constraints") or []):
        used = set((c.get("forbid") or {})) | set((c.get("when") or {})) | set(c.get("irrelevant") or [])
        if a.name in used:
            m["constraints"].remove(c)
            print(f"  заодно убрано правило {c.get('id')} — ссылалось на параметр")
    print(f"параметр «{a.name}» убран")
    store.save(a.model, m)


def cmd_rule_rm(a):
    m = store.load(a.model)
    before = len(m.get("constraints") or [])
    m["constraints"] = [c for c in (m.get("constraints") or []) if c.get("id") != a.id]
    if len(m["constraints"]) == before:
        die(f"правила «{a.id}» нет")
    store.save(a.model, m)
    print(f"правило «{a.id}» убрано")


def cmd_state_rm(a):
    m = store.load(a.model)
    before = len(m.get("states") or [])
    m["states"] = [s for s in (m.get("states") or []) if s.get("name") != a.name]
    if len(m["states"]) == before:
        die(f"состояния «{a.name}» нет")
    store.save(a.model, m)
    print(f"состояние «{a.name}» убрано")


def cmd_transition_add(a):
    m = store.load(a.model)
    P = m.get("params") or {}
    def parse(pairs, allow_bang=False):
        d = {}
        for x in pairs or []:
            k, v = x.split("=", 1)
            if k not in P:
                die(f"неизвестный параметр «{k}»")
            if not (allow_bang and v.startswith("!")):
                for z in v.split(","):
                    if z not in [str(y) for y in P[k]["values"]]:
                        die(f"значение «{z}» отсутствует в {k}.values")
            vals = v.split(",")
            d[k] = vals if len(vals) > 1 else vals[0]
        return d
    if not a.evidence:
        die("нет --evidence", "переход должен ссылаться на код или спеку")
    if not a.set:
        die("нет --set", "переход обязан что-то менять")
    t = {"event": a.event, "when": parse(a.when), "set": parse(a.set, allow_bang=True),
         "evidence": a.evidence}
    m.setdefault("transitions", []).append(t)
    store.save(a.model, m)
    print(f"переход «{a.event}» добавлен")


def cmd_catalog_list(a):
    """Только название и описание. Вопросы — через catalog-get по конкретному типу."""
    cat = catalogs(os.path.dirname(a.model or ".") or ".")
    if a.type:
        cat = [c for c in cat if a.type in (c.get("matches") or {}).get("types", [])]
    print(f"{len(cat)} типов параметров"
          + (f" с типом «{a.type}»" if a.type else "") + ":\n")
    for c in cat:
        env = "  [окружение]" if c.get("env_candidate") else ""
        print(f"  {c['id']:18} {c.get('title', '—')}{env}")
        print(f"  {'':18} {c.get('desc', '')}")
        print()
    print("вопросы конкретного типа: sm.py catalog-get <модель> <id>")


def cmd_catalog_get(a):
    """Полная карточка типа: вопросы, значения, спецзначения, имена."""
    cat = {c["id"]: c for c in catalogs(os.path.dirname(a.model) or ".")}
    c = cat.get(a.id)
    if not c:
        die(f"типа «{a.id}» в корзине нет",
            "посмотреть все: sm.py catalog-list; завести: sm.py catalog-new")
    print(f"{c['id']} — {c.get('title','—')}")
    print(f"  {c.get('desc','')}\n")
    print(f"ВОПРОСЫ ({len(c['questions'])}) — задавай ПО ОДНОМУ, с вариантами:")
    for q in c["questions"]:
        print(f"  {q['id']}: {q['ask']}")
        if q.get("options"):
            print(f"      варианты: {' | '.join(q['options'])}")
    print(f"\n  значения по умолчанию : {', '.join(map(str, c.get('values', [])))}")
    print(f"  вне матрицы           : {', '.join(map(str, c.get('special', []))) or '—'}")
    print(f"  типичные имена        : {', '.join((c.get('matches') or {}).get('names', [])) or '—'}")
    for sn in (c.get("seen") or [])[-2:]:
        print(f"  раньше здесь          : {sn.get('where')} → {sn.get('values')}")


def cmd_catalog_edit(a):
    """Дополнить тип: новые вопросы, имена, значения. Правка ложится в проектную
    корзину и не трогает дефолтную — обновление плагина её не затрёт."""
    p = project_catalog(a.model)
    cur = store.load(p) or []
    base = {c["id"]: c for c in catalogs(os.path.dirname(a.model) or ".")}
    if a.id not in base:
        die(f"типа «{a.id}» в корзине нет", "завести новый: sm.py catalog-new")
    entry = next((e for e in cur if e["id"] == a.id), None)
    if entry is None:
        entry = {"id": a.id}
        cur.append(entry)
    added = []
    for q in a.add_questions or []:
        qid, ask = q.split("=", 1)
        opts = None
        if "|" in ask:
            ask, _, rest = ask.partition("|")
            ask = ask.strip()
            opts = [x.strip() for x in rest.split("|") if x.strip()]
        if not ask.endswith("?"):
            die(f"вопрос «{qid}» не заканчивается знаком вопроса",
                "вопрос должен быть вопросом, иначе на него не отвечают")
        if any(x["id"] == qid for x in base[a.id].get("questions", [])):
            die(f"вопрос «{qid}» у типа «{a.id}» уже есть")
        nq = {"id": qid, "ask": ask,
              "options": (opts or []) + ["в спеке не сказано"]}
        entry.setdefault("questions", []).append(nq)
        added.append(qid)
    for key, val in (("names", a.add_names), ("values", a.add_values),
                     ("special", a.add_special)):
        if val:
            if key == "names":
                entry.setdefault("matches", {}).setdefault("names", []).extend(val)
            else:
                entry.setdefault(key, []).extend(val)
            added.append(f"{key}: {', '.join(val)}")
    if a.desc:
        entry["desc"] = a.desc
        added.append("описание")
    if not added:
        die("нечего добавлять", "укажи --add-questions, --add-names, --add-values,"
            " --add-special или --desc")
    store.save(p, cur)
    print(f"тип «{a.id}» дополнен: {'; '.join(added)}")
    print(f"правка в {p} — при следующем разборе вопросы зададутся автоматически")


def cmd_catalog_new(a):
    if not a.title or not a.desc:
        die("нужны --title и --desc",
            "без названия и описания тип нельзя выбрать из списка")
    p = project_catalog(a.model)
    cur = store.load(p) or []
    if any(c["id"] == a.id for c in cur):
        die(f"семантика «{a.id}» уже есть в проектном каталоге")
    qs = []
    for q in a.questions or []:
        qid, ask = q.split("=", 1)
        opts = None
        if "|" in ask:
            ask, _, rest = ask.partition("|")
            ask = ask.strip()
            opts = [x.strip() for x in rest.split("|") if x.strip()]
        if not ask.endswith("?"):
            die(f"вопрос «{qid}» не заканчивается знаком вопроса",
                "вопрос должен быть вопросом, иначе на него не отвечают")
        qs.append({"id": qid, "ask": ask,
                   "options": (opts or []) + ["в спеке не сказано"]})
    if not qs:
        die("нет --questions", "семантика без вопросов бесполезна")
    cur.append({"id": a.id, "title": a.title, "desc": a.desc,
                "matches": {"names": a.names or [], "types": [a.type]},
                "questions": qs, "values": a.values or [], "special": a.special or [],
                "seen": []})
    store.save(p, cur)
    print(f"тип «{a.id}» ({a.title}) добавлен в {p}: {len(qs)} вопросов")



def cmd_catalog(a):
    if not a.model or not a.name:
        die("нужны модель и имя параметра",
            "sm.py catalog <модель> <имя> --type <тип>, либо sm.py catalog list")
    if not a.type:
        die("нет --type", "тип определяется по тому, что с параметром делают")
    cat = catalogs(os.path.dirname(a.model) or ".")
    exact, loose = find(cat, a.name, a.type)
    L = ledger(a.model)
    hit = exact[0] if exact else None

    print(f"# корзина для «{a.name}» (тип {a.type})")
    if exact:
        print(f"\nТОЧНОЕ СОВПАДЕНИЕ ПО ИМЕНИ: {hit['id']}")
    elif loose:
        print(f"\nПО ИМЕНИ НЕ НАШЛОСЬ. Подходят по типу «{a.type}» — ВЫБЕРИ САМ:")
        for c in loose:
            names = ", ".join((c.get("matches") or {}).get("names", [])[:4])
            print(f"  {c['id']:18} {len(c['questions'])} вопр.  значения: "
                  f"{', '.join(map(str, c.get('values', [])))}")
            print(f"      обычно это: {names}")
        print(f"\nпередай выбор в param add: --catalog <id>")
        print(f"ничего не подходит — заведи свою: sm.py catalog-new")
    else:
        print("\nСОВПАДЕНИЙ НЕТ — семантика новая, заведи её: sm.py catalog-new")

    qs = (hit or {}).get("questions") or []
    if hit:
        print(f"  значения по умолчанию : {', '.join(map(str, hit.get('values', [])))}")
        print(f"  вне матрицы           : {', '.join(map(str, hit.get('special', [])))}")
        for sn in (hit.get("seen") or [])[-2:]:
            print(f"  раньше здесь          : {sn.get('where')} → {sn.get('values')}")
    if qs:
        print(f"\nВОПРОСОВ: {len(qs)}. Задавай ПО ОДНОМУ, с вариантами ответа."
              " Что нашёл в спеке — отвечай сам, не спрашивая.")
        print(f"первый: {qs[0]['ask']}")
        if qs[0].get("options"):
            print(f"  варианты: {' | '.join(qs[0]['options'])}")
        print(f"\nостальные и их варианты: sm.py catalog-get {a.model} {(hit or {}).get('id')}")
    else:
        print("  (у этого типа вопросов нет)")

    L["lookups"][a.name] = {"catalog": (hit or {}).get("id"),
                            "questions": [q["id"] for q in qs],
                            "choices": {c["id"]: [q["id"] for q in c["questions"]]
                                        for c in loose} if not exact else {},
                            "at": datetime.datetime.now().isoformat(timespec="seconds")}
    save_ledger(a.model, L)
    if exact or not loose:
        print(f"\nзапрос записан; дальше: sm.py param add {a.model} --name {a.name} …")


def cmd_param_add(a):
    L = ledger(a.model)
    look = L["lookups"].get(a.name)
    if not look:
        die(f"корзина для «{a.name}» не запрашивалась",
            f"сначала: sm.py catalog {a.model} {a.name} --type {a.type}")
    choices = look.get("choices") or {}
    if choices and not a.catalog:
        die(f"по имени «{a.name}» семантика не определилась — выбери сам",
            "подходят: " + ", ".join(choices) + "; передай --catalog <id>"
            " или заведи свою через sm.py catalog-new")
    if a.catalog:
        if choices and a.catalog not in choices:
            die(f"семантика «{a.catalog}» не подходит по типу",
                "подходят: " + ", ".join(choices))
        look = dict(look)
        look["catalog"] = a.catalog
        look["questions"] = choices.get(a.catalog, look["questions"])
    ans = dict(x.split("=", 1) for x in (a.answer or []))
    missing = [q for q in look["questions"] if q not in ans]
    if missing:
        die(f"нет ответов на вопросы семантики: {', '.join(missing)}",
            "ответить: -a <вопрос>=\"…\" по каждому, либо -a <вопрос>=неизвестно")
    if not a.frm:
        die("не указан --from", "источник значений обязателен: file:line")
    if not a.values:
        die("не указаны --values", "классы значений выводятся из ответов, но задаются явно")
    if not a.all_values:
        die("не указаны --all-values",
            "сначала перечисли ВСЕ возможные значения параметра из спеки, "
            "и только потом объединяй их в классы")
    extra = [v for v in a.all_values if v not in a.values]
    if extra and not a.grouping:
        die(f"{len(a.all_values)} значений свёрнуто в {len(a.values)} классов без объяснения",
            "нужен --grouping: почему эти значения ведут себя одинаково. "
            f"вне классов оказались: {', '.join(extra[:8])}")

    m = load_model(a.model)
    m.setdefault("params", {})
    if a.name in m["params"] and not a.force:
        die(f"параметр «{a.name}» уже есть", "перезаписать: --force")
    p = {"type": a.type, "all_values": a.all_values, "values": a.values, "from": a.frm}
    if a.grouping:
        p["grouping"] = a.grouping
    if a.desc: p["desc"] = a.desc
    if look.get("catalog"): p["catalog"] = look["catalog"]
    if a.special: p["special"] = a.special
    if a.env: p["env"] = True
    p["answers"] = ans
    m["params"][a.name] = p
    save_model(a.model, m)
    if extra:
        print(f"  объединено: {len(a.all_values)} значений → {len(a.values)} классов")
        print(f"  основание: {a.grouping}")
    print(f"параметр «{a.name}» добавлен: {len(a.values)} значений"
          f"{', ' + str(len(a.special)) + ' вне матрицы' if a.special else ''}"
          f"{', окружение' if a.env else ''}")


def cmd_exclude(a):
    m = load_model(a.model)
    m.setdefault("excluded", {})[a.name] = a.reason
    save_model(a.model, m)
    print(f"«{a.name}» исключён: {a.reason}")


def cmd_rule_add(a):
    m = load_model(a.model)
    P = m.get("params") or {}
    if not P:
        die("в модели нет параметров", "сначала добавь параметры")
    def parse(pairs):
        d = {}
        for x in pairs or []:
            k, v = x.split("=", 1)
            vals = v.split(",")
            if k not in P: die(f"неизвестный параметр «{k}»")
            for z in vals:
                if z not in [str(y) for y in P[k]["values"]]:
                    die(f"значение «{z}» отсутствует в {k}.values")
            d[k] = vals if len(vals) > 1 else vals[0]
        return d
    if not a.evidence:
        die("нет --evidence", "правило без основания не принимается")
    tail = a.evidence.split(":")[-1][:6] if ":" in a.evidence else ""
    has_ref = ":" in a.evidence and (any(ch.isdigit() for ch in tail) or "§" in a.evidence)
    status = "proven" if has_ref and not a.assumed else "assumed"
    if status == "assumed" and not a.ask:
        die("правило без ссылки file:line становится assumed и требует --ask",
            "сформулируй вопрос человеку одной фразой")
    r = {"id": a.id, "evidence": a.evidence, "status": status}
    if a.desc: r["desc"] = a.desc
    if a.ask: r["ask"] = a.ask
    if a.forbid:
        r["forbid"] = parse(a.forbid)
    elif a.irrelevant:
        r["when"] = parse(a.when)
        r["irrelevant"] = a.irrelevant
    else:
        die("нужно либо --forbid, либо --irrelevant")
    m.setdefault("constraints", []).append(r)
    save_model(a.model, m)
    print(f"правило {a.id} добавлено со статусом {status}")


def cmd_state_add(a):
    m = load_model(a.model)
    P = m.get("params") or {}
    d = {}
    for x in a.when or []:
        k, v = x.split("=", 1)
        if k not in P: die(f"неизвестный параметр «{k}»")
        vals = v.split(",")
        d[k] = vals if len(vals) > 1 else vals[0]
    if not a.evidence:
        die("нет --evidence", "состояние должно ссылаться на код или спеку")
    st = {"name": a.name, "when": d, "evidence": a.evidence}
    if a.desc: st["desc"] = a.desc
    m.setdefault("states", []).append(st)
    save_model(a.model, m)
    print(f"состояние «{a.name}» добавлено; условие: {d or 'всегда'}")


def cmd_build(a):
    """Вывод подпроцессов обязательно перехватывается и печатается через print:
    под MCP stdout — это поток JSON-RPC, и прямая запись в него ломает сессию."""
    import subprocess
    sc = lambda n: os.path.join(ROOT, "scripts", n)
    name = os.path.splitext(os.path.basename(a.model))[0].replace(".states", "")
    out = os.path.join(os.path.dirname(a.model) or ".", "..", "runs", name + ".json")
    out = os.path.normpath(out)
    steps = [["python3", sc("verify.py"), a.model, "--root", a.root],
             ["python3", sc("validate.py"), a.model],
             ["python3", sc("engine.py"), a.model, "-a",
              os.path.join(os.path.dirname(a.model) or ".", "..", "answers.json"), "-o", out]]
    for cmd in steps:
        r = subprocess.run(cmd, text=True, capture_output=True)
        text = (r.stdout or "") + (r.stderr or "")
        if text.strip():
            print(text.rstrip())
        if r.returncode:
            die(f"шаг не прошёл: {os.path.basename(cmd[1])}",
                "конвейер остановлен, модель не собрана")
    r = subprocess.run(["python3", sc("report_md.py"), out], text=True, capture_output=True)
    if r.returncode:
        die("отчёт не собрался", (r.stderr or "").strip()[:300])
    print()
    print(r.stdout.rstrip())


def main():
    ap = argparse.ArgumentParser(prog="sm.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("init", help="завести пустую модель")
    i.add_argument("model"); i.add_argument("--system", required=True)
    i.add_argument("--source", required=True)
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    sh = sub.add_parser("show", help="модель человеческим текстом")
    sh.add_argument("model"); sh.set_defaults(fn=cmd_show)

    rw = sub.add_parser("rows", help="строки матрицы для разбора")
    rw.add_argument("result"); rw.add_argument("--env", type=int, default=0)
    rw.add_argument("--no-state", action="store_true", dest="no_state")
    rw.add_argument("--status"); rw.add_argument("--limit", type=int, default=50)
    rw.set_defaults(fn=cmd_rows)

    an = sub.add_parser("answer", help="ответ человека")
    an.add_argument("model"); an.add_argument("id"); an.add_argument("value")
    an.add_argument("--section", default="constraints",
                    choices=["constraints", "outcomes"])
    an.set_defaults(fn=cmd_answer)

    c = sub.add_parser("catalog", help="ОБЯЗАТЕЛЬНЫЙ первый шаг для параметра")
    c.add_argument("model", nargs="?"); c.add_argument("name", nargs="?")
    c.add_argument("--type")
    c.set_defaults(fn=cmd_catalog)

    cl = sub.add_parser("catalog-list", help="показать корзину семантик")
    cl.add_argument("--type"); cl.add_argument("--model", default=".")
    cl.set_defaults(fn=cmd_catalog_list)

    cg = sub.add_parser("catalog-get", help="вопросы и значения конкретного типа")
    cg.add_argument("model"); cg.add_argument("id")
    cg.set_defaults(fn=cmd_catalog_get)

    ce = sub.add_parser("catalog-edit", help="дополнить тип вопросами и именами")
    ce.add_argument("model"); ce.add_argument("id")
    ce.add_argument("--add-questions", nargs="*", dest="add_questions")
    ce.add_argument("--add-names", nargs="*", dest="add_names")
    ce.add_argument("--add-values", nargs="*", dest="add_values")
    ce.add_argument("--add-special", nargs="*", dest="add_special")
    ce.add_argument("--desc")
    ce.set_defaults(fn=cmd_catalog_edit)

    cn = sub.add_parser("catalog-new", help="завести новый тип параметра")
    cn.add_argument("model"); cn.add_argument("--id", required=True)
    cn.add_argument("--title", required=True); cn.add_argument("--desc", required=True)
    cn.add_argument("--names", nargs="*"); cn.add_argument("--type", required=True)
    cn.add_argument("--questions", nargs="+"); cn.add_argument("--values", nargs="*")
    cn.add_argument("--special", nargs="*")
    cn.set_defaults(fn=cmd_catalog_new)

    p = sub.add_parser("param").add_subparsers(dest="x", required=True)
    pa = p.add_parser("add")
    pa.add_argument("model"); pa.add_argument("--name", required=True)
    pa.add_argument("--type", required=True); pa.add_argument("--values", nargs="+")
    pa.add_argument("--from", dest="frm"); pa.add_argument("--desc")
    pa.add_argument("--special", nargs="*"); pa.add_argument("--env", action="store_true")
    pa.add_argument("-a", "--answer", action="append")
    pa.add_argument("--all-values", nargs="+", dest="all_values",
                    help="ВСЕ возможные значения из спеки, до объединения")
    pa.add_argument("--grouping", help="почему значения объединены в классы")
    pa.add_argument("--catalog", help="id семантики, когда по имени не определилось")
    pa.add_argument("--force", action="store_true")
    pa.set_defaults(fn=cmd_param_add)
    pr = p.add_parser("rm"); pr.add_argument("model"); pr.add_argument("name")
    pr.set_defaults(fn=cmd_param_rm)

    e = sub.add_parser("exclude")
    e.add_argument("model"); e.add_argument("name"); e.add_argument("reason")
    e.set_defaults(fn=cmd_exclude)

    r = sub.add_parser("rule").add_subparsers(dest="x", required=True)
    ra = r.add_parser("add")
    ra.add_argument("model"); ra.add_argument("--id", required=True)
    ra.add_argument("--forbid", nargs="*"); ra.add_argument("--when", nargs="*")
    ra.add_argument("--irrelevant", nargs="*")
    ra.add_argument("--evidence"); ra.add_argument("--desc"); ra.add_argument("--ask")
    ra.add_argument("--assumed", action="store_true")
    ra.set_defaults(fn=cmd_rule_add)
    rr = r.add_parser("rm"); rr.add_argument("model"); rr.add_argument("id")
    rr.set_defaults(fn=cmd_rule_rm)

    st = sub.add_parser("state").add_subparsers(dest="x", required=True)
    sa = st.add_parser("add")
    sa.add_argument("model"); sa.add_argument("--name", required=True)
    sa.add_argument("--when", nargs="*"); sa.add_argument("--desc")
    sa.add_argument("--evidence")
    sa.set_defaults(fn=cmd_state_add)
    sr = st.add_parser("rm"); sr.add_argument("model"); sr.add_argument("name")
    sr.set_defaults(fn=cmd_state_rm)

    tr = sub.add_parser("transition").add_subparsers(dest="x", required=True)
    ta = tr.add_parser("add")
    ta.add_argument("model"); ta.add_argument("--event", required=True)
    ta.add_argument("--when", nargs="*"); ta.add_argument("--set", nargs="*")
    ta.add_argument("--evidence")
    ta.set_defaults(fn=cmd_transition_add)

    b = sub.add_parser("build")
    b.add_argument("model"); b.add_argument("--root", default=".")
    b.set_defaults(fn=cmd_build)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
